// Copyright 2021 Jonne Kokkonen
// Released under the MIT licence, https://opensource.org/licenses/MIT

#include "render.h"

#include <SDL3/SDL.h>

#include "SDL2_inprint.h"
#include "command.h"
#include "config.h"
#include "fx_cube.h"
#include "log_overlay.h"
#include "settings.h"

#include "fonts/fonts.h"

#include <stdlib.h>

// --- Start of Overlay Includes & Globals ---
#include <fcntl.h>
#include <unistd.h>
#include <sys/stat.h>
#include <string.h>
#include <ctype.h>

#define OVERLAY_PIPE "/tmp/m8c_overlay"
#define OVERLAY_DURATION 5000 

typedef struct {
    char lines[3][128];
    uint64_t hide_at;
    bool active;
    int pipe_fd;
} OverlayHUD;

static OverlayHUD hud = {0};

// Our dedicated Virtual Canvas for the overlay to guarantee perfect scaling
static SDL_Texture *overlay_texture = NULL; 

// We will store the dynamically sniffed theme color here 
static SDL_Color global_foreground_color = {0x00, 0x92, 0xBC, 255}; 
// --- End of Overlay Globals ---

static SDL_Window *win;
static SDL_Renderer *rend;
static SDL_Texture *main_texture;
static SDL_Texture *hd_texture = NULL;
static SDL_Color global_background_color = (SDL_Color){.r = 0x00, .g = 0x00, .b = 0x00, .a = 0x00};
static SDL_RendererLogicalPresentation window_scaling_mode = SDL_LOGICAL_PRESENTATION_INTEGER_SCALE;
static SDL_ScaleMode texture_scaling_mode = SDL_SCALEMODE_NEAREST;

static Uint64 ticks_fps;
static int fps;
static int font_mode = -1;
static unsigned int m8_hardware_model = 0;
static int screen_offset_y = 0;
static int text_offset_y = 0;
static int waveform_max_height = 24;

static int texture_width = 320;
static int texture_height = 240;
static int hd_texture_width, hd_texture_height = 0;

static SDL_FRect cached_dest_rect = {0};
static int cached_aspect_mode = 0; 

static int screensaver_initialized = 0;
uint8_t fullscreen = 0;
static uint8_t dirty = 0;

// --- Start of Overlay Functions ---
void update_overlay_data(void) {
    char buffer[512];
    ssize_t bytes = read(hud.pipe_fd, buffer, sizeof(buffer) - 1);
    
    if (bytes > 0) {
        buffer[bytes] = '\0';
        for (int j = 0; j < 3; j++) {
            hud.lines[j][0] = '\0';
        }

        char *token = strtok(buffer, "~");
        int i = 0;
        while (token != NULL && i < 3) {
            token[strcspn(token, "\r\n")] = 0; 
            for (int k = 0; token[k] != '\0'; k++) {
                token[k] = toupper((unsigned char)token[k]);
            }
            strncpy(hud.lines[i], token, 127);
            token = strtok(NULL, "~");
            i++;
        }
        
        hud.hide_at = SDL_GetTicks() + OVERLAY_DURATION;
        hud.active = true;
        dirty = 1; 
    }
}

static void draw_overlay(SDL_Renderer *renderer) {
    if (hud.active && SDL_GetTicks() > hud.hide_at) {
        hud.active = false;
        dirty = 1; 
        return;
    }

    if (!hud.active || !overlay_texture) return;

    // Save the current target so we don't break the M8's rendering flow
    SDL_Texture *old_target = SDL_GetRenderTarget(renderer);

    // 1. Switch our paintbrush to the 320x240 Virtual Canvas
    SDL_SetRenderTarget(renderer, overlay_texture);

    // Wipe the canvas completely transparent
    SDL_SetRenderDrawColor(renderer, 0, 0, 0, 0);
    SDL_RenderClear(renderer);

    // Draw the Background Box (Width stretches across the screen, 48px height)
    SDL_FRect bg = {0.0f, 0.0f, (float)texture_width, 48.0f}; 
    SDL_SetRenderDrawColor(renderer, global_background_color.r, global_background_color.g, global_background_color.b, 255);
    SDL_RenderFillRect(renderer, &bg);

    uint32_t bg_hex = (global_background_color.r << 16) | (global_background_color.g << 8) | global_background_color.b;
    uint32_t fg_hex = (global_foreground_color.r << 16) | (global_foreground_color.g << 8) | global_foreground_color.b;

    // Draw Text with clean, breathable 12-pixel line spacing
    for (int i = 0; i < 3; i++) {
        if (strlen(hud.lines[i]) > 0) {
            inprint(renderer, hud.lines[i], 4, 4 + (i * 12), fg_hex, bg_hex);
        }
    }

    // 2. Switch the paintbrush back to the main monitor output
    SDL_SetRenderTarget(renderer, old_target);

    // 3. Stretch and stamp our Virtual Canvas onto the screen
    SDL_RenderTexture(renderer, overlay_texture, NULL, NULL);
}
// --- End of Overlay Functions ---

static void update_cached_scaling(int window_width, int window_height) {
  const float texture_aspect_ratio = (float)texture_width / (float)texture_height;
  const float window_aspect_ratio = (float)window_width / (float)window_height;

  if (window_aspect_ratio > texture_aspect_ratio) {
    cached_aspect_mode = 1;
    cached_dest_rect.h = (float)window_height;
    cached_dest_rect.w = cached_dest_rect.h * texture_aspect_ratio;
    cached_dest_rect.x = ((float)window_width - cached_dest_rect.w) / 2.0f;
    cached_dest_rect.y = 0;
  } else if (window_aspect_ratio < texture_aspect_ratio) {
    cached_aspect_mode = -1;
    cached_dest_rect.w = (float)window_width;
    cached_dest_rect.h = cached_dest_rect.w / texture_aspect_ratio;
    cached_dest_rect.x = 0;
    cached_dest_rect.y = ((float)window_height - cached_dest_rect.h) / 2.0f;
  } else {
    cached_aspect_mode = 0;
  }
}

void setup_hd_texture_scaling(void) {
  int window_width, window_height;
  if (!SDL_GetWindowSizeInPixels(win, &window_width, &window_height)) {
    SDL_LogCritical(SDL_LOG_CATEGORY_RENDER, "Couldn't get window size: %s", SDL_GetError());
  }
  const float texture_aspect_ratio = (float)texture_width / (float)texture_height;
  const float window_aspect_ratio = (float)window_width / (float)window_height;
  update_cached_scaling(window_width, window_height);

  SDL_Texture *og_texture = SDL_GetRenderTarget(rend);
  SDL_SetRenderTarget(rend, NULL);
  SDL_SetRenderLogicalPresentation(rend, 0, 0, SDL_LOGICAL_PRESENTATION_DISABLED);
  SDL_SetTextureScaleMode(main_texture, SDL_SCALEMODE_NEAREST);

  if (texture_aspect_ratio == window_aspect_ratio) {
    SDL_SetTextureScaleMode(hd_texture, SDL_SCALEMODE_NEAREST);
  } else {
    SDL_SetTextureScaleMode(hd_texture, SDL_SCALEMODE_LINEAR);
  }
  SDL_SetRenderTarget(rend, og_texture);
}

static void create_hd_texture(void) {
  int window_width, window_height;
  SDL_GetWindowSizeInPixels(win, &window_width, &window_height);
  int scale_factor = SDL_min(window_width / texture_width, window_height / texture_height);
  if (scale_factor < 1) scale_factor = 1; 

  const int new_hd_texture_width = texture_width * scale_factor;
  const int new_hd_texture_height = texture_height * scale_factor;
  if (hd_texture != NULL && new_hd_texture_width == hd_texture_width &&
      new_hd_texture_height == hd_texture_height) {
    return;
  }

  hd_texture_width = new_hd_texture_width;
  hd_texture_height = new_hd_texture_height;

  if (hd_texture != NULL) SDL_DestroyTexture(hd_texture);

  hd_texture = SDL_CreateTexture(rend, SDL_PIXELFORMAT_ARGB8888, SDL_TEXTUREACCESS_TARGET,
                                 hd_texture_width, hd_texture_height);
  SDL_SetTextureScaleMode(hd_texture, SDL_SCALEMODE_LINEAR);
  SDL_SetTextureBlendMode(hd_texture,SDL_BLENDMODE_BLEND);
  setup_hd_texture_scaling();
}

static void change_font(const unsigned int index) {
  inline_font_close();
  inline_font_set_renderer(rend);
  inline_font_initialize(fonts_get(index));
}

void renderer_log_init(void) { log_overlay_init(); }

static void check_and_adjust_window_and_texture_size(const int new_width, const int new_height) {
  if (texture_width == new_width && texture_height == new_height) return;

  int window_h, window_w;
  texture_width = new_width;
  texture_height = new_height;

  SDL_GetWindowSize(win, &window_w, &window_h);
  if (window_w < texture_width * 2 || window_h < texture_height * 2) {
    SDL_SetWindowSize(win, texture_width * 2, texture_height * 2);
  }

  if (hd_texture != NULL) {
    SDL_DestroyTexture(hd_texture);
    create_hd_texture(); 
    setup_hd_texture_scaling();
  }

  if (main_texture != NULL) SDL_DestroyTexture(main_texture);
  
  // Update Overlay Texture size to exactly match the M8's physical resolution
  if (overlay_texture != NULL) SDL_DestroyTexture(overlay_texture);
  overlay_texture = SDL_CreateTexture(rend, SDL_PIXELFORMAT_ARGB8888, SDL_TEXTUREACCESS_TARGET, texture_width, texture_height);
  SDL_SetTextureBlendMode(overlay_texture, SDL_BLENDMODE_BLEND);

  log_overlay_invalidate();

  main_texture = SDL_CreateTexture(rend, SDL_PIXELFORMAT_ARGB8888, SDL_TEXTUREACCESS_TARGET,
                                   texture_width, texture_height);
  SDL_SetTextureScaleMode(main_texture, texture_scaling_mode);
  SDL_SetRenderTarget(rend, main_texture);

  settings_on_texture_size_change(rend);
}

void set_m8_model(const unsigned int model) {
  if (model == 1) {
    m8_hardware_model = 1;
    check_and_adjust_window_and_texture_size(480, 320);
  } else {
    m8_hardware_model = 0;
    check_and_adjust_window_and_texture_size(320, 240);
  }
}

void renderer_set_font_mode(int mode) {
  if (mode < 0 || mode > 2) return;
  if (m8_hardware_model == 1) mode += 2;
  if (font_mode == mode) return;

  font_mode = mode;
  const struct inline_font *new_font = fonts_get(mode);
  screen_offset_y = new_font->screen_offset_y;
  text_offset_y = new_font->text_offset_y;
  waveform_max_height = new_font->waveform_max_height;

  change_font(mode);
}

void renderer_close(void) {
  inline_font_close();
  if (main_texture != NULL) SDL_DestroyTexture(main_texture);
  if (hd_texture != NULL) SDL_DestroyTexture(hd_texture);
  if (overlay_texture != NULL) SDL_DestroyTexture(overlay_texture);
  
  log_overlay_destroy();
  SDL_DestroyRenderer(rend);
  SDL_DestroyWindow(win);

  // --- Overlay Cleanup ---
  if (hud.pipe_fd > 0) close(hud.pipe_fd);
  unlink(OVERLAY_PIPE); 
  // -----------------------
}

int toggle_fullscreen(config_params_s *conf) {
  const unsigned long fullscreen_state = SDL_GetWindowFlags(win) & SDL_WINDOW_FULLSCREEN;
  SDL_SetWindowFullscreen(win, fullscreen_state ? false : true);
  conf->init_fullscreen = (unsigned int)!fullscreen_state;
  SDL_SyncWindow(win);
  if (fullscreen_state) SDL_ShowCursor();
  else SDL_HideCursor();

  dirty = 1;
  return (int)conf->init_fullscreen;
}

int draw_character(struct draw_character_command *command) {
  const uint32_t fgcolor =
      command->foreground.r << 16 | command->foreground.g << 8 | command->foreground.b;
  const uint32_t bgcolor =
      command->background.r << 16 | command->background.g << 8 | command->background.b;

  // --- The Bulletproof "Tempo T" Sniffer ---
  // Looks for the 'T' character in the entire top-right block of the screen.
  // This catches the theme color whether the UI shifts it to Y=16, 24, or 32!
  if (command->c == 'T' && command->pos.x >= texture_width - 64 && command->pos.y >= 8 && command->pos.y <= 32) {
      global_foreground_color.r = command->foreground.r;
      global_foreground_color.g = command->foreground.g;
      global_foreground_color.b = command->foreground.b;
  }
  // -----------------------------------------

  inprint(rend, (char *)&command->c, command->pos.x,
          command->pos.y + text_offset_y + screen_offset_y, fgcolor, bgcolor);
  dirty = 1;
  return 1;
}

void draw_rectangle(struct draw_rectangle_command *command) {
  SDL_FRect render_rect;
  render_rect.x = (float)command->pos.x;
  render_rect.y = (float)(command->pos.y + screen_offset_y);
  render_rect.h = command->size.height;
  render_rect.w = command->size.width;

  if (render_rect.x == 0 && render_rect.y <= 0 && render_rect.w == (float)texture_width &&
      render_rect.h >= (float)texture_height) {
    global_background_color.r = command->color.r;
    global_background_color.g = command->color.g;
    global_background_color.b = command->color.b;
    global_background_color.a = 0xFF;
  }

  SDL_SetRenderDrawColor(rend, command->color.r, command->color.g, command->color.b, 0xFF);
  SDL_RenderFillRect(rend, &render_rect);
  dirty = 1;
}

void draw_waveform(struct draw_oscilloscope_waveform_command *command) {
  static uint8_t wfm_cleared = 0;
  static int prev_waveform_size = 0;

  if (!(wfm_cleared && command->waveform_size == 0)) {
    SDL_FRect wf_rect;
    if (command->waveform_size > 0) {
      wf_rect.x = (float)(texture_width - command->waveform_size);
      wf_rect.y = 0;
      wf_rect.w = command->waveform_size;
      wf_rect.h = (float)(waveform_max_height + 1);
    } else {
      wf_rect.x = (float)(texture_width - prev_waveform_size);
      wf_rect.y = 0;
      wf_rect.w = (float)prev_waveform_size;
      wf_rect.h = (float)(waveform_max_height + 1);
    }
    prev_waveform_size = command->waveform_size;

    SDL_SetRenderDrawColor(rend, global_background_color.r, global_background_color.g,
                           global_background_color.b, global_background_color.a);
    SDL_RenderFillRect(rend, &wf_rect);

    SDL_SetRenderDrawColor(rend, command->color.r, command->color.g, command->color.b, 255);

    static SDL_FPoint waveform_points[480];
    for (int i = 0; i < command->waveform_size; i++) {
      if (command->waveform[i] > waveform_max_height) {
        command->waveform[i] = waveform_max_height;
      }
      waveform_points[i].x = (float)i + wf_rect.x;
      waveform_points[i].y = command->waveform[i];
    }
    SDL_RenderPoints(rend, waveform_points, command->waveform_size);

    if (command->waveform_size == 0) wfm_cleared = 1;
    else wfm_cleared = 0;

    dirty = 1;
  }
}

void display_keyjazz_overlay(const uint8_t show, const uint8_t base_octave,
                             const uint8_t velocity) {
  const struct inline_font *font = fonts_get(font_mode);
  const Uint16 overlay_offset_x = texture_width - (font->glyph_x * 7 + 1);
  const Uint16 overlay_offset_y = texture_height - (font->glyph_y + 1);
  const Uint32 bg_color =
      global_background_color.r << 16 | global_background_color.g << 8 | global_background_color.b;

  if (show) {
    char overlay_text[7];
    SDL_snprintf(overlay_text, sizeof(overlay_text), "%02X %u", velocity, base_octave);
    inprint(rend, overlay_text, overlay_offset_x, overlay_offset_y, 0xC8C8C8, bg_color);
    inprint(rend, "*", overlay_offset_x + (font->glyph_x * 5 + 5), overlay_offset_y,
            0xFF0000, bg_color);
  } else {
    inprint(rend, "      ", overlay_offset_x, overlay_offset_y, 0xC8C8C8, bg_color);
  }
  dirty = 1;
}

static void log_fps_stats(void) {
  fps++;
  const Uint64 now = SDL_GetTicks();
  if (now - ticks_fps > 5000) {
    ticks_fps = now;
    fps = 0;
  }
}

int renderer_initialize(config_params_s *conf) {
  atexit(SDL_Quit);

  if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_EVENTS) == false) return 0;

  if (!SDL_CreateWindowAndRenderer("M8C", texture_width * 2, texture_height * 2,
                                   SDL_WINDOW_RESIZABLE | SDL_WINDOW_HIGH_PIXEL_DENSITY |
                                       SDL_WINDOW_OPENGL | conf->init_fullscreen,
                                   &win, &rend)) {
    return false;
  }

  SDL_SetRenderVSync(rend, 1);
  SDL_SetRenderLogicalPresentation(rend, texture_width, texture_height, window_scaling_mode);

  main_texture = SDL_CreateTexture(rend, SDL_PIXELFORMAT_ARGB8888, SDL_TEXTUREACCESS_TARGET,
                                   texture_width, texture_height);

  if (conf->integer_scaling == 0) create_hd_texture();

  SDL_SetTextureScaleMode(main_texture, texture_scaling_mode);
  SDL_SetRenderTarget(rend, main_texture);
  SDL_SetRenderDrawColor(rend, global_background_color.r, global_background_color.g,
                         global_background_color.b, global_background_color.a);
  SDL_RenderClear(rend);

  renderer_set_font_mode(0);

  // --- Overlay Init ---
  overlay_texture = SDL_CreateTexture(rend, SDL_PIXELFORMAT_ARGB8888, SDL_TEXTUREACCESS_TARGET, texture_width, texture_height);
  SDL_SetTextureBlendMode(overlay_texture, SDL_BLENDMODE_BLEND);

  mkfifo(OVERLAY_PIPE, 0666);
  hud.pipe_fd = open(OVERLAY_PIPE, O_RDWR | O_NONBLOCK);
  // --------------------

  SDL_SetHint(SDL_HINT_IOS_HIDE_HOME_INDICATOR, "1");
  renderer_fix_texture_scaling_after_window_resize(conf); 

  dirty = 1;
  SDL_PumpEvents();
  render_screen(conf);

  return 1;
}

void render_screen(config_params_s *conf) {
  if (!dirty && !settings_is_open()) return;

  dirty = 0;
  SDL_SetRenderTarget(rend, NULL);
  SDL_SetRenderDrawColor(rend, global_background_color.r, global_background_color.g,
                              global_background_color.b, global_background_color.a);
  SDL_RenderClear(rend);

  if (conf->integer_scaling) {
    SDL_RenderTexture(rend, main_texture, NULL, NULL);
    log_overlay_render(rend, texture_width, texture_height, texture_scaling_mode, font_mode);
    if (settings_is_open()) settings_render_overlay(rend, conf, texture_width, texture_height);
    
    // Drawn perfectly scaled on top!
    draw_overlay(rend); 

  } else {
    if (hd_texture == NULL) create_hd_texture();
    SDL_SetRenderTarget(rend, hd_texture);
    SDL_SetRenderDrawColor(rend, global_background_color.r, global_background_color.g,
                           global_background_color.b, global_background_color.a);
    SDL_RenderClear(rend);
    SDL_RenderTexture(rend, main_texture, NULL, NULL);
    log_overlay_render(rend, texture_width, texture_height, texture_scaling_mode, font_mode);
    if (settings_is_open()) settings_render_overlay(rend, conf, texture_width, texture_height);

    // Drawn perfectly scaled on top!
    draw_overlay(rend);

    SDL_SetRenderTarget(rend, NULL);
    if (cached_aspect_mode != 0) {
      SDL_RenderTexture(rend, hd_texture, NULL, &cached_dest_rect);
    } else {
      SDL_RenderTexture(rend, hd_texture, NULL, NULL);
    }
  }

  SDL_RenderPresent(rend);
  SDL_SetRenderTarget(rend, main_texture);
  log_fps_stats();
}

int screensaver_init(void) {
  if (screensaver_initialized) return 1;
  SDL_SetRenderTarget(rend, main_texture);
  renderer_set_font_mode(1);
  global_background_color.r = 0;
  global_background_color.g = 0;
  global_background_color.b = 0;
  fx_cube_init(rend, (SDL_Color){255, 255, 255, 255}, texture_width, texture_height,
               fonts_get(font_mode)->glyph_x);
  screensaver_initialized = 1;
  return 1;
}

void screensaver_draw(void) { dirty = fx_cube_update(); }

void screensaver_destroy(void) {
  fx_cube_destroy();
  renderer_set_font_mode(0);
  screensaver_initialized = 0;
}

void renderer_fix_texture_scaling_after_window_resize(config_params_s *conf) {
  SDL_SetRenderTarget(rend, NULL);
  if (conf->integer_scaling) {
    SDL_SetRenderLogicalPresentation(rend, texture_width, texture_height,
                                     SDL_LOGICAL_PRESENTATION_INTEGER_SCALE);
  } else {
    if (hd_texture != NULL) create_hd_texture(); 
    setup_hd_texture_scaling();
  }
  SDL_SetTextureScaleMode(main_texture, texture_scaling_mode);
}

void show_error_message(const char *message) {
  SDL_ShowSimpleMessageBox(SDL_MESSAGEBOX_ERROR, "m8c error", message, win);
}

void renderer_clear_screen(void) {
  SDL_SetRenderDrawColor(rend, global_background_color.r, global_background_color.g,
                         global_background_color.b, global_background_color.a);
  SDL_SetRenderTarget(rend, main_texture);
  SDL_RenderClear(rend);
  SDL_SetRenderTarget(rend, NULL);
  SDL_RenderClear(rend);
}

void renderer_request_redraw(void) { dirty = 1; }