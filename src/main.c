// Copyright 2021 Jonne Kokkonen
// Released under the MIT licence, https://opensource.org/licenses/MIT

/* Uncomment this line to enable debug messages or call make with `make
   CFLAGS=-DDEBUG_MSG` */
// #define DEBUG_MSG

#define APP_VERSION "v2.2.4"

#include <SDL3/SDL.h>
#define SDL_MAIN_USE_CALLBACKS
#include <SDL3/SDL_main.h>
#include <stdlib.h>

#include "SDL2_inprint.h"
#include "backends/audio.h"
#include "backends/m8.h"
#include "common.h"
#include "config.h"
#include "gamepads.h"
#include "render.h"
#include "log_overlay.h"

// --- Start of overlay ---

#include <SDL3_ttf/SDL_ttf.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/stat.h>
#include <string.h>

#define OVERLAY_PIPE "/tmp/m8c_overlay"
#define OVERLAY_DURATION 5000 // 5 seconds in milliseconds

typedef struct {
    char lines[3][128];
    uint64_t hide_at;
    TTF_Font *font;
    bool active;
    int pipe_fd;
} OverlayHUD;

OverlayHUD hud = {0};

void update_overlay_data() {
    char buffer[512];
    // Non-blocking read from the pipe
    ssize_t bytes = read(hud.pipe_fd, buffer, sizeof(buffer) - 1);
    
    if (bytes > 0) {
        buffer[bytes] = '\0';
        
        // 1. Wipe old lines before writing new ones
        for (int j = 0; j < 3; j++) {
            hud.lines[j][0] = '\0';
        }

        // 2. Parse the data using the tilde (~) as the line breaker
        char *token = strtok(buffer, "~");
        int i = 0;
        while (token != NULL && i < 3) {
            // Strip any invisible newlines sent by the terminal
            token[strcspn(token, "\r\n")] = 0; 
            strncpy(hud.lines[i], token, 127);
            token = strtok(NULL, "~");
            i++;
        }
        
        // 3. Force the screen to update instantly to show the new HUD
        if (!hud.active) {
            m8_reset_display(); 
        }
        
        hud.hide_at = SDL_GetTicks() + OVERLAY_DURATION;
        hud.active = true;
    }
}

void draw_overlay(SDL_Renderer *renderer) {
    // Check if the 5 seconds are up
    if (hud.active && SDL_GetTicks() > hud.hide_at) {
        hud.active = false;
        // Force the M8 to redraw the screen, wiping the old HUD away
        m8_reset_display(); 
        return;
    }

    if (!hud.active) {
        return;
    }

    // 1. Draw Background Box (Black) 
    // Height set to exactly 48.0f to cover the 3 waveform rows
    SDL_FRect bg = {0.0f, 0.0f, 320.0f, 48.0f}; 
    SDL_SetRenderDrawColor(renderer, 0, 0, 0, 255);
    SDL_RenderFillRect(renderer, &bg);

    // 2. Draw 3 Lines of Text (White)
    SDL_Color white = {255, 255, 255, 255};
    for (int i = 0; i < 3; i++) {
        if (strlen(hud.lines[i]) > 0) {
            SDL_Surface *surf = TTF_RenderText_Blended(hud.font, hud.lines[i], 0, white);
            if (surf) {
                SDL_Texture *tex = SDL_CreateTextureFromSurface(renderer, surf);
                float tw = (float)surf->w;
                float th = (float)surf->h;
                // Start at y=4, add 16px per line for perfect double-spacing
                SDL_FRect dst = {4.0f, 4.0f + (i * 16.0f), tw, th};
                SDL_RenderTexture(renderer, tex, NULL, &dst);
                SDL_DestroySurface(surf);
                SDL_DestroyTexture(tex);
            }
        }
    }
}

// --- End of overlay ---

static void do_wait_for_device(struct app_context *ctx) {
  static Uint64 ticks_poll_device = 0;
  static int screensaver_initialized = 0;

  // Handle app suspension
  if (ctx->app_suspended) {
    return;
  }

  if (!screensaver_initialized) {
    screensaver_initialized = screensaver_init();
  }
  screensaver_draw();
  render_screen(&ctx->conf);

  // Poll for M8 device every second
  if (ctx->device_connected == 0 && SDL_GetTicks() - ticks_poll_device > 1000) {
    ticks_poll_device = SDL_GetTicks();
    if (m8_initialize(0, ctx->preferred_device)) {

      SDL_Log("Device found, settling USB...");
      SDL_Delay(500); // Wait for Linux USB bus to settle

      if (ctx->conf.audio_enabled) {
        if (!audio_initialize(ctx->conf.audio_device_name, ctx->conf.audio_buffer_size)) {
          SDL_LogError(SDL_LOG_CATEGORY_AUDIO, "Cannot initialize audio");
          ctx->conf.audio_enabled = 0;
        }
      }

      const int m8_enabled = m8_enable_display(1);
      // Device was found; enable display and proceed to the main loop
      if (m8_enabled == 1) {
        ctx->app_state = RUN;
        ctx->device_connected = 1;
        SDL_Delay(100); 
        screensaver_destroy();
        screensaver_initialized = 0;
        // The reset is now handled in the main iterate loop for better reliability
      } else {
        SDL_LogCritical(SDL_LOG_CATEGORY_ERROR, "Device not detected.");
        ctx->app_state = QUIT;
        screensaver_destroy();
        screensaver_initialized = 0;
#ifdef USE_RTMIDI
        show_error_message(
            "Cannot initialize M8 remote display. Make sure you're running "
            "firmware 6.0.0 or newer. Please close and restart the application to try again.");
#endif
      }
    }
  }
}

static config_params_s initialize_config(int argc, char *argv[], char **preferred_device,
                                         char **config_filename) {
  for (int i = 1; i < argc; i++) {
    if (SDL_strcmp(argv[i], "--list") == 0) {
      exit(m8_list_devices());
    }
    if (SDL_strcmp(argv[i], "--dev") == 0 && i + 1 < argc) {
      *preferred_device = argv[i + 1];
      SDL_Log("Using preferred device: %s", *preferred_device);
      i++;
    } else if (SDL_strcmp(argv[i], "--config") == 0 && i + 1 < argc) {
      *config_filename = argv[i + 1];
      SDL_Log("Using config file: %s", *config_filename);
      i++;
    }
  }

  config_params_s conf = config_initialize(*config_filename);

  if (TARGET_OS_IOS == 1) {
    // Predefined settings for iOS
    conf.init_fullscreen = 1;
  }
  config_read(&conf);

  return conf;
}

// Main callback loop - read inputs, process data from the device, render screen
SDL_AppResult SDL_AppIterate(void *appstate) {
  if (appstate == NULL) {
    return SDL_APP_FAILURE;
  }

  struct app_context *ctx = appstate;
  SDL_AppResult app_result = SDL_APP_CONTINUE;

  // Poll for overlay text data from Python every frame
  update_overlay_data();

  switch (ctx->app_state) {
  case INITIALIZE:
    break;

  case WAIT_FOR_DEVICE:
    do_wait_for_device(ctx);
    break;

  case RUN: {
    // Handle app suspension
    if (ctx->app_suspended) {
      return SDL_APP_CONTINUE;
    }

    // --- FIX: Force full M8 refresh on the first frame of the main loop ---
    static int initial_reset_done = 0;
    if (!initial_reset_done) {
        SDL_Log("Main loop active. Forcing initial M8 display reset...");
        SDL_Delay(200);      // Tiny extra wait to ensure window is hot
        m8_reset_display();  // Command M8 to send a full frame
        initial_reset_done = 1;
    }
    // ----------------------------------------------------------------------

    const int result = m8_process_data(&ctx->conf);
    if (result == DEVICE_DISCONNECTED) {
      ctx->device_connected = 0;
      ctx->app_state = WAIT_FOR_DEVICE;
      initial_reset_done = 0; // Reset flag for next reconnection
      audio_close();
    } else if (result == DEVICE_FATAL_ERROR) {
      return SDL_APP_FAILURE;
    }
    
    render_screen(&ctx->conf);

    // Overlay is drawn AFTER render_screen so it sits on top of the M8 interface
    // Intercept the active window and renderer directly from SDL3
    int num_windows = 0;
    SDL_Window **windows = SDL_GetWindows(&num_windows);
    if (windows && num_windows > 0) {
        SDL_Renderer *active_renderer = SDL_GetRenderer(windows[0]);
        if (active_renderer) {
            draw_overlay(active_renderer);
        }
        SDL_free(windows); // SDL3 requires us to free the window list
    }

    break;
  }

  case QUIT:
    app_result = SDL_APP_SUCCESS;
    break;
  }

  return app_result;
}

// Initialize the app: initialize context, configs, renderer controllers and attempt to find M8
SDL_AppResult SDL_AppInit(void **appstate, int argc, char **argv) {
  SDL_SetAppMetadata("M8C",APP_VERSION,"fi.laamaa.m8c");

  char *config_filename = NULL;

  // Initialize in-app log capture/overlay
  log_overlay_init();

#ifndef NDEBUG
  // Show debug messages in the application log
  SDL_SetLogPriorities(SDL_LOG_PRIORITY_DEBUG);
  SDL_LogDebug(SDL_LOG_CATEGORY_TEST, "Running a Debug build");
#else
  // Show debug messages in the application log
  SDL_SetLogPriorities(SDL_LOG_PRIORITY_INFO);
#endif

  // FIX: Process callback at 60 Hz to match M8 hardware and reduce USB stress
  SDL_SetHint(SDL_HINT_MAIN_CALLBACK_RATE, "60");

  struct app_context *ctx = SDL_calloc(1, sizeof(struct app_context));
  if (ctx == NULL) {
    SDL_LogCritical(SDL_LOG_CATEGORY_SYSTEM, "SDL_calloc failed: %s", SDL_GetError());
    return SDL_APP_FAILURE;
  }

  *appstate = ctx;
  ctx->app_state = INITIALIZE;
  ctx->conf = initialize_config(argc, argv, &ctx->preferred_device, &config_filename);

  if (!renderer_initialize(&ctx->conf)) {
    SDL_LogCritical(SDL_LOG_CATEGORY_ERROR, "Failed to initialize renderer.");
    return SDL_APP_FAILURE;
  }

  ctx->device_connected =
      m8_initialize(1, ctx->preferred_device);

  // FIX: Settle USB bus after initialization
  if (ctx->device_connected) {
    SDL_Log("M8 detected on launch. Settling USB bus...");
    SDL_Delay(500); 
  }

  if (gamepads_initialize() < 0) {
    SDL_LogCritical(SDL_LOG_CATEGORY_ERROR, "Failed to initialize game controllers.");
    return SDL_APP_FAILURE;
  }

  if (ctx->device_connected && m8_enable_display(1)) {
    if (ctx->conf.audio_enabled) {
      audio_initialize(ctx->conf.audio_device_name, ctx->conf.audio_buffer_size);
    }
    ctx->app_state = RUN;
    // Initial m8_reset_display() is now handled in SDL_AppIterate for better timing
    render_screen(&ctx->conf);
  } else {
    SDL_LogCritical(SDL_LOG_CATEGORY_ERROR, "Device not detected.");
    ctx->device_connected = 0;
    ctx->app_state = WAIT_FOR_DEVICE;
  }

  // --- HUD INITIALIZATION ---
  TTF_Init();
  // Changed font size to 8 to match native M8 text scale
  hud.font = TTF_OpenFont("assets/stealth57.ttf", 8); 
  if (!hud.font) {
      SDL_Log("HUD: Could not load font from assets/stealth57.ttf: %s", SDL_GetError());
  }

  // Create and open the Pipe (FIFO) for Python
  mkfifo(OVERLAY_PIPE, 0666);
  // O_RDWR prevents the pipe from aggressively spinning when Python closes its end
  hud.pipe_fd = open(OVERLAY_PIPE, O_RDWR | O_NONBLOCK);
  // --------------------------

  return SDL_APP_CONTINUE;
}

void SDL_AppQuit(void *appstate, SDL_AppResult result) {
  (void)result; // Suppress compiler warning

  struct app_context *app = appstate;

  if (app) {
    if (app->app_state == WAIT_FOR_DEVICE) {
      screensaver_destroy();
    }
    if (app->conf.audio_enabled) {
      audio_close();
    }
    gamepads_close();
    renderer_close();
    inline_font_close();
    if (app->device_connected) {
      m8_close();
    }
    SDL_free(app);

    // --- HUD CLEANUP ---
    if (hud.font) TTF_CloseFont(hud.font);
    if (hud.pipe_fd > 0) close(hud.pipe_fd);
    TTF_Quit();
    unlink(OVERLAY_PIPE); 
    // -------------------

    SDL_Log("Shutting down.");
    SDL_Quit();
  }
}
