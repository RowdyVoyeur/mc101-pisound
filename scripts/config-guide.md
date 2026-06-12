# nanokontroller.py configuration guide

This guide explains how the `nanokontroller.py` script is configured and how to edit it safely. It is based on the script structure currently used in this repository.

## What the script does

`nanokontroller.py` receives MIDI from the nanoKONTROL, checks the active preset and scene, then sends one of the following:

- MIDI CC messages
- MIDI notes
- MIDI Start/Stop transport messages
- Roland MC-101 SysEx parameter changes
- M8 button/navigation messages
- HUD overlay text

The script opens three virtual MIDI ports:

```python
in_port = mido.open_input("In", virtual=True, client_name="nanoRouterIN")
out_port = mido.open_output("Out", virtual=True, client_name="nanoRouterOUT")
transport_out_port = mido.open_output(
    MC101_TRANSPORT_PORT_NAME,
    virtual=True,
    client_name=MC101_TRANSPORT_CLIENT_NAME,
)
```

Normal MIDI output goes through `nanoRouterOUT`.

MC-101 Start/Stop transport goes through `mc101TransportOUT`, so it can be routed only to the MC-101.

## MIDI channel numbering

The script uses `mido`, which numbers MIDI channels from `0` to `15`.

| Human MIDI channel | Script value |
|---:|---:|
| 1 | `0` |
| 2 | `1` |
| 5 | `4` |
| 8 | `7` |
| 13 | `12` |
| 15 | `14` |
| 16 | `15` |

Examples from the script:

```python
M8_CHANNEL = 15              # MIDI Channel 16
MC101_CONTROL_CHANNEL = 12   # MIDI Channel 13
M8_ROW_CUE_CHANNEL = 14      # MIDI Channel 15
```

When adding a new mapping, subtract `1` from the human MIDI channel number.

Example:

```python
("cc", 0): named(("cc", 4, 74, "CUT"), "Cutoff")
```

This sends `CC74` on human MIDI Channel `5`.

## Main configuration constants

The main constants are near the top of the script.

```python
OVERLAY_PIPE = "/tmp/m8c_overlay"

MC101_TRANSPORT_CLIENT_NAME = "mc101TransportOUT"
MC101_TRANSPORT_PORT_NAME = "Out"

M8_CHANNEL = 15
MC101_CONTROL_CHANNEL = 12

M8_ROW_CUE_CHANNEL = 14
M8_ROW_HOLD_ENABLED = True
M8_ROW_HOLD_CC = 64
M8_ROW_HOLD_VALUE = 127
M8_ROW_RELEASE_VALUE = 0
M8_ROW_NOTE_VELOCITY = 100
```

### `M8_ROW_HOLD_ENABLED`

This controls whether M8 row cue notes are held with CC64.

```python
M8_ROW_HOLD_ENABLED = True
```

| Value | Behaviour |
|---|---|
| `True` | Sends `CC64=127`, sends the row note, and keeps the row note held until another row is selected or the script exits. |
| `False` | Sends no CC64 and uses a short row note pulse instead. |

Use `False` when CC64 should be completely disabled.

## Preset structure

Most configuration lives in the `PRESETS` dictionary.

Basic structure:

```python
PRESETS = {
    PRESET_ID: {
        "name": "Preset Name",
        "context": "none",
        "display_values": True,
        "scenes": {
            SCENE_ID: {
                "name": "Scene Name",
                "mappings": {
                    # mappings go here
                }
            }
        }
    }
}
```

### Preset fields

| Field | Purpose |
|---|---|
| `name` | Name shown in the HUD. |
| `context` | Controls how the HUD builds the edit path. Current values include `"none"`, `"m8"`, `"track"`, `"partial"`, and `"drum"`. |
| `default_track` | Optional. Sets the active MC-101 track when the preset is selected. |
| `display_values` | Controls normal HUD parameter feedback. |
| `scenes` | Dictionary of scenes inside the preset. |

### Scene fields

| Field | Purpose |
|---|---|
| `name` | Scene name shown in the HUD. |
| `default_scene_bank` | Optional. Used by MC-101 scene-launch scenes. |
| `mappings` | Dictionary of incoming nanoKONTROL controls and their actions. |

Example:

```python
PRESET_3: {
    "name": "M8",
    "context": "none",
    "display_values": False,
    "scenes": {
        1: {
            "name": "Mixer",
            "mappings": {
                ("note", 0): named(("note", M8_CHANNEL, 12, "toggle", "M01"), "Mute Track 1"),
                ("cc", 9): named(("cc", M8_CHANNEL, 9, "V01"), "Volume Track 1"),
            }
        }
    }
}
```

## nanoKONTROL scene offsets

The script assumes 18 controls per nanoKONTROL scene.

| nanoKONTROL scene | Incoming CC/note range |
|---:|---:|
| Scene 1 | `0-17` |
| Scene 2 | `18-35` |
| Scene 3 | `36-53` |
| Scene 4 | `54-71` |

The offset is calculated as:

```python
offset = (active_scene - 1) * 18
```

Examples:

```python
("note", 0)   # Scene 1, first button
("note", 18)  # Scene 2, first button
("note", 36)  # Scene 3, first button
("note", 54)  # Scene 4, first button
```

Use the correct input range when adding a mapping to a specific scene.

## HUD behaviour

The HUD overlay can display:

- line 1: preset, scene, target path, parameter name and value
- line 2: first 9 matrix labels
- line 3: second 9 matrix labels

The matrix is built by:

```python
build_matrix_labels()
write_overlay_matrix()
update_overlay()
```

The active parameter label is replaced with:

```text
>X<
```

Unmapped controls display as:

```text
---
```

Labels are truncated to three characters:

```python
core_str = str(label).strip()[:3].upper().ljust(3, " ")
```

Good short labels:

```python
"CUT"
"RES"
"VEL"
"OC+"
"OC-"
"T01"
"P01"
"M01"
"S01"
```

### CCs and notes use different separators

The current script does not add square brackets around note/button labels.

It uses:

```python
sep = " | " if last_touched_type == "cc" else " : "
```

So:

- CC matrix labels are separated with ` | `
- note/button matrix labels are separated with ` : `

## `display_values`

Each preset can enable or disable normal HUD feedback.

```python
"display_values": True
```

or:

```python
"display_values": False
```

| Value | Behaviour |
|---|---|
| `True` | Normal parameter changes, buttons and knobs update the HUD. |
| `False` | Normal parameter/button feedback is hidden. |

Important details:

- Preset and scene selection can still briefly show the title and available button labels.
- Special mappings can still write directly to the HUD. For example, `audio_routing_info` writes only the selected routing description.
- When feedback is disabled, `clear_overlay()` writes a blank overlay message.

## Mapping names with `named(...)`

Most mappings should use `named(...)`.

```python
("cc", 0): named(("cc", M8_CHANNEL, 0, "C00"), "CC 00")
```

The short HUD label is inside the mapping tuple:

```python
"C00"
```

The long readable name is the second argument:

```python
"CC 00"
```

The script stores that long name as metadata:

```python
PARAMETER_NAME_KEY = "__parameter_name__"
```

This means the long name is part of the mapping itself, not kept in a separate table.

Use `named(...)` for new mappings unless the existing code pattern clearly does not use it.

## Standard mapping shape

A normal mapping looks like this:

```python
("input_type", input_number): named(("output_type", output_args...), "Long Name")
```

Examples:

```python
("cc", 0): named(("cc", M8_CHANNEL, 0, "C00"), "CC 00")
("note", 0): named(("note", M8_CHANNEL, 12, "toggle", "M01"), "Mute Track 1")
("note", 0): named(("track_select", 1, "T01"), "Track")
```

### Input types

| Input type | Meaning |
|---|---|
| `"cc"` | Incoming MIDI CC from the nanoKONTROL. |
| `"note"` | Incoming MIDI note from the nanoKONTROL. |

## Supported output types used by the current script

| Output type | Purpose |
|---|---|
| `"cc"` | Send a MIDI CC. |
| `"note"` | Send a MIDI note. Can be momentary or toggle. |
| `"m8_button"` | Hold an M8 button while pressed. Used for combos. |
| `"midi_transport"` | Send Start/Stop through `mc101TransportOUT`. |
| `"track_select"` | Change the active MC-101 track in script state. |
| `"partial_select"` | Change the active MC-101 partial in script state. |
| `"sysex"` | Write a Roland parameter for the active track/partial. |
| `"sysex_track"` | Write a track-level Roland parameter. |
| `"dynamic_sysex_track"` | Pick a SysEx address dynamically, usually by active partial. |
| `"conditional_sysex"` | Pick a SysEx mapping based on another parameter state. |
| `"conditional_sysex_track"` | Track-level version of `conditional_sysex`. |
| `"cycle_sysex"` | Cycle through values on repeated button presses. |
| `"param_mode_toggle"` | Toggle an internal parameter mode used by conditional mappings. |
| `"drum_pad_key_select"` | Select and play a drum key. |
| `"drum_scene_octave"` | Change drum key octave offset. |
| `"drum_pad_velocity"` | Change drum pad velocity. |
| `"drum_sysex_partial"` | Write a drum partial parameter for the selected key. |
| `"keyboard_note"` | Send a keyboard note with octave handling. |
| `"keyboard_octave"` | Change keyboard octave. |
| `"keyboard_velocity"` | Change keyboard velocity. |
| `"keyboard_modifier"` | Modifier used by keyboard controls. |
| `"keyboard_octave_or_velocity"` | Octave normally, velocity when the modifier is held. |
| `"scale_note"` | Play a note from the selected scale. |
| `"scale_octave"` | Change scale keyboard octave. |
| `"scale_control"` | Change scale keyboard MIDI channel, scale, key or velocity. |
| `"mc101_scene_select"` | Send Program Change to select an MC-101 scene and launch the matching M8 row. |
| `"mc101_scene_bank"` | Change the active MC-101 scene bank. |
| `"audio_routing_info"` | Display routing reference text. Sends no MIDI. |
| `"scatter_note"` | Hold an MC-101 scatter note while pressed. |

The script also contains handlers for a few older/unused types such as `note_pulse`, `m8_toggle_note`, `drum_pad_select` and `drum_pad_bank`. They are not used by the current `PRESETS` configuration.

## Standard CC mapping

Format:

```python
("cc", input_cc): named(("cc", output_channel, output_cc, "LBL"), "Long Name")
```

Example:

```python
("cc", 0): named(("cc", M8_CHANNEL, 0, "C00"), "CC 00")
```

This sends incoming `CC0` to outgoing `CC0` on `M8_CHANNEL`.

Example using a specific MIDI channel:

```python
("cc", 5): named(("cc", 4, 74, "CUT"), "Cutoff")
```

This sends incoming `CC5` to `CC74` on human MIDI Channel 5.

## Standard note mapping

Format:

```python
("note", input_note): named(("note", output_channel, output_note, "LBL"), "Long Name")
```

Example:

```python
("note", 3): named(("note", M8_CHANNEL, 15, "N15"), "Note 15")
```

This mirrors the physical input state:

```text
note_on in  -> note_on out
note_off in -> note_off out
```

## Toggle note mapping

Add `"toggle"` to make a button alternate between on and off.

```python
("note", 0): named(("note", M8_CHANNEL, 12, "toggle", "M01"), "Mute Track 1")
```

Behaviour:

```text
first press  -> note_on
second press -> note_off
```

This is used for M8 mute and solo controls in Preset 3, Scene 1.

## M8 button mapping

Format:

```python
("note", input_note): named(("m8_button", M8_CHANNEL, m8_button_note, "LBL"), "Long Name")
```

Example:

```python
("note", 16): named(("m8_button", M8_CHANNEL, 1, "SHI"), "Shift")
```

This holds the M8 button while the nanoKONTROL button is held.

This is used for M8 key combinations such as:

```text
Shift + Left
Edit + Right
```

## M8 navigation and key repeat

Preset selection selector buttons also act as M8 cursor buttons when they are not used in a preset combo.

```python
PRESET_SELECTOR_NOTES = {
    126: (6, "Up"),
    123: (7, "Down"),
    124: (4, "Left"),
    122: (5, "Right"),
}
```

The script sends repeated short note pulses while an arrow is held:

```python
ARROW_REPEAT_INITIAL_DELAY_SECONDS = 0.32
ARROW_REPEAT_INTERVAL_SECONDS = 0.08
```

Modifier buttons such as Shift, Edit and Option are held independently, allowing combinations such as Shift + Left.

## MIDI transport mapping

Example:

```python
("note", 0): named(("midi_transport", "stop", "Stop", "MST"), "MC-101 Stop")
("note", 9): named(("midi_transport", "start", "Start", "MPL"), "MC-101 Play")
```

Format:

```python
("midi_transport", "start" or "stop", display_text, short_name)
```

Important:

- MIDI Start and Stop are system realtime messages.
- They do not have a MIDI channel.
- The script sends them through `mc101TransportOUT`.
- Do not send Start/Stop through `nanoRouterOUT` if the goal is to isolate them from the M8.
- `amidiminder.rules` should connect `mc101TransportOUT` only to the MC-101.

## Track and partial selection

Track selection:

```python
("note", 0): named(("track_select", 1, "T01"), "Track")
```

Partial selection:

```python
("note", 9): named(("partial_select", 1, "P01"), "Partial")
```

These do not send notes to the MC-101. They update script state:

```python
active_track
active_partial
```

SysEx mappings then use the selected track and partial.

## SysEx mappings

SysEx mappings write MC-101 parameters directly.

Basic format:

```python
("cc", input_cc): named(("sysex", offset, max_value, "LBL", byte_size), "Long Name")
```

Example:

```python
("cc", 19): named(("sysex", 0x2032, 1023, "CUT", 4), "Cutoff")
```

### SysEx fields

| Field | Meaning |
|---|---|
| `offset` | Parameter offset, for example `0x2032`. |
| `max_value` | Maximum hardware value. Incoming `0-127` is scaled to this range. |
| `"LBL"` | Short HUD label. Keep it to about three characters. |
| `byte_size` | Data encoding size. Current examples use `1`, `2`, `4`, and `"nibbles2"`. |
| `value_list` | Optional list of allowed hardware values. |
| `value_map` | Optional dictionary that converts hardware values to HUD text. |
| `"toggle"` | Optional. Button press toggles between off/on state before writing. |

### Value scaling

Without a `value_list`, the script scales the incoming MIDI value from `0-127` to the hardware range.

With a `value_list`, the incoming MIDI value selects an item from the list.

Example:

```python
("cc", 9): named(
    ("sysex", 0x2001, 96, "CRS", 1, list(range(16, 113)), CRS_LABELS),
    "Coarse Tune"
)
```

The incoming CC selects a value from `16` to `112`, then displays it using `CRS_LABELS`.

### Value maps

Value maps translate raw values into readable HUD text.

Example:

```python
OSC_TYPE_LABELS = {0: "PCM", 1: "VA ", 2: "SYN", 3: "SAW", 4: "NOI"}
```

Mapping example:

```python
("cc", 0): named(("sysex", 0x3E00, 4, "OTY", 1, OSC_TYPE_LABELS), "Osc Type")
```

Instead of displaying `0`, `1`, `2`, etc., the HUD displays labels such as `PCM`, `VA`, or `SYN`.

### Multiple offsets

Some mappings write the same value to more than one offset.

Example:

```python
("cc", 2): ("conditional_sysex", ("cc", 0), {
    0: named(([0x201C, 0x2034], 2, "BNK", 4, [8, 10, 11], BANK_LABELS), "Wave Bank"),
})
```

This sends the same value to both `0x201C` and `0x2034`.

## Track-level SysEx

Use `sysex_track` for parameters that belong to the track rather than the active partial.

Example:

```python
("cc", 4): named(("sysex_track", 0x3D00, 4, "ST1", 1, ST1_LABELS), "Structure 1-2")
```

Format:

```python
("sysex_track", offset, max_value, "LBL", byte_size, optional_value_map)
```

## Dynamic SysEx by partial

Use `dynamic_sysex_track` when each partial needs a different address.

Example:

```python
("note", 13): named(
    ("dynamic_sysex_track", {1: 0x1002, 2: 0x100B, 3: 0x1014, 4: 0x101D}, 1, "PSW", 1, {0: "OFF", 1: "ON"}, "toggle"),
    "Partial Switch"
)
```

Format:

```python
("dynamic_sysex_track", {partial_number: offset}, max_value, "LBL", byte_size, value_map, "toggle")
```

## Conditional SysEx

Use `conditional_sysex` when one control changes meaning depending on another parameter.

Example:

```python
("cc", 1): ("conditional_sysex", ("cc", 0), {
    0: named((None, 0, "---", 1), "Unavailable"),
    1: named((0x3E01, 8, "WAV", 1, None, VA_WAVE_LABELS), "Wave Form"),
    2: named((None, 0, "---", 1), "Unavailable"),
    3: named((None, 0, "---", 1), "Unavailable"),
})
```

Format:

```python
("conditional_sysex", condition_key, {
    condition_value: target_mapping,
})
```

The `condition_key` is a mapping key such as:

```python
("cc", 0)
("note", 26)
```

The script reads the stored value for that condition and chooses the matching target.

### Placeholder mappings

If the offset is `None`, the mapping sends no SysEx.

```python
named((None, 0, "---", 1), "Unavailable")
```

This acts as a UI placeholder.

### Conditional value list

A target mapping can include a `value_list`.

```python
named(([0x201C, 0x2034], 2, "BNK", 4, [8, 10, 11], BANK_LABELS), "Wave Bank")
```

This converts a continuous `0-127` input into selected hardware values:

```python
[8, 10, 11]
```

### `bank_dependent`

`bank_dependent` is used when the valid target range depends on the current wave bank.

Example:

```python
("cc", 3): ("conditional_sysex", ("cc", 0), {
    0: ("bank_dependent", {
        8: named(([0x2020, 0x2038], 963, "WAV", 4), "Wave Number"),
        10: named(([0x2020, 0x2038], 257, "WAV", 4), "Wave Number"),
        11: named(([0x2020, 0x2038], 620, "WAV", 4), "Wave Number"),
    }),
})
```

The script checks the stored bank value and chooses the matching target.

## Conditional track-level SysEx

Use `conditional_sysex_track` when the conditional parameter is track-level.

Example:

```python
("cc", 5): ("conditional_sysex_track", ("cc", 4), {
    0: named((None, 0, "---", 1), "Unavailable"),
    2: named((0x3D02, 127, "RNG", 1), "Ring Level"),
    3: named((0x3D08, 10800, "MOD", 4), "Mod Depth"),
})
```

The logic is the same as `conditional_sysex`, but the state is read at track level.

## Cycling SysEx values

Use `cycle_sysex` when a button should cycle through values instead of using a CC value.

Example:

```python
("note", 44): named(
    ("cycle_sysex", 0x3011, 3, "1FM", 1, LFO_FADE_MODE_LABELS),
    "LFO1 Fade Mode"
)
```

Each press advances to the next value.

## Parameter mode toggle

`param_mode_toggle` changes an internal mode used by other conditional mappings.

Example:

```python
("note", 26): named(
    ("param_mode_toggle", ("note", 26), "AMP", "PIT", "TVA Env", "Pitch Env"),
    "Amp/Pitch Env Mode"
)
```

This toggles between two labels and two long names. Other mappings can then use `("note", 26)` as a condition.

## Drum editor

Preset 5 uses `build_drum_pad_scene(track, offset)`.

```python
1: {"name": "DRUM T1", "mappings": build_drum_pad_scene(1, 0)}
2: {"name": "DRUM T2", "mappings": build_drum_pad_scene(2, 18)}
3: {"name": "DRUM T3", "mappings": build_drum_pad_scene(3, 36)}
4: {"name": "DRUM T4", "mappings": build_drum_pad_scene(4, 54)}
```

### Drum pad selection

```python
("note", offset + index): named(
    ("drum_pad_key_select", track, key, drum_key_short_name(key)),
    drum_key_long_name(key),
)
```

This selects and plays a drum key.

### Drum partial SysEx

```python
("cc", cc(9)): named(("drum_sysex_partial", 0x0009, 127, "LEV", 1), "Level")
```

Format:

```python
("drum_sysex_partial", parameter_offset, max_value, "LBL", byte_size, optional_value_list, optional_value_map)
```

This targets the active drum key in the active drum track.

### Drum octave

```python
("note", offset + 8): named(("drum_scene_octave", track, 12, "OC+"), "Octave Up")
("note", offset + 17): named(("drum_scene_octave", track, -12, "OC-"), "Octave Down")
```

This shifts the drum key selection by octaves.

### Drum pad velocity

```python
("cc", cc(8)): named(("drum_pad_velocity", "VEL"), "Pad Velocity")
```

This changes the velocity used when playing drum pads from this scene.

## M8 keyboard helper

Preset 4 uses:

```python
build_m8_keyboard_scene(midi_channel, input_offset, velocity_cc)
```

Examples:

```python
1: {"name": "Keyboard CH 5", "mappings": build_m8_keyboard_scene(5, 0, 0)}
2: {"name": "Keyboard CH 6", "mappings": build_m8_keyboard_scene(6, 18, 18)}
3: {"name": "Keyboard CH 7", "mappings": build_m8_keyboard_scene(7, 36, 36)}
4: {"name": "Keyboard CH 8", "mappings": build_m8_keyboard_scene(8, 54, 54)}
```

The function accepts the human MIDI channel number and converts it internally to zero-based numbering.

The helper creates:

| Control | Behaviour |
|---|---|
| First 8 note buttons | Play notes `C-1` to `G-1` plus octave offset. |
| Button 9 | Octave up. |
| Next 8 note buttons | Play notes `G#-1` to `D#0` plus octave offset. |
| Button 18 | Octave down. |
| Velocity CC | Controls keyboard velocity. |
| Remaining CCs | Forward to M8 Channel 16. |

## Scale keyboard

Preset 2, Scene 3 uses:

```python
build_scale_keyboard_scene()
```

Default state:

```python
scale_keyboard_channel = 1     # human MIDI Channel 2
scale_keyboard_scale_index = 0 # Chromatic
scale_keyboard_key = 0         # C
scale_keyboard_velocity = 100
scale_keyboard_octave = 0
```

Controls:

| Control | Label | Behaviour |
|---|---|---|
| `CC41` | `MID` | MIDI Channel, human channels 1-12. |
| `CC42` | `SCA` | Scale selection. |
| `CC43` | `KEY` | Key selection from C to B. |
| `CC44` | `VEL` | Velocity from 0 to 127. |
| Notes `36-43` | dynamic note names | Top row, one octave higher. |
| Note `44` | `OC+` | Octave up. |
| Notes `45-52` | dynamic note names | Bottom row, one octave lower than the top row. |
| Note `53` | `OC-` | Octave down. |

Scales are defined in `SCALE_DEFINITIONS` as semitone intervals from the selected key.

Example:

```python
("Dorian", [0, 2, 3, 5, 7, 9, 10])
```

With key C, this produces:

```text
C, D, D#, F, G, A, A#
```

With key A, this produces:

```text
A, B, C, D, E, F#, G
```

## Audio routing info scene

Preset 2, Scene 4 is a HUD reference scene. It does not change JACK routing and does not send MIDI.

Options are defined in:

```python
AUDIO_ROUTING_OPTIONS = [
    ("R01", "R01: M8 > MC101"),
    ("R02", "R02: M8 > MC101 | PiS > MC101"),
    ("R03", "R03: MC101 > PiS | M8 > PiS"),
    ("R04", "R04: MC101 > M8 > PiS"),
    ("R05", "R05: PiS > MC101 > M8 > PiS"),
    ("R06", "R06: PiS > MC101 > PiS | PiS > M8 > PiS"),
    ("R07", "R07: PiS > M8 > MC101 > PiS"),
    ("R08", "R08: PiS to MC101 (L) | M8 > MC101 (R)"),
]
```

The helper maps notes `54-61` to the descriptions.

When pressed, the HUD shows only the selected description on line 1, for example:

```text
R01: M8 > MC101
```

## MC-101 scene selection

Preset 2 uses `mc101_scene_select` and `mc101_scene_bank`.

### Scene selection

```python
("note", 0): named(("mc101_scene_select", 0), "Scene")
```

Format:

```python
("mc101_scene_select", scene_index)
```

The Program Change number is calculated as:

```python
program = active_mc101_scene_bank * MC101_SCENES_PER_BANK + scene_index
```

With:

```python
MC101_SCENES_PER_BANK = 8
```

Examples:

```text
Bank 01, scene_index 0 -> PC 0
Bank 01, scene_index 7 -> PC 7
Bank 09, scene_index 0 -> PC 64
```

The script also launches the matching M8 song row.

### Bank selection

```python
("note", 9): named(("mc101_scene_bank", 0), "Bank 01")
```

Format:

```python
("mc101_scene_bank", bank_index)
```

`bank_index` is zero-based:

| Bank | `bank_index` |
|---:|---:|
| 01 | `0` |
| 02 | `1` |
| 09 | `8` |
| 16 | `15` |

## Preset selection controls

Preset selection uses two-button combos.

Prefix buttons:

```python
PRESET_PREFIX_PRIMARY = 127    # Selects Presets 1-4
PRESET_PREFIX_SECONDARY = 125  # Selects Presets 5-8
```

Selector buttons:

```python
PRESET_SELECTOR_NOTES = {
    126: (6, "Up"),
    123: (7, "Down"),
    124: (4, "Left"),
    122: (5, "Right"),
}
```

Combos:

| Combo | Result |
|---|---|
| `CC127 + CC126` | Preset 1 |
| `CC127 + CC123` | Preset 2 |
| `CC127 + CC124` | Preset 3 |
| `CC127 + CC122` | Preset 4 |
| `CC125 + CC126` | Preset 5 |
| `CC125 + CC123` | Preset 6 |
| `CC125 + CC124` | Preset 7 |
| `CC125 + CC122` | Preset 8 |

When used as a preset combo, the selector button does not also move the M8 cursor.

## Scatter mappings

Preset 7 uses `scatter_note`.

```python
("note", 0): named(("scatter_note", 12, 60, "P01"), "P01")
```

Format:

```python
("scatter_note", output_channel, note, short_name)
```

The script sends `note_on` while the pad is held and `note_off` when released.

## Keyboard mappings with velocity modifier

Preset 8 uses `keyboard_note`, `keyboard_modifier`, and `keyboard_octave_or_velocity`.

Example keyboard note:

```python
("note", 9): named(("keyboard_note", 0, 60, "C4"), "C4")
```

This sends `C4` on human MIDI Channel 1.

Velocity modifier:

```python
("note", 7): named(("keyboard_modifier", "VEL"), "Velocity +/-")
```

Combined octave and velocity control:

```python
("note", 8): named(("keyboard_octave_or_velocity", 0, 1, "OC+", 7, 10, "VL+", "Velocity Up"), "Octave Up")
("note", 17): named(("keyboard_octave_or_velocity", 0, -1, "OC-", 7, -10, "VL-", "Velocity Down"), "Octave Down")
```

Behaviour:

| Pressed alone | With velocity modifier held |
|---|---|
| octave up/down | velocity up/down |

## Practical examples

### Standard CC

Send incoming `CC0` to `CC10` on human MIDI Channel 15.

```python
("cc", 0): named(("cc", 14, 10, "VOL"), "Volume")
```

### Track selection

```python
("note", 0): named(("track_select", 1, "T01"), "Track")
```

### Partial selection

```python
("note", 9): named(("partial_select", 2, "P02"), "Partial")
```

### SysEx with readable values

```python
("cc", 0): named(("sysex", 0x3E00, 4, "OTY", 1, OSC_TYPE_LABELS), "Osc Type")
```

With:

```python
OSC_TYPE_LABELS = {0: "PCM", 1: "VA ", 2: "SYN", 3: "SAW", 4: "NOI"}
```

### Conditional SysEx with stereo offsets and hardware value jumps

```python
("cc", 2): ("conditional_sysex", ("cc", 0), {
    0: named(([0x201C, 0x2034], 2, "BNK", 4, [8, 10, 11], BANK_LABELS), "Wave Bank"),
    1: named((0x3E06, 127, "PW ", 1), "Pulse Width"),
})
```

With:

```python
BANK_LABELS = {8: "A", 10: "B", 11: "C"}
```

### Toggle note

```python
("note", 0): named(("note", M8_CHANNEL, 12, "toggle", "M01"), "Mute Track 1")
```

### Placeholder conditional option

```python
("cc", 1): ("conditional_sysex", ("cc", 0), {
    0: named((None, 0, "---", 1), "Unavailable"),
})
```

This displays `---` and sends no MIDI for that condition.

### Simple new scene

```python
5: {
    "name": "New Scene",
    "mappings": {
        ("cc", 72): named(("cc", M8_CHANNEL, 72, "C72"), "CC 72"),
        ("note", 72): named(("note", M8_CHANNEL, 28, "N28"), "Note 28"),
    }
}
```

Use the correct incoming CC/note range for the nanoKONTROL scene you are using.

## Safe editing rules

1. Use `named(...)` for new mappings.
2. Keep short labels to about three characters.
3. Remember that MIDI channels are zero-based in the script.
4. Use the correct input offset for the nanoKONTROL scene.
5. For SysEx mappings, verify the offset, range and byte size before testing.
6. Use `None` offsets for unavailable conditional options.
7. Use `value_list` when the hardware only accepts specific values.
8. Use `value_map` when raw values are not useful on the HUD.
9. Do not route MIDI Start/Stop through `nanoRouterOUT` if you want them isolated from the M8.
10. Test syntax before running the script.

## Test after editing

Run syntax validation:

```bash
python3 -m py_compile nanokontroller.py
```

Restart only the nanoKONTROL script:

```bash
pkill -f nanokontroller.py
cd /home/patch/mc101-pisound
python3 nanokontroller.py &
```

Check virtual MIDI ports:

```bash
aconnect -l
```

Expected virtual ports include:

```text
nanoRouterIN
nanoRouterOUT
mc101TransportOUT
```

Restart the full `m8c.sh` stack only when changes require the full routing or display stack to reload.