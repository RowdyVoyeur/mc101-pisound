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
#include <errno.h>

#define OVERLAY_PIPE "/tmp/m8c_overlay"
#define OVERLAY_DURATION 5000 

typedef struct {
    char lines[3][128];
    uint64_t hide_at;
    bool active;
    int pipe_fd;
    char pipe_buffer[1024];
    size_t pipe_buffer_len;
} OverlayHUD;

static OverlayHUD hud = {0};

static SDL_Texture *overlay_texture = NULL;

#define HUD_THEME_MAX_SAMPLES 32
#define HUD_HIGHLIGHT_MARKER ">X<"
#define HUD_OVERLAY_BG_HEIGHT 48.0f
#define HUD_LINE_1_X 8
#define HUD_LINE_1_Y 4
#define HUD_LINE_2_X 8
#define HUD_LINE_2_Y 22
#define HUD_LINE_3_X 8
#define HUD_LINE_3_Y 36
#define HUD_THEME_FREEZE_DELAY_MS 1200

typedef struct {
    SDL_Color color;
    int weight;
} HUDThemeSample;

typedef struct {
    SDL_Color background;
    SDL_Color main;
    SDL_Color highlight;
    bool background_ready;
    bool main_ready;
    bool highlight_ready;
    bool highlight_locked;
    bool main_probe_locked;
    bool highlight_probe_locked;
    bool theme_frozen;
    bool full_redraw_seen;
    Uint64 redraw_started_at;
} HUDTheme;

static HUDTheme hud_theme = {
    .background = {0x00, 0x00, 0x00, 255},
    .main = {0xFF, 0xFF, 0xFF, 255},
    .highlight = {0xFF, 0xFF, 0xFF, 255},
    .background_ready = false,
    .main_ready = false,
    .highlight_ready = false,
    .highlight_locked = false,
    .main_probe_locked = false,
    .highlight_probe_locked = false,
    .theme_frozen = false,
    .full_redraw_seen = false,
    .redraw_started_at = 0,
};

static HUDThemeSample hud_main_samples[HUD_THEME_MAX_SAMPLES] = {0};
static HUDThemeSample hud_main_probe_samples[HUD_THEME_MAX_SAMPLES] = {0};
static HUDThemeSample hud_highlight_samples[HUD_THEME_MAX_SAMPLES] = {0};
static HUDThemeSample hud_highlight_probe_samples[HUD_THEME_MAX_SAMPLES] = {0};

// Kept for existing renderer paths that still need a simple current colour.
static SDL_Color global_foreground_color = {0xFF, 0xFF, 0xFF, 255};
static SDL_Color global_background_color = {0x00, 0x00, 0x00, 255};
// --- End of Overlay Globals ---

static SDL_Window *win;
static SDL_Renderer *rend;
static SDL_Texture *main_texture;
static SDL_Texture *hd_texture = NULL;
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
static SDL_Color hud_make_color(uint8_t r, uint8_t g, uint8_t b) {
    return (SDL_Color){r, g, b, 255};
}

static Uint32 hud_color_to_hex(SDL_Color color) {
    return 0xFF000000 | ((Uint32)color.r << 16) | ((Uint32)color.g << 8) | color.b;
}

static bool hud_same_color(SDL_Color a, SDL_Color b) {
    return a.r == b.r && a.g == b.g && a.b == b.b;
}

static int hud_luma(SDL_Color color) {
    return ((int)color.r * 299 + (int)color.g * 587 + (int)color.b * 114) / 1000;
}

static SDL_Color hud_normalize_main_color(SDL_Color color) {
    uint8_t max = color.r;
    if (color.g > max) max = color.g;
    if (color.b > max) max = color.b;

    uint8_t min = color.r;
    if (color.g < min) min = color.g;
    if (color.b < min) min = color.b;

    if (max == 0) return color;

    /*
     * On dark themes the M8 often sends the main foreground as a dimmed neutral
     * colour. For HUD use, lift that to the bright foreground. On light themes,
     * however, the main foreground is intentionally grey, so keep it as-is.
     */
    if ((uint8_t)(max - min) <= 16) {
        if (!hud_theme.background_ready || hud_luma(hud_theme.background) < 128) {
            return hud_make_color(0xFF, 0xFF, 0xFF);
        }
        return color;
    }

    return hud_make_color((uint8_t)((color.r * 255) / max),
                          (uint8_t)((color.g * 255) / max),
                          (uint8_t)((color.b * 255) / max));
}

static bool hud_rgb_is_color(uint8_t r, uint8_t g, uint8_t b, SDL_Color color) {
    return r == color.r && g == color.g && b == color.b;
}

static bool hud_rgb_is_not_background(uint8_t r, uint8_t g, uint8_t b) {
    return !hud_rgb_is_color(r, g, b, hud_theme.background);
}

static int hud_scale_x(int x) {
    return (x * texture_width) / 320;
}

static int hud_scale_y(int y) {
    return (y * texture_height) / 240;
}

static bool hud_pos_in_scaled_box(int x, int y, int min_x, int max_x, int min_y, int max_y) {
    return x >= hud_scale_x(min_x) && x <= hud_scale_x(max_x) &&
           y >= hud_scale_y(min_y) && y <= hud_scale_y(max_y);
}

static bool hud_is_song_main_probe_position(int x, int y) {
    /*
     * Stable main-colour foregrounds on the SONG screen:
     * - tempo area around T>128
     * - non-selected row labels
     * - non-selected column labels
     */
    return hud_pos_in_scaled_box(x, y, 262, 319, 48, 72) ||
           hud_pos_in_scaled_box(x, y, 0, 50, 76, 208) ||
           hud_pos_in_scaled_box(x, y, 96, 255, 50, 72);
}

static bool hud_is_song_highlight_probe_position(int x, int y) {
    /*
     * Cursor/selected row/selected column area on the default SONG screen.
     * These boxes are scaled from the 320x240 logical layout so they still work
     * on 480x320 Model:02 rendering.
     */
    return hud_pos_in_scaled_box(x, y, 0, 72, 48, 84) ||
           hud_pos_in_scaled_box(x, y, 50, 92, 42, 78);
}

static int hud_color_max_channel(SDL_Color color) {
    uint8_t max = color.r;
    if (color.g > max) max = color.g;
    if (color.b > max) max = color.b;
    return max;
}

static bool hud_theme_debug_enabled(void) {
    static int enabled = -1;
    if (enabled == -1) {
        enabled = getenv("M8C_HUD_THEME_DEBUG") != NULL ? 1 : 0;
    }
    return enabled == 1;
}

static void hud_reset_theme_samples(void) {
    memset(hud_main_samples, 0, sizeof(hud_main_samples));
    memset(hud_main_probe_samples, 0, sizeof(hud_main_probe_samples));
    memset(hud_highlight_samples, 0, sizeof(hud_highlight_samples));
    memset(hud_highlight_probe_samples, 0, sizeof(hud_highlight_probe_samples));
    hud_theme.main_probe_locked = false;
    hud_theme.highlight_probe_locked = false;
}

static void hud_add_theme_sample(HUDThemeSample samples[HUD_THEME_MAX_SAMPLES], SDL_Color color,
                                 int weight) {
    if (weight <= 0) return;

    for (int i = 0; i < HUD_THEME_MAX_SAMPLES; i++) {
        if (samples[i].weight > 0 && hud_same_color(samples[i].color, color)) {
            samples[i].weight += weight;
            return;
        }
    }

    for (int i = 0; i < HUD_THEME_MAX_SAMPLES; i++) {
        if (samples[i].weight == 0) {
            samples[i].color = color;
            samples[i].weight = weight;
            return;
        }
    }

    int weakest = 0;
    for (int i = 1; i < HUD_THEME_MAX_SAMPLES; i++) {
        if (samples[i].weight < samples[weakest].weight) weakest = i;
    }

    if (weight > samples[weakest].weight) {
        samples[weakest].color = color;
        samples[weakest].weight = weight;
    }
}

static int hud_color_chroma(SDL_Color color) {
    uint8_t max = color.r;
    if (color.g > max) max = color.g;
    if (color.b > max) max = color.b;

    uint8_t min = color.r;
    if (color.g < min) min = color.g;
    if (color.b < min) min = color.b;

    return max - min;
}

static bool hud_is_neutral_color(SDL_Color color) {
    return hud_color_chroma(color) <= 24;
}

static SDL_Color hud_best_theme_sample(HUDThemeSample samples[HUD_THEME_MAX_SAMPLES], int *weight) {
    int best = -1;
    for (int i = 0; i < HUD_THEME_MAX_SAMPLES; i++) {
        if (samples[i].weight <= 0) continue;
        if (best < 0 || samples[i].weight > samples[best].weight) best = i;
    }

    if (best < 0) {
        *weight = 0;
        return hud_make_color(0, 0, 0);
    }

    *weight = samples[best].weight;
    return samples[best].color;
}

static SDL_Color hud_best_highlight_sample(HUDThemeSample samples[HUD_THEME_MAX_SAMPLES],
                                           int *weight) {
    int best = -1;

    /*
     * Highlight should be the theme accent colour, not neutral text backgrounds.
     * In the default theme the neutral selected-text background can appear as
     * #D8E0D8, while the actual highlight/accent appears as orange. Prefer
     * chromatic candidates when they exist, then fall back to the strongest
     * neutral candidate for monochrome themes.
     */
    for (int i = 0; i < HUD_THEME_MAX_SAMPLES; i++) {
        if (samples[i].weight <= 0) continue;
        if (hud_is_neutral_color(samples[i].color)) continue;
        if (best < 0 || samples[i].weight > samples[best].weight) best = i;
    }

    if (best < 0) {
        return hud_best_theme_sample(samples, weight);
    }

    *weight = samples[best].weight;
    return samples[best].color;
}

static SDL_Color hud_best_main_probe_sample(int *weight) {
    int best = -1;
    int best_score = -1;
    const int bg_luma = hud_theme.background_ready ? hud_luma(hud_theme.background) : 0;

    for (int i = 0; i < HUD_THEME_MAX_SAMPLES; i++) {
        if (hud_main_probe_samples[i].weight <= 0) continue;

        const SDL_Color color = hud_main_probe_samples[i].color;
        if (hud_theme.background_ready && hud_same_color(color, hud_theme.background)) continue;
        if (!hud_is_neutral_color(color)) continue;

        const int luma = hud_luma(color);
        const int contrast = abs(luma - bg_luma);

        /*
         * Main probe samples come from known SONG-screen text locations. Pick
         * the sample with the strongest contrast against the current background,
         * not the first colour that appears. This lets dark themes pick white
         * when it exists, while light themes keep their darker grey foreground.
         */
        const int score =
            hud_main_probe_samples[i].weight * 8 +
            contrast * 4 +
            (bg_luma < 128 ? luma : (255 - luma));

        if (best < 0 || score > best_score) {
            best = i;
            best_score = score;
        }
    }

    if (best < 0) {
        *weight = 0;
        return hud_make_color(0, 0, 0);
    }

    *weight = hud_main_probe_samples[best].weight;
    return hud_main_probe_samples[best].color;
}

static SDL_Color hud_best_cursor_probe_sample(int *weight) {
    int best = -1;
    int best_score = -1;

    for (int i = 0; i < HUD_THEME_MAX_SAMPLES; i++) {
        if (hud_highlight_probe_samples[i].weight <= 0) continue;

        const SDL_Color color = hud_highlight_probe_samples[i].color;
        if (hud_is_neutral_color(color)) continue;

        const int score =
            hud_color_max_channel(color) * 8 +
            hud_color_chroma(color) * 4 +
            hud_luma(color) +
            hud_highlight_probe_samples[i].weight;

        if (best < 0 || score > best_score) {
            best = i;
            best_score = score;
        }
    }

    if (best < 0) {
        *weight = 0;
        return hud_make_color(0, 0, 0);
    }

    *weight = hud_highlight_probe_samples[best].weight;
    return hud_highlight_probe_samples[best].color;
}

static bool hud_is_cursor_highlight_color(SDL_Color color) {
    if (!hud_theme.background_ready || hud_same_color(color, hud_theme.background)) return false;
    if (hud_is_neutral_color(color)) return false;

    /*
     * Ignore dark shadow/anti-alias variants of the cursor colour. The intended
     * cursor accent normally has at least one strong channel, while darker
     * variants such as brown/orange shadows do not.
     */
    return hud_color_max_channel(color) >= 150;
}

static void hud_maybe_freeze_theme(void) {
    if (hud_theme.theme_frozen) return;
    if (!hud_theme.full_redraw_seen) return;

    /*
     * Do not freeze as soon as the first probe hits. During startup/reset the M8
     * sends a full-screen background first, then the rest of the SONG screen.
     * Waiting a short, fixed delay after that full redraw avoids locking onto
     * early/transient colours before the cursor and header have both been drawn.
     */
    if (!(hud_theme.background_ready && hud_theme.main_ready && hud_theme.highlight_ready &&
          hud_theme.main_probe_locked && hud_theme.highlight_probe_locked)) {
        return;
    }

    const Uint64 now = SDL_GetTicks();
    if (now - hud_theme.redraw_started_at < HUD_THEME_FREEZE_DELAY_MS) {
        dirty = 1;
        return;
    }

    {
        int main_probe_weight = 0;
        SDL_Color main_probe = hud_best_main_probe_sample(&main_probe_weight);
        if (main_probe_weight > 0) {
            hud_theme.main = main_probe;
            hud_theme.main_ready = true;
            global_foreground_color = main_probe;
        }

        hud_theme.theme_frozen = true;

        if (hud_theme_debug_enabled()) {
            SDL_Log("HUD THEME frozen after stable redraw background=#%02X%02X%02X main=#%02X%02X%02X highlight=#%02X%02X%02X",
                    hud_theme.background.r, hud_theme.background.g, hud_theme.background.b,
                    hud_theme.main.r, hud_theme.main.g, hud_theme.main.b,
                    hud_theme.highlight.r, hud_theme.highlight.g, hud_theme.highlight.b);
        }
    }
}

static void hud_reset_theme_for_display_reset(const char *reason) {
    hud_theme.background_ready = false;
    hud_theme.main_ready = false;
    hud_theme.highlight_ready = false;
    hud_theme.highlight_locked = false;
    hud_theme.main_probe_locked = false;
    hud_theme.highlight_probe_locked = false;
    hud_theme.theme_frozen = false;
    hud_theme.full_redraw_seen = false;
    hud_theme.redraw_started_at = 0;
    hud_reset_theme_samples();

    if (hud_theme_debug_enabled()) {
        SDL_Log("HUD THEME reset for resample: %s", reason ? reason : "display reset");
    }
}

static void hud_set_main_theme_color_from_probe(SDL_Color color, int x, int y, char c) {
    if (hud_theme.theme_frozen) return;
    if (!hud_theme.background_ready || hud_same_color(color, hud_theme.background)) return;
    if (!hud_is_neutral_color(color)) return;

    /*
     * Do not lock the first main-colour probe. During a reset/redraw the first
     * neutral foreground can be a stale/dim UI label. Keep sampling until the
     * stable-render freeze point, and continuously choose the best contrast
     * candidate from the known SONG-screen main-text zones.
     */
    hud_add_theme_sample(hud_main_probe_samples, color, 8);

    int probe_weight = 0;
    SDL_Color best_probe = hud_best_main_probe_sample(&probe_weight);
    if (probe_weight <= 0) return;

    const bool changed = !hud_theme.main_probe_locked ||
                         !hud_same_color(hud_theme.main, best_probe);

    hud_theme.main = best_probe;
    hud_theme.main_ready = true;
    hud_theme.main_probe_locked = true;
    global_foreground_color = best_probe;

    if (changed) {
        dirty = 1;

        if (hud_theme_debug_enabled()) {
            SDL_Log("HUD THEME probe main char='%c' x=%d y=%d sample=#%02X%02X%02X selected=#%02X%02X%02X weight=%d",
                    c, x, y,
                    color.r, color.g, color.b,
                    best_probe.r, best_probe.g, best_probe.b, probe_weight);
        }
    }

    hud_maybe_freeze_theme();
}

static void hud_set_highlight_theme_color_from_probe(SDL_Color color, int x, int y, char c,
                                                     const char *source) {
    if (hud_theme.theme_frozen) return;
    if (!hud_is_cursor_highlight_color(color)) return;

    hud_add_theme_sample(hud_highlight_probe_samples, color, 24);

    int probe_weight = 0;
    SDL_Color best_probe = hud_best_cursor_probe_sample(&probe_weight);
    if (probe_weight <= 0) return;

    const bool changed = !hud_theme.highlight_probe_locked ||
                         !hud_same_color(hud_theme.highlight, best_probe);

    hud_theme.highlight = best_probe;
    hud_theme.highlight_ready = true;
    hud_theme.highlight_locked = true;
    hud_theme.highlight_probe_locked = true;

    if (changed) {
        dirty = 1;

        if (hud_theme_debug_enabled()) {
            SDL_Log("HUD THEME probe highlight %s char='%c' x=%d y=%d sample=#%02X%02X%02X selected=#%02X%02X%02X weight=%d",
                    source, c, x, y,
                    color.r, color.g, color.b,
                    best_probe.r, best_probe.g, best_probe.b, probe_weight);
        }
    }

    hud_maybe_freeze_theme();
}

static void hud_update_theme_from_samples(void) {
    if (hud_theme.theme_frozen) return;

    if (!hud_theme.main_probe_locked) {
        int main_weight = 0;
        SDL_Color main = hud_best_theme_sample(hud_main_samples, &main_weight);
        if (main_weight >= 5 && !hud_same_color(hud_theme.main, main)) {
            hud_theme.main = main;
            hud_theme.main_ready = true;
            global_foreground_color = main;
            dirty = 1;
        } else if (main_weight >= 5) {
            hud_theme.main_ready = true;
            global_foreground_color = hud_theme.main;
        }
    }

    if (!hud_theme.highlight_probe_locked && !hud_theme.highlight_locked) {
        int highlight_weight = 0;
        SDL_Color highlight = hud_best_highlight_sample(hud_highlight_samples, &highlight_weight);
        if (highlight_weight >= 5) {
            const bool changed = !hud_same_color(hud_theme.highlight, highlight);
            hud_theme.highlight = highlight;
            hud_theme.highlight_ready = true;

            /*
             * Lock the first stable accent colour until the theme/background changes.
             * This prevents transient state colours, such as a green PLAY indicator,
             * from replacing the actual theme highlight while the M8 is running.
             */
            if (!hud_is_neutral_color(highlight)) {
                hud_theme.highlight_locked = true;
            }

            if (changed) dirty = 1;
        }
    }
}

static void hud_log_theme_samples(const char *label,
                                  HUDThemeSample samples[HUD_THEME_MAX_SAMPLES]) {
    int used[3] = {-1, -1, -1};

    for (int rank = 0; rank < 3; rank++) {
        int best = -1;
        for (int i = 0; i < HUD_THEME_MAX_SAMPLES; i++) {
            if (samples[i].weight <= 0) continue;
            if (i == used[0] || i == used[1] || i == used[2]) continue;
            if (best < 0 || samples[i].weight > samples[best].weight) best = i;
        }

        if (best < 0) return;
        used[rank] = best;
        SDL_Log("HUD THEME %s #%d #%02X%02X%02X weight=%d", label, rank + 1,
                samples[best].color.r, samples[best].color.g, samples[best].color.b,
                samples[best].weight);
    }
}

static void hud_debug_log_theme(void) {
    static Uint64 last_log = 0;
    const Uint64 now = SDL_GetTicks();

    if (!hud_theme_debug_enabled() || now - last_log < 1000) return;
    last_log = now;

    SDL_Log("HUD THEME selected background=#%02X%02X%02X main=#%02X%02X%02X highlight=#%02X%02X%02X",
            hud_theme.background.r, hud_theme.background.g, hud_theme.background.b,
            hud_theme.main.r, hud_theme.main.g, hud_theme.main.b,
            hud_theme.highlight.r, hud_theme.highlight.g, hud_theme.highlight.b);
    hud_log_theme_samples("main", hud_main_samples);
    hud_log_theme_samples("main_probe", hud_main_probe_samples);
    hud_log_theme_samples("highlight", hud_highlight_samples);
    hud_log_theme_samples("highlight_probe", hud_highlight_probe_samples);
}

static void hud_set_background_theme_color(SDL_Color color) {
    if (hud_theme.theme_frozen) {
        global_background_color = hud_theme.background;
        return;
    }

    const bool background_changed =
        !hud_theme.background_ready || !hud_same_color(hud_theme.background, color);

    if (!hud_theme.full_redraw_seen || background_changed) {
        hud_theme.full_redraw_seen = true;
        hud_theme.redraw_started_at = SDL_GetTicks();
    }

    if (background_changed) {
        hud_theme.background = color;
        hud_theme.background_ready = true;
        global_background_color = color;

        hud_theme.main_ready = false;
        hud_theme.highlight_ready = false;
        hud_theme.highlight_locked = false;
        hud_theme.main_probe_locked = false;
        hud_theme.highlight_probe_locked = false;
        hud_reset_theme_samples();
        dirty = 1;

        if (hud_theme_debug_enabled()) {
            SDL_Log("HUD THEME redraw anchor background=#%02X%02X%02X",
                    color.r, color.g, color.b);
        }
        return;
    }

    global_background_color = color;
}

static void hud_sample_main_theme_color(SDL_Color color) {
    if (hud_theme.theme_frozen) return;
    if (!hud_theme.background_ready || hud_same_color(color, hud_theme.background)) return;
    hud_add_theme_sample(hud_main_samples, hud_normalize_main_color(color), 1);
    hud_update_theme_from_samples();
}

static void hud_sample_highlight_theme_color(SDL_Color color, int weight) {
    if (hud_theme.theme_frozen) return;
    if (!hud_theme.background_ready || hud_same_color(color, hud_theme.background)) return;
    hud_add_theme_sample(hud_highlight_samples, color, weight);
    hud_update_theme_from_samples();
}

static void hud_draw_text_run(SDL_Renderer *renderer, const char *text, int x, int y,
                              int glyph_step, Uint32 fg_hex, Uint32 bg_hex) {
    char c[2] = {0, 0};
    for (int i = 0; text[i] != '\0'; i++) {
        c[0] = text[i];
        inprint(renderer, c, x, y, fg_hex, bg_hex);
        x += glyph_step;
    }
}

static void hud_draw_line(SDL_Renderer *renderer, const char *text, int x, int y,
                          const struct inline_font *font, Uint32 main_hex, Uint32 highlight_hex,
                          Uint32 bg_hex) {
    const int glyph_step = font->glyph_x + 1;
    const size_t marker_len = strlen(HUD_HIGHLIGHT_MARKER);

    for (int i = 0; text[i] != '\0';) {
        if (marker_len > 0 && strncmp(&text[i], HUD_HIGHLIGHT_MARKER, marker_len) == 0) {
            hud_draw_text_run(renderer, HUD_HIGHLIGHT_MARKER, x, y, glyph_step, highlight_hex, bg_hex);
            x += (int)marker_len * glyph_step;
            i += (int)marker_len;
        } else {
            char c[2] = {text[i], '\0'};
            inprint(renderer, c, x, y, main_hex, bg_hex);
            x += glyph_step;
            i++;
        }
    }
}

static void hud_apply_overlay_message(char *message) {
    message[strcspn(message, "\r\n")] = '\0';

    bool has_visible_content = false;
    for (char *p = message; *p != '\0'; p++) {
        if (!isspace((unsigned char)*p) && *p != '~') {
            has_visible_content = true;
            break;
        }
    }

    if (!has_visible_content || strcmp(message, "__M8C_OVERLAY_CLEAR__") == 0) {
        for (int j = 0; j < 3; j++) {
            hud.lines[j][0] = '\0';
        }
        hud.active = false;
        dirty = 1;
        return;
    }

    for (int j = 0; j < 3; j++) {
        hud.lines[j][0] = '\0';
    }

    char *token = strtok(message, "~");
    int i = 0;
    while (token != NULL && i < 3) {
        for (int k = 0; token[k] != '\0'; k++) {
            token[k] = toupper((unsigned char)token[k]);
        }
        strncpy(hud.lines[i], token, sizeof(hud.lines[i]) - 1);
        hud.lines[i][sizeof(hud.lines[i]) - 1] = '\0';
        token = strtok(NULL, "~");
        i++;
    }

    hud.hide_at = SDL_GetTicks() + OVERLAY_DURATION;
    hud.active = true;
    dirty = 1;
}

void update_overlay_data(void) {
    char buffer[512];
    char latest_message[512] = {0};
    bool have_complete_message = false;

    for (;;) {
        ssize_t bytes = read(hud.pipe_fd, buffer, sizeof(buffer));
        if (bytes <= 0) {
            if (bytes < 0 && errno != EAGAIN && errno != EWOULDBLOCK) {
                hud.pipe_buffer_len = 0;
            }
            break;
        }

        if (hud.pipe_buffer_len + (size_t)bytes >= sizeof(hud.pipe_buffer)) {
            /*
             * Drop an incomplete backlog rather than rendering mixed fragments.
             * The overlay writer sends newline-terminated messages, so the next
             * complete message will repopulate the HUD immediately.
             */
            hud.pipe_buffer_len = 0;
        }

        memcpy(hud.pipe_buffer + hud.pipe_buffer_len, buffer, (size_t)bytes);
        hud.pipe_buffer_len += (size_t)bytes;

        for (;;) {
            char *newline = memchr(hud.pipe_buffer, '\n', hud.pipe_buffer_len);
            if (newline == NULL) break;

            size_t message_len = (size_t)(newline - hud.pipe_buffer);
            if (message_len >= sizeof(latest_message)) {
                message_len = sizeof(latest_message) - 1;
            }
            memcpy(latest_message, hud.pipe_buffer, message_len);
            latest_message[message_len] = '\0';
            have_complete_message = true;

            size_t consumed = (size_t)(newline - hud.pipe_buffer) + 1;
            memmove(hud.pipe_buffer, hud.pipe_buffer + consumed, hud.pipe_buffer_len - consumed);
            hud.pipe_buffer_len -= consumed;
        }
    }

    if (have_complete_message) {
        hud_apply_overlay_message(latest_message);
    }
}

static void draw_overlay(SDL_Renderer *renderer) {
    if (hud.active && SDL_GetTicks() > hud.hide_at) {
        hud.active = false;
        dirty = 1;
        return;
    }

    if (!hud.active || !overlay_texture) return;

    SDL_Texture *old_target = SDL_GetRenderTarget(renderer);
    SDL_SetRenderTarget(renderer, overlay_texture);

    SDL_SetRenderDrawColor(renderer, 0, 0, 0, 0);
    SDL_RenderClear(renderer);

    const int active_font_mode = font_mode >= 0 ? font_mode : 0;
    const struct inline_font *font = fonts_get(active_font_mode);

    const SDL_Color bg_color = hud_theme.background_ready ? hud_theme.background : global_background_color;
    const SDL_Color main_color = hud_theme.main_ready ? hud_theme.main : global_foreground_color;
    const SDL_Color highlight_color = hud_theme.highlight_ready ? hud_theme.highlight : main_color;

    SDL_FRect bg = {0.0f, 0.0f, (float)texture_width, HUD_OVERLAY_BG_HEIGHT};
    SDL_SetRenderDrawColor(renderer, bg_color.r, bg_color.g, bg_color.b, 255);
    SDL_RenderFillRect(renderer, &bg);

    const Uint32 bg_hex = hud_color_to_hex(bg_color);
    const Uint32 main_hex = hud_color_to_hex(main_color);
    const Uint32 highlight_hex = hud_color_to_hex(highlight_color);

    if (strlen(hud.lines[0]) > 0) {
        hud_draw_line(renderer, hud.lines[0], HUD_LINE_1_X, HUD_LINE_1_Y, font, main_hex, highlight_hex, bg_hex);
    }
    if (strlen(hud.lines[1]) > 0) {
        hud_draw_line(renderer, hud.lines[1], HUD_LINE_2_X, HUD_LINE_2_Y, font, main_hex, highlight_hex, bg_hex);
    }
    if (strlen(hud.lines[2]) > 0) {
        hud_draw_line(renderer, hud.lines[2], HUD_LINE_3_X, HUD_LINE_3_Y, font, main_hex, highlight_hex, bg_hex);
    }

    SDL_SetRenderTarget(renderer, old_target);
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
  
  if (overlay_texture != NULL) SDL_DestroyTexture(overlay_texture);
  overlay_texture = SDL_CreateTexture(
    rend,
    SDL_PIXELFORMAT_ARGB8888,
    SDL_TEXTUREACCESS_TARGET,
    texture_width,
    texture_height
);
SDL_SetTextureBlendMode(overlay_texture, SDL_BLENDMODE_BLEND);
SDL_SetTextureScaleMode(overlay_texture, SDL_SCALEMODE_NEAREST);

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

  if (hud.pipe_fd > 0) close(hud.pipe_fd);
  unlink(OVERLAY_PIPE); 
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

  if (hud_theme.background_ready && command->c != ' ') {
    const int sample_x = command->pos.x;
    const int sample_y = command->pos.y + text_offset_y + screen_offset_y;
    const SDL_Color fg = hud_make_color(command->foreground.r, command->foreground.g,
                                        command->foreground.b);
    const SDL_Color bg = hud_make_color(command->background.r, command->background.g,
                                        command->background.b);
    const bool bg_is_screen_bg = !hud_rgb_is_not_background(command->background.r,
                                                            command->background.g,
                                                            command->background.b);

    if (hud_is_song_main_probe_position(sample_x, sample_y) && bg_is_screen_bg) {
      hud_set_main_theme_color_from_probe(fg, sample_x, sample_y, command->c);
    }

    if (hud_is_song_highlight_probe_position(sample_x, sample_y)) {
      hud_set_highlight_theme_color_from_probe(fg, sample_x, sample_y, command->c, "fg");
      hud_set_highlight_theme_color_from_probe(bg, sample_x, sample_y, command->c, "bg");
    }

    if (bg_is_screen_bg) {
      hud_sample_main_theme_color(fg);
    } else {
      hud_sample_highlight_theme_color(bg, 2);
    }
  }

  hud_debug_log_theme();

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
    hud_set_background_theme_color(hud_make_color(command->color.r, command->color.g,
                                                  command->color.b));
  } else if (hud_theme.background_ready &&
             !hud_rgb_is_color(command->color.r, command->color.g, command->color.b,
                               hud_theme.background)) {
    const int screen_area = texture_width * texture_height;
    const int rect_area = (int)(render_rect.w * render_rect.h);
    const SDL_Color rect_color = hud_make_color(command->color.r, command->color.g,
                                                command->color.b);
    const int rect_center_x = (int)(render_rect.x + render_rect.w / 2.0f);
    const int rect_center_y = (int)(render_rect.y + render_rect.h / 2.0f);

    if (hud_is_song_highlight_probe_position(rect_center_x, rect_center_y)) {
      hud_set_highlight_theme_color_from_probe(rect_color, rect_center_x, rect_center_y,
                                               ' ', "rect");
    }

    if (rect_area > 0 && rect_area < screen_area / 2) {
      int weight = rect_area / 32;
      if (weight < 1) weight = 1;
      if (weight > 64) weight = 64;
      hud_sample_highlight_theme_color(rect_color, weight);
    }
  }

  hud_debug_log_theme();

  SDL_SetRenderDrawColor(rend, command->color.r, command->color.g, command->color.b, 255);
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
                           global_background_color.b, 255);
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
                         global_background_color.b, 255);
  SDL_RenderClear(rend);

  renderer_set_font_mode(0);

  // --- Overlay Init ---
overlay_texture = SDL_CreateTexture(
    rend,
    SDL_PIXELFORMAT_ARGB8888,
    SDL_TEXTUREACCESS_TARGET,
    texture_width,
    texture_height
);
SDL_SetTextureBlendMode(overlay_texture, SDL_BLENDMODE_BLEND);
SDL_SetTextureScaleMode(overlay_texture, SDL_SCALEMODE_NEAREST);

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
                              global_background_color.b, 255);
  SDL_RenderClear(rend);

  if (conf->integer_scaling) {
    SDL_RenderTexture(rend, main_texture, NULL, NULL);
    log_overlay_render(rend, texture_width, texture_height, texture_scaling_mode, font_mode);
    if (settings_is_open()) settings_render_overlay(rend, conf, texture_width, texture_height);
    
    draw_overlay(rend); 

  } else {
    if (hd_texture == NULL) create_hd_texture();
    SDL_SetRenderTarget(rend, hd_texture);
    SDL_SetRenderDrawColor(rend, global_background_color.r, global_background_color.g,
                           global_background_color.b, 255);
    SDL_RenderClear(rend);
    SDL_RenderTexture(rend, main_texture, NULL, NULL);
    log_overlay_render(rend, texture_width, texture_height, texture_scaling_mode, font_mode);
    if (settings_is_open()) settings_render_overlay(rend, conf, texture_width, texture_height);

    draw_overlay(rend);

    SDL_SetRenderTarget(rend, NULL);
    if (cached_aspect_mode != 0) {
      SDL_RenderTexture(rend, hd_texture, NULL, &cached_dest_rect);
    } else {
      SDL_RenderTexture(rend, hd_texture, NULL, NULL);
    }
  }

  SDL_RenderPresent(rend);
  hud_maybe_freeze_theme();
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
  hud_reset_theme_for_display_reset("display reset");

  SDL_SetRenderDrawColor(rend, global_background_color.r, global_background_color.g,
                         global_background_color.b, 255);
  SDL_SetRenderTarget(rend, main_texture);
  SDL_RenderClear(rend);
  SDL_SetRenderTarget(rend, NULL);
  SDL_RenderClear(rend);
}

void renderer_request_redraw(void) { dirty = 1; }