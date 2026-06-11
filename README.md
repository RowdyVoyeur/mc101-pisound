# Table of contents

- [About this project](#about-this-project)
- [Installation](#installation)

# About this project

## Overview

The mc101-pisound started as an idea for a portable device to add audio input to the Roland MC-101, using a Raspberry Pi 4 and Blokas Pisound. It has since grown into a broader performance and control environment for the MC-101.

Alongside audio routing between the MC-101, Pisound and M8C, it provides a HUD overlay and extended Korg nanoKONTROL mappings for scene launching, scale-based playing and editing of several MC-101 parameters of drum tracks and tone partials.

I will not cover the hardware requirements or build details here. However, I am happy to discuss ideas for this project. Meanwhile, you can see some pictures of the build [here](https://github.com/RowdyVoyeur/mc101-pisound/tree/d63daa4af89a75f2fd9006f445e54cdf5670e21d/images).

## Related resources

Since the Roland MC-101 is a central part of this project, you may find useful the [MC-101 tips and tricks website](https://sites.google.com/view/rolandmc101) I created, covering shortcuts, workflow notes and useful information for this groovebox.

If you also use a Dirtywave M8 or M8 Headless, I have put together a separate [M8 shortcuts, tips and tricks website](https://sites.google.com/view/m8tracker/) with additional notes for this tracker.

## Acknowledgements

This project would not exist without [Timothy Lamb](https://github.com/trash80)'s phenomenal invention, the [Dirtywave M8 Tracker](https://dirtywave.com/products/m8-tracker-model-02). Thank you for developing this fantastic product and for allowing the community to test and play it with the M8 Headless! The M8C is also an essential part of this puzzle. Thank you very much [laamaa](https://github.com/laamaa) for creating [this](https://github.com/laamaa/m8c).

## Compatibility

M8C is a client for [Dirtywave M8](https://dirtywave.com/) headless mode. While the original [application](https://github.com/laamaa/m8c) is cross-platform and can be built for Linux, Windows, macOS and Android, **this repository is optimized and tested exclusively for the Raspberry Pi 4 running 64-bit Bookworm** and is tailored for integration with the Roland MC-101 and Pisound.

It is recommended to use M8 Headless Firmware [6.2.1](https://github.com/Dirtywave/M8HeadlessFirmware/blob/main/Releases/M8_V6_2_1_HEADLESS.hex) or earlier. Newer versions, such as 6.5.1 G or 6.5.2 C are known to have MIDI sync issues with external gear when used with Pisound.

# Installation

## 1. Install and configure Patchbox OS

Download and install [Raspberry Pi Imager](https://www.raspberrypi.com/software/).

Download and unzip [Patchbox OS 2024-04-04 (Bookworm ARM64 Debian)](https://dl.blokas.io/patchbox-os/2024-04-04-Patchbox.zip).

Insert the SD card to your computer's SD card reader, launch Raspberry Pi Imager and follow the steps to flash Patchbox OS.

After flashing, safely remove the SD card, insert it into your Raspberry Pi and power it on.

Connect your computer to the same Network as the Raspberry Pi (using an ethernet cable to connect the RPi to the network), open a Terminal window and paste the following after boot is complete (default password: `blokaslabs`). All the steps in this tutorial are done via SSH:

```
ssh-keygen -R patchbox.local
ssh patch@patchbox.local
```

Follow the Setup Wizard instructions of the `Patchbox Configuration Utility`:

- If prompted, start by updating Patchbox OS;

- Then, for security reasons, change the default password;

- Use the following audio settings: `Sampling Rate` of 48,000 Hz, a `Buffer Size` of 64 and a `Period` of 4;

- Choose the boot environment `Console Autologin`;

- When prompted, configure Wi-Fi;

- Select `None: Default Patchbox OS Environment` to disable modules;

- Once the Setup Wizard is finished, type `patchbox` to enter the `Patchbox Configuration Utility` and stop Bluetooth, then disconnect Wi-Fi from default network and disable WiFi hotspot;

- Still in the `Patchbox Configuration Utility`, go to `kernel` and select `install-rt switch te current kernel to realtime one` to enable the RT kernel;

- Reboot with ```sudo reboot```.

## 2. Install dependencies

Install the libraries required by SLD3 and m8c:

```
sudo apt update
sudo apt install -y \
  build-essential cmake git pkg-config \
  libusb-1.0-0-dev \
  libudev-dev libdbus-1-dev \
  libegl1-mesa-dev libgles2-mesa-dev libdrm-dev libgbm-dev \
  libasound2-dev libjack-jackd2-dev libfreetype-dev
```

## 3. Download SDL3

Run the following to clone SDL3:

```
cd ~
# If the folder already exists, just enter it; otherwise, clone.
[ -d "sdl3" ] || git clone --depth 1 https://github.com/libsdl-org/SDL.git sdl3
cd sdl3
mkdir -p build && cd build
```

## 4. Configure SDL3

This command tells SDL3 to use the hardware acceleration of the Pi 4 and the low-latency audio of Patchbox.

```
cmake -DCMAKE_BUILD_TYPE=Release \
      -DSDL_UNIX_CONSOLE_BUILD=ON \
      -DSDL_VIDEO_DRIVER_KMSDRM=ON \
      -DSDL_X11=OFF \
      -DSDL_WAYLAND=OFF \
      -DSDL_OPENGL=OFF \
      -DSDL_OPENGLES=ON \
      -DSDL_ALSA=ON \
      -DSDL_JACK=ON \
      -DSDL_PULSEAUDIO=OFF ..
```

## 5. Compile and install SDL3

Run the following to compile and install SDL3:

```
make -j4
sudo make install
sudo ldconfig
```

## 6. Verification

Run this command to see if the system can find the SDL3:


```
pkg-config --modversion sdl3
```

## 7. Install SDL3_ttf (Font Support)

The M8 visual overlay requires the TrueType Font add-on to draw text. Run the following to download and compile it:

```
cd ~
git clone --depth 1 https://github.com/libsdl-org/SDL_ttf.git
cd SDL_ttf
mkdir -p build && cd build
cmake -DCMAKE_BUILD_TYPE=Release ..
make -j4
sudo make install
sudo ldconfig
```

## 8. Clone mc101-pisound repository

```
cd ~
git clone https://github.com/RowdyVoyeur/mc101-pisound.git
cd mc101-pisound
```

## 9. Run the build

```
make clean
make
```

## 10. Install the Patchbox Module

To run everything automatically and manage the audio/MIDI routing, install the custom Patchbox module included in this repository.

This installation script will automatically configure the required USB udev rules for the M8, so you do not need to set them manually.

Run the following command to install the module:

```
patchbox module install https://github.com/RowdyVoyeur/mc101-pisound
```

Once installed, reboot and then activate the module:

```
patchbox module activate mc101-pisound
```

## 11. Run the application

```
./m8c
```

## 12. Install nktrl_set

nanokontroller.nktrl_set must be installed into Korg nanoKONTROL to ensure the nanokontroller.py works

## Settings

### M8 Headless Settings
- Live Quantitize: 10 (16 Steps)

### M8 Headless MIDI Settings
- SYNC IN:  TRANSPORT
- SYNC OUT: CLOCK
- REC. NOTE CHAN: 14
- CC MAP CHAN: 16
- SONGROW CUE CH: 15

### Roland MC-101 System (MIDI) Settings
- Sync Src: USB
- Sync Out: ON
- SyncOut USB: ON
- RX SartStop: ON
- RX Start USB: ON
- Ctrl Ch: 13
- Ctrl Tx OUT: ON
- Ctrl Tx USB: ON
- Ctrl Rx: ON
- Rx Scatter: ON

### Roland MC-101 Tempo Settings
- MstrStepLen: 16 steps (same as on M8)

## Pisounr Audio Routing Modes

The Pisound button can cycle through several JACK audio-routing presets. Each mode clears the current JACK connections before applying the selected route.

1. **M8 to MC-101**
   Routes the M8 stereo output into the MC-101 USB audio input. If the MC-101 is not connected, the script falls back to Pisound standalone routing.

2. **M8 + Pisound In to MC-101**
   Routes both the M8 stereo output and the Pisound audio input into the MC-101 USB audio input. If the MC-101 is not connected, the script falls back to Pisound standalone routing.

3. **MC-101 + M8 to Pisound Out**
   Routes the MC-101 stereo output and the M8 stereo output to the Pisound audio outputs.

4. **MC-101 to M8 to Pisound Out**
   Routes the MC-101 stereo output into the M8 input, then routes the M8 stereo output to the Pisound audio outputs.

5. **Pisound In to MC-101 to M8 to Pisound Out**
   Routes the Pisound audio input into the MC-101, then routes the MC-101 output into the M8, and finally routes the M8 output to the Pisound audio outputs.

6. **Pisound In to MC-101 and M8 to Pisound Out**
   Routes the Pisound audio input into both the MC-101 and the M8, then routes both the MC-101 and M8 outputs to the Pisound audio outputs.

7. **Pisound In to M8 to MC-101 to Pisound Out**
   Routes the Pisound audio input into the M8, routes the M8 output into the MC-101, and routes the MC-101 output to the Pisound audio outputs.

8. **Split Input to MC-101**
   Routes the Pisound audio input to the left side of the MC-101 input and the M8 output to the right side of the MC-101 input. If the MC-101 is not connected, the script routes the M8 output to the Pisound audio outputs.

# nanoKONTROL Presets and Scenes

The Korg nanoKONTROL is organised into 8 presets, each containing one or more scenes.

## Preset 1: M8 & MC-101

* **Scene 1: Controller**
  M8 button controls and MC-101 transport controls.

## Preset 2: M8 & MC-101

* **Scene 1: Live (01-08)**
  MC-101 scene launch for banks 01-08, plus transport controls.

* **Scene 2: Live (09-16)**
  MC-101 scene launch for banks 09-16, plus transport controls.

* **Scene 3: Scale Keyboard**
  Scale-based keyboard control with selectable MIDI channel, scale, key, velocity, and octave.

* **Scene 4: Audio Routing**
  HUD reference for the available audio-routing options.

## Preset 3: M8

* **Scene 1: Mixer**
  M8 mute, solo, volume, and CC controls.

* **Scene 2: Performance 1**
  M8 CC performance controls.

* **Scene 3: Performance 2**
  M8 CC performance controls.

* **Scene 4: Performance 3**
  M8 CC performance controls.

## Preset 4: M8

* **Scene 1: Keyboard CH 5**
  M8 keyboard control on MIDI Channel 5.

* **Scene 2: Keyboard CH 6**
  M8 keyboard control on MIDI Channel 6.

* **Scene 3: Keyboard CH 7**
  M8 keyboard control on MIDI Channel 7.

* **Scene 4: Keyboard CH 8**
  M8 keyboard control on MIDI Channel 8.

## Preset 5: MC-101

* **Scene 1: DRUM T1**
  MC-101 drum editor for Track 1.

* **Scene 2: DRUM T2**
  MC-101 drum editor for Track 2.

* **Scene 3: DRUM T3**
  MC-101 drum editor for Track 3.

* **Scene 4: DRUM T4**
  MC-101 drum editor for Track 4.

## Preset 6: MC-101

* **Scene 1: Common & Oscillator**
  MC-101 partial common, oscillator, structure, tuning, pan, level, and partial controls.

* **Scene 2: Filter & Envelope**
  MC-101 filter, amp envelope, pitch envelope, and related partial controls.

* **Scene 3: LFO 1/2**
  MC-101 LFO 1 and LFO 2 controls.

* **Scene 4: Matrix 1-4**
  MC-101 modulation matrix controls for Matrix slots 1-4.

## Preset 7: MC-101

* **Scene 1: Scatter & CH 1**
  MC-101 scatter pads and MIDI Channel 1 CC controls.

* **Scene 2: Scatter & CH 2**
  MC-101 scatter pads and MIDI Channel 2 CC controls.

* **Scene 3: Scatter & CH 3**
  MC-101 scatter pads and MIDI Channel 3 CC controls.

* **Scene 4: Scatter & CH 4**
  MC-101 scatter pads and MIDI Channel 4 CC controls.

## Preset 8: MC-101

* **Scene 1: Keyboard CH 1**
  MC-101 keyboard and CC controls on MIDI Channel 1.

* **Scene 2: Keyboard CH 2**
  MC-101 keyboard and CC controls on MIDI Channel 2.

* **Scene 3: Keyboard CH 3**
  MC-101 keyboard and CC controls on MIDI Channel 3.

* **Scene 4: Keyboard CH 4**
  MC-101 keyboard and CC controls on MIDI Channel 4.


# `nanokontroller.py` Configuration Guide

This guide explains how the current `nanokontroller.py` is configured and how to edit it safely.

It is based on the script structure currently used in this repository. The extra cheat-sheet notes are included only where they match the current script.

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

---

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

---

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

---

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

---

## Current preset overview

| Preset | Name | Purpose |
|---:|---|---|
| 1 | `M8 & MC-101` | M8 buttons and MC-101 transport. |
| 2 | `M8 & MC-101` | MC-101 scene launch, scale keyboard, audio routing reference. |
| 3 | `M8` | M8 mixer, mute, solo and CC performance controls. |
| 4 | `M8` | M8 keyboard on MIDI Channels 5-8. |
| 5 | `MC-101` | Drum track editor for Tracks 1-4. |
| 6 | `MC-101` | Partial, oscillator, filter, envelope, LFO and matrix editing. |
| 7 | `MC-101` | Scatter pads and per-channel CC control. |
| 8 | `MC-101` | Keyboard and per-channel CC control. |

---

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

---

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

---

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

---

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

---

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

---

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

---

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

---

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

---

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

---

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

---

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

---

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

---

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

---

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

---

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

---

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

---

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

---

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

---

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

---

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

---

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

---

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

---

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

---

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

---

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

---

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

---

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

---

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

---

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

---

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

---

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