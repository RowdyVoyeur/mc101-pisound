#!/usr/bin/env python3
import sys
import time
import os
import mido
import threading

# --- CONFIGURATION ---
OVERLAY_PIPE = "/tmp/m8c_overlay"
MC101_TRANSPORT_CLIENT_NAME = "mc101TransportOUT"
MC101_TRANSPORT_PORT_NAME = "Out"
M8_CHANNEL = 15  # MIDI channel 16 in mido's zero-based numbering.
MC101_CONTROL_CHANNEL = 12  # MIDI channel 13 in mido's zero-based numbering.
MC101_SCENE_BANK_COUNT = 8
MC101_SCENES_PER_BANK = 8

# M8 song row cue configuration.
# M8 row cue notes are sent on MIDI channel 15, which is channel 14
# in mido's zero-based numbering. CC64 is kept above 64 so the
# selected row remains held instead of being released immediately.
M8_ROW_CUE_CHANNEL = 14
# Set to False to disable the CC64 hold/release messages while keeping the
# rest of the M8 row-cue behaviour intact. Set back to True to re-enable CC64.
M8_ROW_HOLD_ENABLED = True
M8_ROW_HOLD_CC = 64
M8_ROW_HOLD_VALUE = 127
M8_ROW_RELEASE_VALUE = 0
M8_ROW_NOTE_VELOCITY = 100

# M8 keyboard configuration for Preset 4.
M8_KEYBOARD_DEFAULT_VELOCITY = 100
M8_KEYBOARD_MIN_OCTAVE = 0
M8_KEYBOARD_MAX_OCTAVE = 9

# Presets
PRESET_1 = 1
PRESET_2 = 2
PRESET_3 = 3
PRESET_4 = 4
PRESET_5 = 5
PRESET_6 = 6
PRESET_7 = 7
PRESET_8 = 8

# Preset selection controls.
PRESET_PREFIX_PRIMARY = 127    # Follow with selector to choose Presets 1-4.
PRESET_PREFIX_SECONDARY = 125  # Follow with selector to choose Presets 5-8.
PRESET_PREFIX_TIMEOUT = 2.0

# These CCs select presets when combined with CC 127 or CC 125.
# When pressed by themselves, they send the M8 cursor notes on MIDI channel 16.
# MIDI note numbers use C-1 = 0.
PRESET_SELECTOR_NOTES = {
    126: (6, "Up"),     # F#-1
    123: (7, "Down"),   # G-1
    124: (4, "Left"),   # E-1
    122: (5, "Right"),  # F-1
}

SELECTOR_NOTE_PULSE_SECONDS = 0.025
# When an arrow is held, emulate the M8 hardware key repeat by sending
# repeated short note pulses while any modifier buttons, such as Shift, stay held.
ARROW_REPEAT_INITIAL_DELAY_SECONDS = 0.32
ARROW_REPEAT_INTERVAL_SECONDS = 0.08
LOOPBACK_IGNORE_SECONDS = 0.30

PRESET_COMBOS = {
    (PRESET_PREFIX_PRIMARY, 126): PRESET_1,
    (PRESET_PREFIX_PRIMARY, 123): PRESET_2,
    (PRESET_PREFIX_PRIMARY, 124): PRESET_3,
    (PRESET_PREFIX_PRIMARY, 122): PRESET_4,
    (PRESET_PREFIX_SECONDARY, 126): PRESET_5,
    (PRESET_PREFIX_SECONDARY, 123): PRESET_6,
    (PRESET_PREFIX_SECONDARY, 124): PRESET_7,
    (PRESET_PREFIX_SECONDARY, 122): PRESET_8,
}

# Global State
active_preset = PRESET_1
active_scene = 1
active_track = 1
active_partial = 1
active_pad = 1
active_pad_bank = 0
active_mc101_scene_bank = 0
active_m8_row_note = None

last_edited_label = None
last_edited_name = None
last_edited_val = None
last_edited_text = None
last_sysex_time = 0
last_interaction_time = 0
last_touched_type = "cc"
current_line1 = ""
preset_prefix = None
preset_prefix_time = 0
selector_last_fire = {}
ignored_output_notes = {}
output_notes_held = set()
arrow_repeat_stops = {}
arrow_repeat_lock = threading.Lock()

toggle_states = {}
param_states = {}
keyboard_octaves = {}
keyboard_velocity = M8_KEYBOARD_DEFAULT_VELOCITY
keyboard_notes_held = {}
active_drum_velocity = 100
drum_scene_octave_offsets = {1: 0, 2: 0, 3: 0, 4: 0}
drum_pad_notes_held = {}

# --- VALUE MAPS ---
OSC_TYPE_LABELS = {0: "PCM", 1: "VA ", 2: "SYN", 3: "SAW", 4: "NOI"}
BANK_LABELS = {8: "A", 10: "B", 11: "C"}
VA_WAVE_LABELS = {0: "SAW", 1: "SQR", 2: "TRI", 3: "SIN", 4: "RMP", 5: "JUN", 6: "TR2", 7: "TR3", 8: "SI2"}
PWD_LABELS = {i: f"+{i-64}" if i > 64 else str(i-64) for i in range(1, 128)}
SYN_WAVE_LABELS = {i: f"{i+1:02d}" for i in range(48)}
CRS_LABELS = {i: f"+{i-64}" if i > 64 else str(i-64) for i in range(16, 113)}
FIN_LABELS = {i: f"+{i-64}" if i > 64 else str(i-64) for i in range(14, 115)}
PAN_LABELS = {i: f"R{i-64}" if i > 64 else (f"L{64-i}" if i < 64 else "C") for i in range(128)}
DRUM_KEY_LABELS = {i: f"+{i-64}" if i > 64 else str(i-64) for i in range(40, 89)}
DRUM_FINE_LABELS = {i: f"+{i-64}" if i > 64 else str(i-64) for i in range(14, 115)}
DRUM_200_OFFSET_VALUES = list(range(28, 229))
DRUM_200_OFFSET_LABELS = {i: f"+{i-128}" if i > 128 else str(i-128) for i in range(28, 229)}
DRUM_OUTPUT_ASSIGN_LABELS = {
    0: "DRY", 1: "MFX", 2: "CP1", 3: "CP2",
    4: "CP3", 5: "CP4", 6: "CP5", 7: "CP6",
}
ST1_LABELS = {0: "OFF", 1: "SNC", 2: "RNG", 3: "XMD", 4: "XM2"}
TVF_TYP_LABELS = {0: "OFF", 1: "LPF", 2: "BPF", 3: "HPF", 4: "PKG", 5: "LP2", 6: "LP3"}
ENV_LABELS = {i: f"+{i-64}" if i > 64 else str(i-64) for i in range(1, 128)}
FILTER_TYPE_LABELS = {0: "TVF", 1: "VCF"}
VCF_TYPE_LABELS = {1: "FLAT", 2: "TYPE-JP", 3: "TYPE-M", 4: "TYPE-P"}
LFO_WAVE_LABELS = {
    0: "SIN", 1: "TRI", 2: "SAW-UP", 3: "SAW-DW", 4: "SQR",
    5: "RND", 6: "TRP", 7: "S&H", 8: "CHS", 9: "VSIN", 10: "STEP",
}
LFO_RATE_NOTE_LABELS = {
    0: "1/64T", 1: "1/64", 2: "1/32T", 3: "1/32", 4: "1/16T",
    5: "1/32.", 6: "1/16", 7: "1/8T", 8: "1/16.", 9: "1/8",
    10: "1/4T", 11: "1/8.", 12: "1/4", 13: "1/2T", 14: "1/4.",
    15: "1/2", 16: "1T", 17: "1/2.", 18: "1", 19: "2T",
    20: "1.", 21: "2", 22: "4",
}
LFO_FADE_MODE_LABELS = {0: "ON-IN", 1: "ON-OUT", 2: "OFF-IN", 3: "OFF-OUT"}

MATRIX_SOURCE_LABELS = {
    0: "OFF",
    1: "CC01",
    2: "CC02",
    3: "CC03",
    4: "CC04",
    5: "CC05",
    6: "CC06",
    7: "CC07",
    8: "CC08",
    9: "CC09",
    10: "CC10",
    11: "CC11",
    12: "CC12",
    13: "CC13",
    14: "CC14",
    15: "CC15",
    16: "CC16",
    17: "CC17",
    18: "CC18",
    19: "CC19",
    20: "CC20",
    21: "CC21",
    22: "CC22",
    23: "CC23",
    24: "CC24",
    25: "CC25",
    26: "CC26",
    27: "CC27",
    28: "CC28",
    29: "CC29",
    30: "CC30",
    31: "CC31",
    32: "CC33",
    33: "CC34",
    34: "CC35",
    35: "CC36",
    36: "CC37",
    37: "CC38",
    38: "CC39",
    39: "CC40",
    40: "CC41",
    41: "CC42",
    42: "CC43",
    43: "CC44",
    44: "CC45",
    45: "CC46",
    46: "CC47",
    47: "CC48",
    48: "CC49",
    49: "CC50",
    50: "CC51",
    51: "CC52",
    52: "CC53",
    53: "CC54",
    54: "CC55",
    55: "CC56",
    56: "CC57",
    57: "CC58",
    58: "CC59",
    59: "CC60",
    60: "CC61",
    61: "CC62",
    62: "CC63",
    63: "CC64",
    64: "CC65",
    65: "CC66",
    66: "CC67",
    67: "CC68",
    68: "CC69",
    69: "CC70",
    70: "CC71",
    71: "CC72",
    72: "CC73",
    73: "CC74",
    74: "CC75",
    75: "CC76",
    76: "CC77",
    77: "CC78",
    78: "CC79",
    79: "CC80",
    80: "CC81",
    81: "CC82",
    82: "CC83",
    83: "CC84",
    84: "CC85",
    85: "CC86",
    86: "CC87",
    87: "CC88",
    88: "CC89",
    89: "CC90",
    90: "CC91",
    91: "CC92",
    92: "CC93",
    93: "CC94",
    94: "CC95",
    95: "BEND",
    96: "AFT",
    97: "SYS-CTRL1",
    98: "SYS-CTRL2",
    99: "SYS-CTRL3",
    100: "SYS-CTRL4",
    101: "VELOCITY",
    102: "KEYFOLLOW",
    103: "TEMPO",
    104: "LFO1",
    105: "LFO2",
    106: "PIT-ENV",
    107: "TVF-ENV",
    108: "TVA-ENV",
}

MATRIX_DEST_LABELS = {
    0: "OFF",
    1: "PCH",
    2: "CUT",
    3: "RES",
    4: "LEV",
    5: "PAN",
    6: "DLY",
    7: "REV",
    8: "PIT-LFO1",
    9: "PIT-LFO2",
    10: "TVF-LFO1",
    11: "TVF-LFO2",
    12: "TVA-LFO1",
    13: "TVA-LFO2",
    14: "PAN-LFO1",
    15: "PAN-LFO2",
    16: "LFO1-RATE",
    17: "LFO2-RATE",
    18: "PIT-ATK",
    19: "PIT-DCY",
    20: "PIT-REL",
    21: "TVF-ATK",
    22: "TVF-DCY",
    23: "TVF-REL",
    24: "TVA-ATK",
    25: "TVA-DCY",
    26: "TVA-REL",
    27: "PMT",
    28: "FXM",
    29: "MFX-CTRL1",
    30: "MFX-CTRL2",
    31: "MFX-CTRL3",
    32: "MFX-CTRL4",
    33: "PW",
    34: "PWM",
    35: "FAT",
    36: "XMOD",
    37: "LFO1_STEP",
    38: "LFO2_STEP",
    39: "SSAW-DETN",
    40: "PIT_DEPTH",
    41: "TVF-DEPTH",
    42: "TVA-DEPTH",
    43: "XMOD2",
    44: "ATT",
    45: "RING-OSC1-LEV",
    46: "RING-OSC2-LEV",
    47: "XMOD-OSC1-LEV",
    48: "XMOD-OSC2-LEV",
}

MATRIX_SENS_VALUES = list(range(1, 128))
MATRIX_SENS_LABELS = {i: f"+{i-64}" if i > 64 else str(i-64) for i in range(1, 128)}

SLP_LABELS = {0: "-12", 1: "-18", 2: "-24"}
KF_LABELS = {i: f"+{i-1024}" if i > 1024 else str(i-1024) for i in range(824, 1225)}
PITCH_ENV_LEVEL_VALUES = list(range(513, 1536))
PITCH_ENV_LEVEL_LABELS = {i: f"+{i-1024}" if i > 1024 else str(i-1024) for i in range(513, 1536)}

PAD_NOTES = [37, 39, 42, 46, 49, 51, 54, 56, 36, 38, 41, 45, 48, 62, 63, 64]

# Mapping metadata helpers.
# Long, human-readable names live inside each mapping using named(...).
PARAMETER_NAME_KEY = "__parameter_name__"

def named(mapping, parameter_name):
    return (*mapping, {PARAMETER_NAME_KEY: parameter_name})

def is_parameter_name_meta(value):
    return isinstance(value, dict) and PARAMETER_NAME_KEY in value

def is_value_map_dict(value):
    return isinstance(value, dict) and not is_parameter_name_meta(value)

def strip_mapping_metadata(mapping):
    if not isinstance(mapping, tuple):
        return mapping
    return tuple(item for item in mapping if not is_parameter_name_meta(item))

def get_configured_parameter_name(mapping, fallback=None):
    if isinstance(mapping, tuple):
        for item in reversed(mapping):
            if is_parameter_name_meta(item):
                return item[PARAMETER_NAME_KEY]
    return fallback or "Parameter"

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

def midi_note_name(note):
    octave = (note // 12) - 1
    return f"{NOTE_NAMES[note % 12]}{octave}"

def keyboard_short_name(base_note):
    return NOTE_NAMES[base_note % 12]

def keyboard_output_note(channel, base_note):
    octave = keyboard_octaves.get(channel, 0)
    return max(0, min(127, base_note + (octave * 12)))

def set_keyboard_octave(channel, octave):
    keyboard_octaves[channel] = max(M8_KEYBOARD_MIN_OCTAVE, min(M8_KEYBOARD_MAX_OCTAVE, octave))
    return keyboard_octaves[channel]

def change_keyboard_octave(channel, direction):
    return set_keyboard_octave(channel, keyboard_octaves.get(channel, 0) + direction)

def set_keyboard_velocity(value):
    global keyboard_velocity
    keyboard_velocity = max(1, min(127, int(value)))
    return keyboard_velocity


def build_m8_cc_scene(start_cc):
    """Build one 18-control M8 CC passthrough scene.

    Incoming CC numbers are forwarded as the same CC numbers on MIDI Channel 16.
    """
    return {
        ("cc", cc_number): named(
            ("cc", M8_CHANNEL, cc_number, f"C{cc_number:02d}"[-3:]),
            f"CC{cc_number:02d}",
        )
        for cc_number in range(start_cc, start_cc + 18)
    }

def build_m8_keyboard_scene(midi_channel, input_offset, velocity_cc):
    """Build one 18-button keyboard scene for Preset 4.

    midi_channel is the human MIDI channel number. mido uses zero-based
    channel numbers internally.
    """
    channel = midi_channel - 1
    mappings = {}

    for index in range(8):
        mappings[("note", input_offset + index)] = named(
            ("keyboard_note", channel, index, keyboard_short_name(index)),
            midi_note_name(index),
        )

    mappings[("note", input_offset + 8)] = named(
        ("keyboard_octave", channel, 1, "OC+"),
        "Octave +",
    )

    for index in range(8):
        base_note = 8 + index
        mappings[("note", input_offset + 9 + index)] = named(
            ("keyboard_note", channel, base_note, keyboard_short_name(base_note)),
            midi_note_name(base_note),
        )

    mappings[("note", input_offset + 17)] = named(
        ("keyboard_octave", channel, -1, "OC-"),
        "Octave -",
    )

    mappings[("cc", velocity_cc)] = named(("keyboard_velocity", "VEL"), "Velocity")
    for cc_number in range(velocity_cc + 1, velocity_cc + 18):
        mappings[("cc", cc_number)] = named(
            ("cc", M8_CHANNEL, cc_number, f"C{cc_number:02d}"[-3:]),
            f"CC {cc_number:02d}",
        )

    return mappings

def drum_key_to_pad_number(key):
    """Return MC-101 physical pad number for the standard 16 pad keys."""
    try:
        return PAD_NOTES.index(int(key)) + 1
    except ValueError:
        return int(key)

def drum_key_is_editable(key):
    return 22 <= int(key) <= 108

def drum_key_short_name(key):
    key = int(key)
    if not drum_key_is_editable(key):
        return "---"
    pad_number = drum_key_to_pad_number(key)
    if 1 <= pad_number <= 16:
        return f"P{pad_number:02d}"
    return f"{key:03d}"

def drum_key_long_name(key):
    key = int(key)
    if not drum_key_is_editable(key):
        return "---"
    pad_number = drum_key_to_pad_number(key)
    if 1 <= pad_number <= 16:
        return f"Drum Pad {pad_number:02d}"
    return f"Drum Pad {key:03d}"

def clamp_midi_note(note):
    return max(0, min(127, int(note)))

def get_drum_scene_octave_offset(scene=None):
    scene_number = active_scene if scene is None else scene
    return drum_scene_octave_offsets.get(scene_number, 0)

def shifted_drum_key(base_key, scene=None):
    return int(base_key) + get_drum_scene_octave_offset(scene)

def get_drum_octave_label(scene=None):
    offset = get_drum_scene_octave_offset(scene)
    octave = offset // 12
    if octave > 0:
        return f"+{octave}"
    if octave < 0:
        return str(octave)
    return "0"

def build_drum_octave_line1(scene=None):
    scene_number = active_scene if scene is None else scene
    return f"MC-101 > DRUM TRACK {scene_number} > OCT {get_drum_octave_label(scene_number)}"

def build_drum_pad_scene(track, offset):
    """Build Preset 5 drum editor scene for one nanoKONTROL scene.

    Scene number selects the MC-101 track. The 16 note buttons play/select the
    standard MC-101 drum pads, while the selected key is stored as the actual
    drum key/pitch so the SysEx addresses work for the full Key#22..108 range.
    """
    mappings = {}

    first_row_keys = [37, 39, 42, 46, 49, 51, 54, 56]
    second_row_keys = [36, 38, 41, 45, 48, 62, 63, 64]

    for index, key in enumerate(first_row_keys):
        mappings[("note", offset + index)] = named(
            ("drum_pad_key_select", track, key, drum_key_short_name(key)),
            drum_key_long_name(key),
        )

    for index, key in enumerate(second_row_keys):
        mappings[("note", offset + 9 + index)] = named(
            ("drum_pad_key_select", track, key, drum_key_short_name(key)),
            drum_key_long_name(key),
        )

    cc = lambda base_cc: offset + base_cc

    # Drum Kit Partial offsets from the Roland/Fantom PCMR_PTL block.
    mappings[("cc", cc(0))] = named(("drum_sysex_partial", 0x000A, 127, "PAN", 1, None, PAN_LABELS), "Pan")
    mappings[("cc", cc(1))] = named(("drum_sysex_partial", 0x0011, 200, "CUT", "nibbles2", DRUM_200_OFFSET_VALUES, DRUM_200_OFFSET_LABELS), "Cutoff Offset")
    mappings[("cc", cc(2))] = named(("drum_sysex_partial", 0x0013, 200, "RES", "nibbles2", DRUM_200_OFFSET_VALUES, DRUM_200_OFFSET_LABELS), "Resonance Offset")
    mappings[("cc", cc(3))] = named(("drum_sysex_partial", 0x000F, 48, "KEY", 1, list(range(40, 89)), DRUM_KEY_LABELS), "Key Offset")
    mappings[("cc", cc(4))] = named(("drum_sysex_partial", 0x0010, 100, "FIN", 1, list(range(14, 115)), DRUM_FINE_LABELS), "Fine Tune Offset")
    mappings[("cc", cc(5))] = named(("drum_sysex_partial", 0x000E, 7, "OUT", 1, None, DRUM_OUTPUT_ASSIGN_LABELS), "Output Assign")
    mappings[("cc", cc(6))] = named(("drum_sysex_partial", 0x000D, 31, "MUT", 1), "Mute Group")
    mappings[("cc", cc(8))] = named(("drum_pad_velocity", "VEL"), "Pad Velocity")
    mappings[("cc", cc(9))] = named(("drum_sysex_partial", 0x0009, 127, "LEV", 1), "Level")
    mappings[("cc", cc(10))] = named(("drum_sysex_partial", 0x0015, 200, "ATK", "nibbles2", DRUM_200_OFFSET_VALUES, DRUM_200_OFFSET_LABELS), "Attack Offset")
    mappings[("cc", cc(11))] = named(("drum_sysex_partial", 0x0017, 200, "DCY", "nibbles2", DRUM_200_OFFSET_VALUES, DRUM_200_OFFSET_LABELS), "Decay Offset")
    mappings[("cc", cc(12))] = named(("drum_sysex_partial", 0x0019, 200, "REL", "nibbles2", DRUM_200_OFFSET_VALUES, DRUM_200_OFFSET_LABELS), "Release Offset")
    mappings[("cc", cc(13))] = named(("drum_sysex_partial", 0x000B, 127, "CHO", 1), "Chorus/Delay Send")
    mappings[("cc", cc(14))] = named(("drum_sysex_partial", 0x000C, 127, "REV", 1), "Reverb Send")

    # Octave navigation for the 16 pad-select/play notes in this scene.
    # Scene 1: G#-1 up / F0 down
    # Scene 2: D1 up / B1 down
    # Scene 3: G#2 up / F3 down
    # Scene 4: D4 up / B4 down
    mappings[("note", offset + 8)] = named(("drum_scene_octave", track, 12, "OC+"), "Octave Up")
    mappings[("note", offset + 17)] = named(("drum_scene_octave", track, -12, "OC-"), "Octave Down")

    return mappings

PRESETS = {
    PRESET_1: {
        "name": "M8 & MC-101",
        "context": "m8",
        "display_values": False,
        "scenes": {
            1: {
                "name": "Controller",
                "mappings": {

                    # Requested Preset 1 M8 button mappings. MIDI note numbers use C-1 = 0.
                    # Physical G-1/G#-1/E0/F0 send short M8 button pulses.
                    ("note", 7): named(("m8_button", M8_CHANNEL, 3, "OPT"), "Option"),
                    ("note", 8): named(("m8_button", M8_CHANNEL, 2, "EDI"), "Edit"),
                    ("note", 16): named(("m8_button", M8_CHANNEL, 1, "SHI"), "Shift"),
                    ("note", 17): named(("m8_button", M8_CHANNEL, 0, "PLA"), "Play"),

                    # MC-101 transport controls.
                    # MIDI note numbers use C-1 = 0:
                    #   C-1 = 0  -> MIDI Stop
                    #   A-1  = 9 -> MIDI Start
                    ("note", 0): named(("midi_transport", "stop", "Stop", "MST"), "MC-101 Stop"),
                    ("note", 9): named(("midi_transport", "start", "Start", "MPL"), "MC-101 Play"),
                }
            }
        }
    },
    PRESET_2: {
        "name": "M8 & MC-101",
        "context": "none",
        "display_values": True,
        "scenes": {
            1: {
                "name": "Live (01-08)",
                "default_scene_bank": 0,
                "mappings": {
                    # Scene trigge)r buttons. The selected bank decides which
                    # Program Change range these notes send:
                    #   Bank 01 -> PC 0-7, Bank 02 -> PC 8-15, etc.
                    ("note", 0): named(("mc101_scene_select", 0), "Scene"),
                    ("note", 1): named(("mc101_scene_select", 1), "Scene"),
                    ("note", 2): named(("mc101_scene_select", 2), "Scene"),
                    ("note", 3): named(("mc101_scene_select", 3), "Scene"),
                    ("note", 4): named(("mc101_scene_select", 4), "Scene"),
                    ("note", 5): named(("mc101_scene_select", 5), "Scene"),
                    ("note", 6): named(("mc101_scene_select", 6), "Scene"),
                    ("note", 7): named(("mc101_scene_select", 7), "Scene"),

                    # Bank selectors. A-1 selects Bank 01,
                    # A#-1 selects Bank 02, through E0 = Bank 08.
                    ("note", 9): named(("mc101_scene_bank", 0), "Bank 01"),
                    ("note", 10): named(("mc101_scene_bank", 1), "Bank 02"),
                    ("note", 11): named(("mc101_scene_bank", 2), "Bank 03"),
                    ("note", 12): named(("mc101_scene_bank", 3), "Bank 04"),
                    ("note", 13): named(("mc101_scene_bank", 4), "Bank 05"),
                    ("note", 14): named(("mc101_scene_bank", 5), "Bank 06"),
                    ("note", 15): named(("mc101_scene_bank", 6), "Bank 07"),
                    ("note", 16): named(("mc101_scene_bank", 7), "Bank 08"),

                    # MC-101 transport controls.
                    # MIDI note numbers use C-1 = 0:
                    #   G#-1 = 8  -> MIDI Stop
                    #   F0  = 17 -> MIDI Start
                    ("note", 8): named(("midi_transport", "stop", "Stop", "STP"), "Stop"),
                    ("note", 17): named(("midi_transport", "start", "Start", "PLA"), "Play"),
                }
            },
            2: {
                "name": "Live (09-16)",
                "default_scene_bank": 8,
                "mappings": {
                    # Same layout as Scene 1, but offset to nanoKONTROL Scene 2
                    # note numbers and defaulting to Bank 09.
                    #   Bank 09 -> PC 64-71, Bank 10 -> PC 72-79, etc.
                    ("note", 18): named(("mc101_scene_select", 0), "Scene"),
                    ("note", 19): named(("mc101_scene_select", 1), "Scene"),
                    ("note", 20): named(("mc101_scene_select", 2), "Scene"),
                    ("note", 21): named(("mc101_scene_select", 3), "Scene"),
                    ("note", 22): named(("mc101_scene_select", 4), "Scene"),
                    ("note", 23): named(("mc101_scene_select", 5), "Scene"),
                    ("note", 24): named(("mc101_scene_select", 6), "Scene"),
                    ("note", 25): named(("mc101_scene_select", 7), "Scene"),

                    # Bank selectors. A-1 selects Bank 09,
                    # A#-1 selects Bank 10, through E0 = Bank 16.
                    ("note", 27): named(("mc101_scene_bank", 8), "Bank 09"),
                    ("note", 28): named(("mc101_scene_bank", 9), "Bank 10"),
                    ("note", 29): named(("mc101_scene_bank", 10), "Bank 11"),
                    ("note", 30): named(("mc101_scene_bank", 11), "Bank 12"),
                    ("note", 31): named(("mc101_scene_bank", 12), "Bank 13"),
                    ("note", 32): named(("mc101_scene_bank", 13), "Bank 14"),
                    ("note", 33): named(("mc101_scene_bank", 14), "Bank 15"),
                    ("note", 34): named(("mc101_scene_bank", 15), "Bank 16"),

                    # MC-101 transport controls.
                    # MIDI note numbers use C-1 = 18 in nanoKONTROL Scene 2:
                    #   G#-1 = 26 -> MIDI Stop
                    #   F0  = 35 -> MIDI Start
                    ("note", 26): named(("midi_transport", "stop", "Stop", "STP"), "Stop"),
                    ("note", 35): named(("midi_transport", "start", "Start", "PLA"), "Play"),
                }
            }
        }
    },
    PRESET_3: {
        "name": "M8",
        "context": "none",
        "display_values": False,
        "scenes": {
            1: {
                "name": "Mixer",
                "mappings": {

                    # M8 track mute controls. MIDI note numbers use C-1 = 0.
                    # Physical C-1 to G-1 send C0 to G0 on MIDI Channel 16.
                    ("note", 0): named(("note", M8_CHANNEL, 12, "toggle", "M01"), "Mute Track 1"),
                    ("note", 1): named(("note", M8_CHANNEL, 13, "toggle", "M02"), "Mute Track 2"),
                    ("note", 2): named(("note", M8_CHANNEL, 14, "toggle", "M03"), "Mute Track 3"),
                    ("note", 3): named(("note", M8_CHANNEL, 15, "toggle", "M04"), "Mute Track 4"),
                    ("note", 4): named(("note", M8_CHANNEL, 16, "toggle", "M05"), "Mute Track 5"),
                    ("note", 5): named(("note", M8_CHANNEL, 17, "toggle", "M06"), "Mute Track 6"),
                    ("note", 6): named(("note", M8_CHANNEL, 18, "toggle", "M07"), "Mute Track 7"),
                    ("note", 7): named(("note", M8_CHANNEL, 19, "toggle", "M08"), "Mute Track 8"),

                    # M8 track solo controls.
                    # Physical A-1 to E0 send G#0 to D#1 on MIDI Channel 16.
                    ("note", 9): named(("note", M8_CHANNEL, 20, "toggle", "S01"), "Solo Track 1"),
                    ("note", 10): named(("note", M8_CHANNEL, 21, "toggle", "S02"), "Solo Track 2"),
                    ("note", 11): named(("note", M8_CHANNEL, 22, "toggle", "S03"), "Solo Track 3"),
                    ("note", 12): named(("note", M8_CHANNEL, 23, "toggle", "S04"), "Solo Track 4"),
                    ("note", 13): named(("note", M8_CHANNEL, 24, "toggle", "S05"), "Solo Track 5"),
                    ("note", 14): named(("note", M8_CHANNEL, 25, "toggle", "S06"), "Solo Track 6"),
                    ("note", 15): named(("note", M8_CHANNEL, 26, "toggle", "S07"), "Solo Track 7"),
                    ("note", 16): named(("note", M8_CHANNEL, 27, "toggle", "S08"), "Solo Track 8"),

                    # M8 CC controls on MIDI Channel 16.
                    ("cc", 0): named(("cc", M8_CHANNEL, 0, "C00"), "CC 00"),
                    ("cc", 1): named(("cc", M8_CHANNEL, 1, "C01"), "CC 01"),
                    ("cc", 2): named(("cc", M8_CHANNEL, 2, "C02"), "CC 02"),
                    ("cc", 3): named(("cc", M8_CHANNEL, 3, "C03"), "CC 03"),
                    ("cc", 4): named(("cc", M8_CHANNEL, 4, "C04"), "CC 04"),
                    ("cc", 5): named(("cc", M8_CHANNEL, 5, "C05"), "CC 05"),
                    ("cc", 6): named(("cc", M8_CHANNEL, 6, "C06"), "CC 06"),
                    ("cc", 7): named(("cc", M8_CHANNEL, 7, "C07"), "CC 07"),
                    ("cc", 8): named(("cc", M8_CHANNEL, 8, "C08"), "CC 08"),
                    ("cc", 9): named(("cc", M8_CHANNEL, 9, "V01"), "Volume Track 1"),
                    ("cc", 10): named(("cc", M8_CHANNEL, 10, "V02"), "Volume Track 2"),
                    ("cc", 11): named(("cc", M8_CHANNEL, 11, "V03"), "Volume Track 3"),
                    ("cc", 12): named(("cc", M8_CHANNEL, 12, "V04"), "Volume Track 4"),
                    ("cc", 13): named(("cc", M8_CHANNEL, 13, "V05"), "Volume Track 5"),
                    ("cc", 14): named(("cc", M8_CHANNEL, 14, "V06"), "Volume Track 6"),
                    ("cc", 15): named(("cc", M8_CHANNEL, 15, "V07"), "Volume Track 7"),
                    ("cc", 16): named(("cc", M8_CHANNEL, 16, "V08"), "Volume Track 8"),
                    ("cc", 17): named(("cc", M8_CHANNEL, 17, "V09"), "Volume Track 9"),

                }
            },
            2: {"name": "PERFORMANCE 1", "mappings": build_m8_cc_scene(18)},
            3: {"name": "PERFORMANCE 2", "mappings": build_m8_cc_scene(36)},
            4: {"name": "PERFORMANCE 3", "mappings": build_m8_cc_scene(54)},
        }
    },
    PRESET_4: {
        "name": "M8",
        "context": "none",
        "display_values": False,
        "scenes": {
            1: {"name": "Keyboard CH 5", "mappings": build_m8_keyboard_scene(5, 0, 0)},
            2: {"name": "Keyboard CH 6", "mappings": build_m8_keyboard_scene(6, 18, 18)},
            3: {"name": "Keyboard CH 7", "mappings": build_m8_keyboard_scene(7, 36, 36)},
            4: {"name": "Keyboard CH 8", "mappings": build_m8_keyboard_scene(8, 54, 54)},
        }
    },
    PRESET_5: {
        "name": "MC-101",
        "context": "drum",
        "default_track": 1,
        "display_values": True,
        "scenes": {
            1: {"name": "DRUM T1", "mappings": build_drum_pad_scene(1, 0)},
            2: {"name": "DRUM T2", "mappings": build_drum_pad_scene(2, 18)},
            3: {"name": "DRUM T3", "mappings": build_drum_pad_scene(3, 36)},
            4: {"name": "DRUM T4", "mappings": build_drum_pad_scene(4, 54)},
        }
    },
    PRESET_6: {
        "name": "MC-101",
        "context": "partial",
        "default_track": 1,
        "display_values": True,
        "scenes": {
            1: {
                "name": "Common & Oscillator",
                "mappings": {
                    ("cc", 0): named(("sysex", 0x3E00, 4, "OTY", 1, OSC_TYPE_LABELS), "Osc Type"),
                    ("cc", 1): ("conditional_sysex", ("cc", 0), {
                        0: named((None, 0, "---", 1), "Unavailable"),
                        1: named((0x3E01, 8, "WAV", 1, None, VA_WAVE_LABELS), "Wave Form"),
                        2: named((None, 0, "---", 1), "Unavailable"),
                        3: named((None, 0, "---", 1), "Unavailable")
                    }),
                    ("cc", 2): ("conditional_sysex", ("cc", 0), {
                        0: named(([0x201C, 0x2034], 2, "BNK", 4, [8, 10, 11], BANK_LABELS), "Wave Bank"),
                        1: named((0x3E06, 127, "PW ", 1), "Pulse Width"),
                        2: named((0x3E02, 47, "WAV", 4, None, SYN_WAVE_LABELS), "Sync Wave"),
                        3: named((0x3E08, 127, "DET", 1), "Detune")
                    }),
                    ("cc", 3): ("conditional_sysex", ("cc", 0), {
                        0: ("bank_dependent", {
                            8: named(([0x2020, 0x2038], 963, "WAV", 4), "Wave Number"),
                            10: named(([0x2020, 0x2038], 257, "WAV", 4), "Wave Number"),
                            11: named(([0x2020, 0x2038], 620, "WAV", 4), "Wave Number")
                        }),
                        1: named((0x3E07, 126, "PWD", 1, list(range(1, 128)), PWD_LABELS), "Pulse Width Depth"),
                        2: named((None, 0, "---", 1), "Unavailable"),
                        3: named((None, 0, "---", 1), "Unavailable")
                    }),
                    ("cc", 4): named(("sysex_track", 0x3D00, 4, "ST1", 1, ST1_LABELS), "Structure 1-2"),
                    ("cc", 5): ("conditional_sysex_track", ("cc", 4), {
                        0: named((None, 0, "---", 1), "Unavailable"),
                        1: named((None, 0, "---", 1), "Unavailable"),
                        2: named((0x3D02, 127, "RNG", 1), "Ring Level"),
                        3: named((0x3D08, 10800, "MOD", 4), "Mod Depth"),
                        4: named((0x3D15, 127, "MOD", 1), "Md Depth")
                    }),
                    ("cc", 13): ("conditional_sysex_track", ("cc", 4), {
                        0: named((None, 0, "---", 1), "Unavailable"),
                        1: named((None, 0, "---", 1), "Unavailable"),
                        2: named((0x3D04, 127, "LV1", 1), "Osc1 Level"),
                        3: named((0x3D10, 127, "LV1", 1), "Osc1 Level"),
                        4: named((0x3D10, 127, "LV1", 1), "Osc1 Level")
                    }),
                    ("cc", 14): ("conditional_sysex_track", ("cc", 4), {
                        0: named((None, 0, "---", 1), "Unavailable"),
                        1: named((None, 0, "---", 1), "Unavailable"),
                        2: named((0x3D05, 127, "LV2", 1), "Osc2 Level"),
                        3: named((0x3D11, 127, "LV2", 1), "Osc2 Level"),
                        4: named((0x3D11, 127, "LV2", 1), "Osc2 Level")
                    }),
                    ("cc", 6): named(("sysex_track", 0x3D01, 4, "ST3", 1, ST1_LABELS), "Structure 3-4"),
                    ("cc", 7): ("conditional_sysex_track", ("cc", 6), {
                        0: named((None, 0, "---", 1), "Unavailable"),
                        1: named((None, 0, "---", 1), "Unavailable"),
                        2: named((0x3D03, 127, "RNG", 1), "Ring Level"),
                        3: named((0x3D0C, 10800, "MOD", 4), "Mod Depth"),
                        4: named((0x3D16, 127, "MOD", 1), "Mod Depth")
                    }),
                    ("cc", 15): ("conditional_sysex_track", ("cc", 6), {
                        0: named((None, 0, "---", 1), "Unavailable"),
                        1: named((None, 0, "---", 1), "Unavailable"),
                        2: named((0x3D06, 127, "LV3", 1), "Osc3 Level"),
                        3: named((0x3D12, 127, "LV3", 1), "Osc3 Level"),
                        4: named((0x3D12, 127, "LV3", 1), "Osc3 Level")
                    }),
                    ("cc", 16): ("conditional_sysex_track", ("cc", 6), {
                        0: named((None, 0, "---", 1), "Unavailable"),
                        1: named((None, 0, "---", 1), "Unavailable"),
                        2: named((0x3D07, 127, "LV4", 1), "Osc4 Level"),
                        3: named((0x3D13, 127, "LV4", 1), "Osc4 Level"),
                        4: named((0x3D13, 127, "LV4", 1), "Osc4 Level")
                    }),
                    ("cc", 8): named(("sysex_track", 0x001C, 127, "ANL", 1), "Analog Feel"),
                    ("cc", 17): named(("sysex_track", 0x0024, 1023, "TIM", 4), "Portamento Time"),
                    ("note", 8): named(("sysex_track", 0x001D, 1, "M/P", 1, {0: "MNO", 1: "PLY"}, "toggle"), "Mono/Poly"),
                    ("note", 16): named(("sysex_track", 0x0021, 1, "PRM", 1, {0: "NRM", 1: "LGT"}, "toggle"), "Portamento Mode"),
                    ("note", 17): named(("sysex_track", 0x0020, 1, "PRT", 1, {0: "OFF", 1: "ON"}, "toggle"), "Portamento Switch"),
                    ("note", 7): named(("sysex_track", 0x3C00, 1, "UNS", 1, {0: "OFF", 1: "ON"}, "toggle"), "Unison"),
                    ("cc", 9): named(("sysex", 0x2001, 96, "CRS", 1, list(range(16, 113)), CRS_LABELS), "Coarse Tune"),
                    ("cc", 10): named(("sysex", 0x2002, 100, "FIN", 1, list(range(14, 115)), FIN_LABELS), "Fine Tune"),
                    ("cc", 11): named(("sysex", 0x2000, 127, "LEV", 1), "Level"),
                    ("cc", 12): named(("sysex", 0x2007, 127, "PAN", 1, None, PAN_LABELS), "Pan"),
                    ("note", 0): named(("track_select", 1, "T01"), "Track"),
                    ("note", 1): named(("track_select", 2, "T02"), "Track"),
                    ("note", 2): named(("track_select", 3, "T03"), "Track"),
                    ("note", 3): named(("track_select", 4, "T04"), "Track"),
                    ("note", 4): named(("conditional_sysex_track", ("cc", 4), {
                        0: named((None, 0, "---", 1), "Unavailable"),
                        1: named((None, 0, "---", 1), "Unavailable"),
                        2: named((None, 0, "---", 1), "Unavailable"),
                        3: named((0x3D14, 1, "LCK", 1, None, {0: "OFF", 1: "ON"}), "Structure Lock"),
                        4: named((0x3D14, 1, "LCK", 1, None, {0: "OFF", 1: "ON"}), "Structure Lock"),
                    }, "toggle"), "Structure Lock"),
                    ("note", 6): named(("conditional_sysex_track", ("cc", 6), {
                        0: named((None, 0, "---", 1), "Unavailable"),
                        1: named((None, 0, "---", 1), "Unavailable"),
                        2: named((None, 0, "---", 1), "Unavailable"),
                        3: named((0x3D14, 1, "LCK", 1, None, {0: "OFF", 1: "ON"}), "Structure Lock"),
                        4: named((0x3D14, 1, "LCK", 1, None, {0: "OFF", 1: "ON"}), "Structure Lock"),
                    }, "toggle"), "Structure Lock"),
                    ("note", 9): named(("partial_select", 1, "P01"), "Partial"),
                    ("note", 10): named(("partial_select", 2, "P02"), "Partial"),
                    ("note", 11): named(("partial_select", 3, "P03"), "Partial"),
                    ("note", 12): named(("partial_select", 4, "P04"), "Partial"),
                    ("note", 13): named(("dynamic_sysex_track", {1: 0x1002, 2: 0x100B, 3: 0x1014, 4: 0x101D}, 1, "PSW", 1, {0: "OFF", 1: "ON"}, "toggle"), "Partial Switch"),
                }
            },
            2: {
                "name": "Filter & Envelope",
                "mappings": {
                    ("cc", 18): ("conditional_sysex", ("cc", 22), {
                        0: named((0x2031, 6, "TYP", 1, TVF_TYP_LABELS), "TVF Filter Type"),
                        1: named((0x3E12, 4, "FTY", 1, [1, 2, 3, 4], VCF_TYPE_LABELS), "VCF Type"),
                    }),
                    ("cc", 19): named(("sysex", 0x2032, 1023, "CUT", 4), "Cutoff"),
                    ("cc", 20): named(("sysex", 0x203D, 1023, "RES", 4), "Resonance"),
                    ("cc", 21): named(("sysex", 0x2800, 126, "ENV", 1, list(range(1, 128)), ENV_LABELS), "Filter Envelope"),
                    ("cc", 22): named(("sysex", 0x3E0E, 1, "FLT", 1, FILTER_TYPE_LABELS), "Filter Model"),
                    ("cc", 23): named(("sysex", 0x2036, 400, "KF ", 4, list(range(824, 1225)), KF_LABELS), "Key Follow"),
                    ("cc", 24): named(("sysex", 0x3E0F, 2, "SLP", 1, SLP_LABELS), "Slope"),
                    ("cc", 25): ("conditional_sysex", ("cc", 22), {
                        0: named((None, 0, "---", 1), "Unavailable"),
                        1: named((0x3E0A, 1023, "HPF", 4), "High-pass Cutoff")
                    }),
                    ("cc", 26): named(("sysex", 0x3E11, 127, "FAT", 1), "Fat"),
                    ("cc", 27): named(("sysex", 0x2808, 1023, "F-A", 4), "TVF T1 Attack"),
                    ("cc", 28): named(("sysex", 0x2810, 1023, "F-D", 4), "TVF T3 Deacy"),
                    ("cc", 29): named(("sysex", 0x2824, 1023, "F-S", 4), "TVF L3 Sustain"),
                    ("cc", 30): named(("sysex", 0x2814, 1023, "F-R", 4), "TVF T4 Release"),
                    ("cc", 31): ("conditional_sysex", ("note", 26), {
                        0: named((0x2C04, 1023, "A-A", 4), "TVA T1 Attack"),
                        1: named((0x2400, 200, "PED", "nibbles2", list(range(28, 229)), DRUM_200_OFFSET_LABELS), "Pitch Env Depth"),
                    }),
                    ("cc", 32): ("conditional_sysex", ("note", 26), {
                        0: named((0x2C0C, 1023, "A-D", 4), "TVA T3 Deacy"),
                        1: named((0x2408, 1023, "P-A", 4), "Pitch Env Attack"),
                    }),
                    ("cc", 33): ("conditional_sysex", ("note", 26), {
                        0: named((0x2C1C, 1023, "A-S", 4), "TVA L3 Sustain"),
                        1: named((0x2424, 1022, "P-S", 4, PITCH_ENV_LEVEL_VALUES, PITCH_ENV_LEVEL_LABELS), "Pitch Env Sustain"),
                    }),
                    ("cc", 34): ("conditional_sysex", ("note", 26), {
                        0: named((0x2C10, 1023, "A-R", 4), "TVA T4 Release"),
                        1: named((0x2410, 1023, "P-D", 4), "Pitch Env Deacy"),
                    }),
                    ("note", 18): named(("track_select", 1, "T01"), "Track"),
                    ("note", 19): named(("track_select", 2, "T02"), "Track"),
                    ("note", 20): named(("track_select", 3, "T03"), "Track"),
                    ("note", 21): named(("track_select", 4, "T04"), "Track"),
                    ("note", 26): named(("param_mode_toggle", ("note", 26), "AMP", "PIT", "TVA Env", "Pitch Env"), "Amp/Pitch Env Mode"),
                    ("note", 27): named(("partial_select", 1, "P01"), "Partial"),
                    ("note", 28): named(("partial_select", 2, "P02"), "Partial"),
                    ("note", 29): named(("partial_select", 3, "P03"), "Partial"),
                    ("note", 30): named(("partial_select", 4, "P04"), "Partial"),
                    ("note", 31): named(("dynamic_sysex_track", {1: 0x1002, 2: 0x100B, 3: 0x1014, 4: 0x101D}, 1, "PSW", 1, {0: "OFF", 1: "ON"}, "toggle"), "Partial Switch"),
                    ("note", 35): named(("sysex", 0x3E10, 1, "ADS", 1, {0: "OFF", 1: "ON"}, "toggle"), "ADSREnv Switch"),
                }
            },
            3: {
                "name": "LFO 1/2",
                "mappings": {
                    ("note", 36): named(("track_select", 1, "T01"), "Track"),
                    ("note", 37): named(("track_select", 2, "T02"), "Track"),
                    ("note", 38): named(("track_select", 3, "T03"), "Track"),
                    ("note", 39): named(("track_select", 4, "T04"), "Track"),
                    ("cc", 36): named(("sysex", 0x3000, 10, "1WT", 1, LFO_WAVE_LABELS), "LFO1 Wave Type"),
                    ("cc", 37): ("conditional_sysex", ("note", 42), {
                        0: named((0x3004, 1023, "1RT", 4), "LFO1 Rate"),
                        1: named((0x3002, 22, "1RN", 1, list(reversed(range(23))), LFO_RATE_NOTE_LABELS), "LFO1 Rate Note"),
                    }),
                    ("cc", 38): named(("sysex", 0x300B, 1023, "1DT", 4), "LFO1 Delay Time"),
                    ("cc", 39): named(("sysex", 0x3012, 1023, "1FT", 4), "LFO1 Fade Time"),
                    ("cc", 40): named(("sysex", 0x304F, 10, "2WT", 1, LFO_WAVE_LABELS), "LFO2 Wave Type"),
                    ("cc", 41): ("conditional_sysex", ("note", 51), {
                        0: named((0x3053, 1023, "2RT", 4), "LFO2 Rate"),
                        1: named((0x3051, 22, "2RN", 1, list(reversed(range(23))), LFO_RATE_NOTE_LABELS), "LFO2 Rate Note"),
                    }),
                    ("cc", 42): named(("sysex", 0x305A, 1023, "2DT", 4), "LFO2 Delay Time"),
                    ("cc", 43): named(("sysex", 0x3061, 1023, "2FT", 4), "LFO2 Fade Time"),
                    ("cc", 45): named(("sysex", 0x301B, 200, "1AD", "nibbles2", list(range(28, 229)), DRUM_200_OFFSET_LABELS), "LFO1 Amp Depth"),
                    ("cc", 46): named(("sysex", 0x301D, 200, "1PD", "nibbles2", list(range(28, 229)), DRUM_200_OFFSET_LABELS), "LFO1 Pan Depth"),
                    ("cc", 47): named(("sysex", 0x3019, 200, "1FD", "nibbles2", list(range(28, 229)), DRUM_200_OFFSET_LABELS), "LFO1 Filter Depth"),
                    ("cc", 48): named(("sysex", 0x3017, 200, "1XD", "nibbles2", list(range(28, 229)), DRUM_200_OFFSET_LABELS), "LFO1 Pitch Depth"),
                    ("cc", 49): named(("sysex", 0x306A, 200, "2AD", "nibbles2", list(range(28, 229)), DRUM_200_OFFSET_LABELS), "LFO2 Amp Depth"),
                    ("cc", 50): named(("sysex", 0x306C, 200, "2PD", "nibbles2", list(range(28, 229)), DRUM_200_OFFSET_LABELS), "LFO2 Pan Depth"),
                    ("cc", 51): named(("sysex", 0x3068, 200, "2FD", "nibbles2", list(range(28, 229)), DRUM_200_OFFSET_LABELS), "LFO2 Filter Depth"),
                    ("cc", 52): named(("sysex", 0x3066, 200, "2XD", "nibbles2", list(range(28, 229)), DRUM_200_OFFSET_LABELS), "LFO2 Pitch Depth"),
                    ("note", 42): named(("sysex", 0x3001, 1, "1RS", 1, {0: "OFF", 1: "ON"}, "toggle"), "LFO1 Rate Sync"),
                    ("note", 43): named(("sysex", 0x3016, 1, "1KT", 1, {0: "OFF", 1: "ON"}, "toggle"), "LFO1 Key Trigger"),
                    ("note", 44): named(("cycle_sysex", 0x3011, 3, "1FM", 1, LFO_FADE_MODE_LABELS), "LFO1 Fade Mode"),
                    ("note", 45): named(("partial_select", 1, "P01"), "Partial"),
                    ("note", 46): named(("partial_select", 2, "P02"), "Partial"),
                    ("note", 47): named(("partial_select", 3, "P03"), "Partial"),
                    ("note", 48): named(("partial_select", 4, "P04"), "Partial"),
                    ("note", 49): named(("dynamic_sysex_track", {1: 0x1002, 2: 0x100B, 3: 0x1014, 4: 0x101D}, 1, "PSW", 1, {0: "OFF", 1: "ON"}, "toggle"), "Partial Switch"),
                    ("note", 51): named(("sysex", 0x3050, 1, "2RS", 1, {0: "OFF", 1: "ON"}, "toggle"), "LFO2 Rate Sync"),
                    ("note", 52): named(("sysex", 0x3065, 1, "2KT", 1, {0: "OFF", 1: "ON"}, "toggle"), "LFO2 Key Trigger"),
                    ("note", 53): named(("cycle_sysex", 0x3060, 3, "2FM", 1, LFO_FADE_MODE_LABELS), "LFO2 Fade Mode"),
                }
            },
            4: {
                "name": "Matrix 1-4",
                "mappings": {
                    ("note", 54): named(("track_select", 1, "T01"), "Track"),
                    ("note", 55): named(("track_select", 2, "T02"), "Track"),
                    ("note", 56): named(("track_select", 3, "T03"), "Track"),
                    ("note", 57): named(("track_select", 4, "T04"), "Track"),

                    ("cc", 54): named(("sysex", 0x205F, 108, "1SC", 1, MATRIX_SOURCE_LABELS), "Matrix 1 Source"),
                    ("cc", 55): named(("sysex", 0x2060, 48, "1DT", 1, MATRIX_DEST_LABELS), "Matrix 1 Dest"),
                    ("cc", 63): named(("sysex", 0x2061, 126, "1SN", 1, MATRIX_SENS_VALUES, MATRIX_SENS_LABELS), "Matrix 1 Sens"),

                    ("cc", 56): named(("sysex", 0x2068, 108, "2SC", 1, MATRIX_SOURCE_LABELS), "Matrix 2 Source"),
                    ("cc", 57): named(("sysex", 0x2069, 48, "2DT", 1, MATRIX_DEST_LABELS), "Matrix 2 Dest"),
                    ("cc", 65): named(("sysex", 0x206A, 126, "2SN", 1, MATRIX_SENS_VALUES, MATRIX_SENS_LABELS), "Matrix 2 Sens"),

                    ("cc", 58): named(("sysex", 0x2071, 108, "3SC", 1, MATRIX_SOURCE_LABELS), "Matrix 3 Source"),
                    ("cc", 59): named(("sysex", 0x2072, 48, "3DT", 1, MATRIX_DEST_LABELS), "Matrix 3 Dest"),
                    ("cc", 67): named(("sysex", 0x2073, 126, "3SN", 1, MATRIX_SENS_VALUES, MATRIX_SENS_LABELS), "Matrix 3 Sens"),

                    ("cc", 60): named(("sysex", 0x207A, 108, "4SC", 1, MATRIX_SOURCE_LABELS), "Matrix 4 Source"),
                    ("cc", 61): named(("sysex", 0x207B, 48, "4DT", 1, MATRIX_DEST_LABELS), "Matrix 4 Dest"),
                    ("cc", 69): named(("sysex", 0x207C, 126, "4SN", 1, MATRIX_SENS_VALUES, MATRIX_SENS_LABELS), "Matrix 4 Sens"),

                    ("note", 63): named(("partial_select", 1, "P01"), "Partial"),
                    ("note", 64): named(("partial_select", 2, "P02"), "Partial"),
                    ("note", 65): named(("partial_select", 3, "P03"), "Partial"),
                    ("note", 66): named(("partial_select", 4, "P04"), "Partial"),
                    ("note", 67): named(("dynamic_sysex_track", {1: 0x1002, 2: 0x100B, 3: 0x1014, 4: 0x101D}, 1, "PSW", 1, {0: "OFF", 1: "ON"}, "toggle"), "Partial Switch"),
                }
            }
        }
    },
    PRESET_7: {
        "name": "MC-101",
        "context": "track",
        "default_track": 1,
        "display_values": True,
        "scenes": {
            1: {
                "name": "Scatter & CH 1",
                "mappings": {
                    ("note", 0): named(("note", 12, 60, "P01"), "P01"),
                    ("note", 1): named(("note", 12, 61, "P02"), "P02"),
                    ("note", 2): named(("note", 12, 62, "P03"), "P03"),
                    ("note", 3): named(("note", 12, 63, "P04"), "P04"),
                    ("note", 4): named(("note", 12, 64, "P05"), "P05"),
                    ("note", 5): named(("note", 12, 65, "P06"), "P06"),
                    ("note", 6): named(("note", 12, 66, "P07"), "P07"),
                    ("note", 7): named(("note", 12, 67, "P08"), "P08"),
                    ("note", 9): named(("note", 12, 68, "P09"), "P09"),
                    ("note", 10): named(("note", 12, 69, "P10"), "P10"),
                    ("note", 11): named(("note", 12, 70, "P11"), "P11"),
                    ("note", 12): named(("note", 12, 71, "P12"), "P12"),
                    ("note", 13): named(("note", 12, 72, "P13"), "P13"),
                    ("note", 14): named(("note", 12, 73, "P14"), "P14"),
                    ("note", 15): named(("note", 12, 74, "P15"), "P15"),
                    ("note", 16): named(("note", 12, 75, "P16"), "P16"),

                    ("cc", 0): named(("cc", 0, 74, "CUT"), "Cutoff"),
                    ("cc", 1): named(("cc", 0, 71, "RES"), "Resonance"),
                    ("cc", 2): named(("cc", 0, 10, "PAN"), "Pan"),
                    ("cc", 3): named(("cc", 0, 91, "REV"), "Reverb Send Level"),
                    ("cc", 4): named(("cc", 0, 93, "DLY"), "Delay Send Level"),
                    ("cc", 5): named(("cc", 0, 80, "FLT"), "[FILTER] Knob"),
                    ("cc", 6): named(("cc", 0, 81, "MOD"), "[MOD] Knob"),
                    ("cc", 7): named(("cc", 0, 82, "FX"), "[FX] Knob"),
                    ("cc", 8): named(("cc", 0, 83, "SND"), "[SOUND] Knob"),

                    ("cc", 9): named(("cc", 0, 7, "VOL"), "Volume"),
                    ("cc", 10): named(("cc", 0, 73, "ATK"), "Attack Time"),
                    ("cc", 11): named(("cc", 0, 75, "DCY"), "Decay Time"),
                    ("cc", 12): named(("cc", 0, 72, "REL"), "Release Time"),
                    ("cc", 13): named(("cc", 0, 1, "MOD"), "Modulation"),
                    ("cc", 14): named(("cc", 0, 5, "POR"), "Portamento Time"),
                    ("cc", 15): named(("cc", 0, 84, "PCT"), "Portamento Control"),
                    ("cc", 16): named(("cc", 0, 76, "VRT"), "Vibrato Rate"),
                    ("cc", 17): named(("cc", 0, 77, "VDP"), "Vibrato Depth"),
                }
            },
            2: {
                "name": "Scatter & CH 2",
                "mappings": {
                    ("note", 18): named(("note", 12, 60, "P01"), "P01"),
                    ("note", 19): named(("note", 12, 61, "P02"), "P02"),
                    ("note", 20): named(("note", 12, 62, "P03"), "P03"),
                    ("note", 21): named(("note", 12, 63, "P04"), "P04"),
                    ("note", 22): named(("note", 12, 64, "P05"), "P05"),
                    ("note", 23): named(("note", 12, 65, "P06"), "P06"),
                    ("note", 24): named(("note", 12, 66, "P07"), "P07"),
                    ("note", 25): named(("note", 12, 67, "P08"), "P08"),
                    ("note", 27): named(("note", 12, 68, "P09"), "P09"),
                    ("note", 28): named(("note", 12, 69, "P10"), "P10"),
                    ("note", 29): named(("note", 12, 70, "P11"), "P11"),
                    ("note", 30): named(("note", 12, 71, "P12"), "P12"),
                    ("note", 31): named(("note", 12, 72, "P13"), "P13"),
                    ("note", 32): named(("note", 12, 73, "P14"), "P14"),
                    ("note", 33): named(("note", 12, 74, "P15"), "P15"),
                    ("note", 34): named(("note", 12, 75, "P16"), "P16"),

                    ("cc", 18): named(("cc", 1, 74, "CUT"), "Cutoff"),
                    ("cc", 19): named(("cc", 1, 71, "RES"), "Resonance"),
                    ("cc", 20): named(("cc", 1, 10, "PAN"), "Pan"),
                    ("cc", 21): named(("cc", 1, 91, "REV"), "Reverb Send Level"),
                    ("cc", 22): named(("cc", 1, 93, "DLY"), "Delay Send Level"),
                    ("cc", 23): named(("cc", 1, 80, "FLT"), "[FILTER] Knob"),
                    ("cc", 24): named(("cc", 1, 81, "MOD"), "[MOD] Knob"),
                    ("cc", 25): named(("cc", 1, 82, "FX"), "[FX] Knob"),
                    ("cc", 26): named(("cc", 1, 83, "SND"), "[SOUND] Knob"),

                    ("cc", 27): named(("cc", 1, 7, "VOL"), "Volume"),
                    ("cc", 28): named(("cc", 1, 73, "ATK"), "Attack Time"),
                    ("cc", 29): named(("cc", 1, 75, "DCY"), "Decay Time"),
                    ("cc", 30): named(("cc", 1, 72, "REL"), "Release Time"),
                    ("cc", 31): named(("cc", 1, 1, "MOD"), "Modulation"),
                    ("cc", 32): named(("cc", 1, 5, "POR"), "Portamento Time"),
                    ("cc", 33): named(("cc", 1, 84, "PCT"), "Portamento Control"),
                    ("cc", 34): named(("cc", 1, 76, "VRT"), "Vibrato Rate"),
                    ("cc", 35): named(("cc", 1, 77, "VDP"), "Vibrato Depth"),
                }
            },
            3: {
                "name": "Scatter & CH 3",
                "mappings": {
                    ("note", 36): named(("note", 12, 60, "P01"), "P01"),
                    ("note", 37): named(("note", 12, 61, "P02"), "P02"),
                    ("note", 38): named(("note", 12, 62, "P03"), "P03"),
                    ("note", 39): named(("note", 12, 63, "P04"), "P04"),
                    ("note", 40): named(("note", 12, 64, "P05"), "P05"),
                    ("note", 41): named(("note", 12, 65, "P06"), "P06"),
                    ("note", 42): named(("note", 12, 66, "P07"), "P07"),
                    ("note", 43): named(("note", 12, 67, "P08"), "P08"),
                    ("note", 45): named(("note", 12, 68, "P09"), "P09"),
                    ("note", 46): named(("note", 12, 69, "P10"), "P10"),
                    ("note", 47): named(("note", 12, 70, "P11"), "P11"),
                    ("note", 48): named(("note", 12, 71, "P12"), "P12"),
                    ("note", 49): named(("note", 12, 72, "P13"), "P13"),
                    ("note", 50): named(("note", 12, 73, "P14"), "P14"),
                    ("note", 51): named(("note", 12, 74, "P15"), "P15"),
                    ("note", 52): named(("note", 12, 75, "P16"), "P16"),

                    ("cc", 36): named(("cc", 2, 74, "CUT"), "Cutoff"),
                    ("cc", 37): named(("cc", 2, 71, "RES"), "Resonance"),
                    ("cc", 38): named(("cc", 2, 10, "PAN"), "Pan"),
                    ("cc", 39): named(("cc", 2, 91, "REV"), "Reverb Send Level"),
                    ("cc", 40): named(("cc", 2, 93, "DLY"), "Delay Send Level"),
                    ("cc", 41): named(("cc", 2, 80, "FLT"), "[FILTER] Knob"),
                    ("cc", 42): named(("cc", 2, 81, "MOD"), "[MOD] Knob"),
                    ("cc", 43): named(("cc", 2, 82, "FX"), "[FX] Knob"),
                    ("cc", 44): named(("cc", 2, 83, "SND"), "[SOUND] Knob"),

                    ("cc", 45): named(("cc", 2, 7, "VOL"), "Volume"),
                    ("cc", 46): named(("cc", 2, 73, "ATK"), "Attack Time"),
                    ("cc", 47): named(("cc", 2, 75, "DCY"), "Decay Time"),
                    ("cc", 48): named(("cc", 2, 72, "REL"), "Release Time"),
                    ("cc", 49): named(("cc", 2, 1, "MOD"), "Modulation"),
                    ("cc", 50): named(("cc", 2, 5, "POR"), "Portamento Time"),
                    ("cc", 51): named(("cc", 2, 84, "PCT"), "Portamento Control"),
                    ("cc", 52): named(("cc", 2, 76, "VRT"), "Vibrato Rate"),
                    ("cc", 53): named(("cc", 2, 77, "VDP"), "Vibrato Depth"),
                }
            },
            4: {
                "name": "Scatter & CH 4",
                "mappings": {
                    ("note", 54): named(("note", 12, 60, "P01"), "P01"),
                    ("note", 55): named(("note", 12, 61, "P02"), "P02"),
                    ("note", 56): named(("note", 12, 62, "P03"), "P03"),
                    ("note", 57): named(("note", 12, 63, "P04"), "P04"),
                    ("note", 58): named(("note", 12, 64, "P05"), "P05"),
                    ("note", 59): named(("note", 12, 65, "P06"), "P06"),
                    ("note", 60): named(("note", 12, 66, "P07"), "P07"),
                    ("note", 61): named(("note", 12, 67, "P08"), "P08"),
                    ("note", 63): named(("note", 12, 68, "P09"), "P09"),
                    ("note", 64): named(("note", 12, 69, "P10"), "P10"),
                    ("note", 65): named(("note", 12, 70, "P11"), "P11"),
                    ("note", 66): named(("note", 12, 71, "P12"), "P12"),
                    ("note", 67): named(("note", 12, 72, "P13"), "P13"),
                    ("note", 68): named(("note", 12, 73, "P14"), "P14"),
                    ("note", 69): named(("note", 12, 74, "P15"), "P15"),
                    ("note", 70): named(("note", 12, 75, "P16"), "P16"),

                    ("cc", 54): named(("cc", 3, 74, "CUT"), "Cutoff"),
                    ("cc", 55): named(("cc", 3, 71, "RES"), "Resonance"),
                    ("cc", 56): named(("cc", 3, 10, "PAN"), "Pan"),
                    ("cc", 57): named(("cc", 3, 91, "REV"), "Reverb Send Level"),
                    ("cc", 58): named(("cc", 3, 93, "DLY"), "Delay Send Level"),
                    ("cc", 59): named(("cc", 3, 80, "FLT"), "[FILTER] Knob"),
                    ("cc", 60): named(("cc", 3, 81, "MOD"), "[MOD] Knob"),
                    ("cc", 61): named(("cc", 3, 82, "FX"), "[FX] Knob"),
                    ("cc", 62): named(("cc", 3, 83, "SND"), "[SOUND] Knob"),

                    ("cc", 63): named(("cc", 3, 7, "VOL"), "Volume"),
                    ("cc", 64): named(("cc", 3, 73, "ATK"), "Attack Time"),
                    ("cc", 65): named(("cc", 3, 75, "DCY"), "Decay Time"),
                    ("cc", 66): named(("cc", 3, 72, "REL"), "Release Time"),
                    ("cc", 67): named(("cc", 3, 1, "MOD"), "Modulation"),
                    ("cc", 68): named(("cc", 3, 5, "POR"), "Portamento Time"),
                    ("cc", 69): named(("cc", 3, 84, "PCT"), "Portamento Control"),
                    ("cc", 70): named(("cc", 3, 76, "VRT"), "Vibrato Rate"),
                    ("cc", 71): named(("cc", 3, 77, "VDP"), "Vibrato Depth"),
                }
            }
        }
    },
        PRESET_8: {
        "name": "MC-101",
        "context": "none",
        "display_values": False,
        "scenes": {1: {"name": "Keyboard CH 1", "mappings": {}}}
    }, 
}

# --- ROLAND 7-BIT SYSEX MATH HELPERS ---
def to_7bit_int(address):
    b1, b2, b3, b4 = (address >> 24) & 0x7F, (address >> 16) & 0x7F, (address >> 8) & 0x7F, address & 0x7F
    return (b1 << 21) | (b2 << 14) | (b3 << 7) | b4

def to_7bit_hex(value):
    b1, b2, b3, b4 = (value >> 21) & 0x7F, (value >> 14) & 0x7F, (value >> 7) & 0x7F, value & 0x7F
    return (b1 << 24) | (b2 << 16) | (b3 << 8) | b4

def add_roland_address(base, *offsets):
    val = to_7bit_int(base)
    for off in offsets:
        val += to_7bit_int(off)
    return to_7bit_hex(val)

def compute_checksum(payload):
    return (128 - (sum(payload) % 128)) % 128

def send_sysex(out_port, address, value, size):
    DEVICE_ID, MODEL_ID = 0x10, [0x00, 0x00, 0x00, 0x5E]
    header = [0x41, DEVICE_ID] + MODEL_ID + [0x12]
    addr_bytes = [(address >> 24) & 0x7F, (address >> 16) & 0x7F, (address >> 8) & 0x7F, address & 0x7F]
    if size == 4:
        data_bytes = [(value >> 12) & 0x0F, (value >> 8) & 0x0F, (value >> 4) & 0x0F, value & 0x0F]
    elif size == "nibbles2":
        data_bytes = [(value >> 4) & 0x0F, value & 0x0F]
    elif size == 2:
        data_bytes = [(value >> 7) & 0x7F, value & 0x7F]
    else:
        data_bytes = [value & 0x7F]
    payload = addr_bytes + data_bytes
    sysex_data = header + payload + [compute_checksum(payload)]
    out_port.send(mido.Message("sysex", data=sysex_data))

# --- ADDRESS GENERATORS ---
def get_mc101_address(track, partial, param_offset):
    track_bases = {1: 0x30200000, 2: 0x30420000, 3: 0x30640000, 4: 0x31060000}
    base = track_bases.get(track, 0x30200000)
    partial_offset_int = (partial - 1) * 128
    return add_roland_address(base, to_7bit_hex(partial_offset_int), param_offset)

def get_drum_partial_address(track, pad, param_offset):
    drum_bases = {1: 0x32400000, 2: 0x32730000, 3: 0x33260000, 4: 0x33590000}
    base = drum_bases.get(track, 0x32400000)

    # The drum partial map is keyed by MIDI pitch/key number.
    # For backwards compatibility, pad values 1..16 still resolve through
    # the physical MC-101 PAD_NOTES list. Values 22..108 are treated as direct
    # drum keys, which lets Preset 5 address the full Drum Kit Partial range.
    if 22 <= int(pad) <= 108:
        pad_key = int(pad)
    elif 1 <= int(pad) <= len(PAD_NOTES):
        pad_key = PAD_NOTES[int(pad) - 1]
    else:
        pad_key = int(pad)

    key_offset_addr = (0x16 + (pad_key - 21)) << 8
    return add_roland_address(base, key_offset_addr, param_offset)

# --- HUD HELPERS ---
def get_value_text(value=None, text=None):
    if text is not None:
        return str(text)
    if value is not None:
        return str(value)
    if last_edited_text is not None:
        return str(last_edited_text)
    if last_edited_val is not None:
        return str(last_edited_val)
    return ""

def get_drum_edit_target_path():
    return f"MC-101 > T{active_track:02d} > {drum_key_short_name(active_pad)}"

def get_edit_target_path(preset_name):
    preset_data = PRESETS.get(active_preset, {})
    context = preset_data.get("context", "none")

    if context == "drum":
        return get_drum_edit_target_path()

    parts = [preset_name]

    if context in ("track", "partial"):
        parts.append(f"T{active_track:02d}")

    if context == "partial":
        parts.append(f"P{active_partial:02d}")

    return " > ".join(parts)

def build_preset_line1():
    return PRESETS.get(active_preset, {}).get("name", "NONE")

def build_scene_line1():
    if active_preset == PRESET_5 and 1 <= active_scene <= 4:
        return f"MC-101 > DRUM TRACK {active_scene}"

    preset_data = PRESETS.get(active_preset, {})
    scene_data = preset_data.get("scenes", {}).get(active_scene, {})
    return f"{preset_data.get('name', 'NONE')} > {scene_data.get('name', f'S{active_scene}')}"


def get_default_mc101_scene_bank(scene_number=None):
    preset_data = PRESETS.get(active_preset, {})
    scene_data = preset_data.get("scenes", {}).get(scene_number or active_scene, {})
    return scene_data.get("default_scene_bank", 0)


def mc101_scene_program(scene_index):
    return active_mc101_scene_bank * MC101_SCENES_PER_BANK + scene_index

def mc101_scene_label(scene_index):
    return f"S{active_mc101_scene_bank + 1}{scene_index + 1}"

def mc101_scene_name(scene_index):
    return f"Scene {active_mc101_scene_bank + 1:02d}-{scene_index + 1:02d}"

def send_m8_row_hold(out_port, value=M8_ROW_HOLD_VALUE):
    if not M8_ROW_HOLD_ENABLED:
        return

    out_port.send(mido.Message(
        "control_change",
        channel=M8_ROW_CUE_CHANNEL,
        control=M8_ROW_HOLD_CC,
        value=value,
    ))

def release_active_m8_row(out_port):
    global active_m8_row_note

    if active_m8_row_note is None:
        return

    out_port.send(mido.Message(
        "note_off",
        channel=M8_ROW_CUE_CHANNEL,
        note=active_m8_row_note,
        velocity=0,
    ))
    active_m8_row_note = None

def send_m8_row_note_pulse(out_port, row_index):
    out_port.send(mido.Message(
        "note_on",
        channel=M8_ROW_CUE_CHANNEL,
        note=row_index,
        velocity=M8_ROW_NOTE_VELOCITY,
    ))
    time.sleep(SELECTOR_NOTE_PULSE_SECONDS)
    out_port.send(mido.Message(
        "note_off",
        channel=M8_ROW_CUE_CHANNEL,
        note=row_index,
        velocity=0,
    ))

def launch_m8_song_row(out_port, row_index):
    """Launch/cue an M8 song row from the nanoKONTROL scene launcher.

    When M8_ROW_HOLD_ENABLED is True, keep the selected row held with CC64 and
    leave the row note on until another row is selected or the script exits.

    When M8_ROW_HOLD_ENABLED is False, do not send CC64 at all and do not leave
    the row note held. In that mode the row is launched with a short note pulse.
    """
    global active_m8_row_note

    if not M8_ROW_HOLD_ENABLED:
        release_active_m8_row(out_port)
        send_m8_row_note_pulse(out_port, row_index)
        return

    if active_m8_row_note is not None:
        # Release the previously held row before holding the next one. The new
        # row is sent immediately afterwards, so normal scene changes remain
        # seamless while avoiding a pile-up of held row notes.
        send_m8_row_hold(out_port, M8_ROW_RELEASE_VALUE)
        release_active_m8_row(out_port)

    send_m8_row_hold(out_port, M8_ROW_HOLD_VALUE)

    out_port.send(mido.Message(
        "note_on",
        channel=M8_ROW_CUE_CHANNEL,
        note=row_index,
        velocity=M8_ROW_NOTE_VELOCITY,
    ))
    active_m8_row_note = row_index

def cleanup_m8_song_row(out_port):
    release_active_m8_row(out_port)
    if M8_ROW_HOLD_ENABLED:
        send_m8_row_hold(out_port, M8_ROW_RELEASE_VALUE)

def mc101_scene_bank_label(bank_index):
    return f"B{bank_index + 1:02d}"

def mc101_scene_bank_name(bank_index):
    return f"Scene Bank {bank_index + 1:02d}"

def drum_parameter_display_name(name):
    if not name:
        return "Parameter"
    replacements = {
        "Cutoff Offset": "Cutoff",
        "Resonance Offset": "Resonance",
        "Key Offset": "Key",
        "Fine Tune Offset": "Fine Tune",
        "Attack Offset": "Attack",
        "Decay Offset": "Decay",
        "Release Offset": "Release",
    }
    return replacements.get(str(name), str(name))

def build_edit_line1(label=None, value=None, text=None, name=None):
    preset_name = PRESETS.get(active_preset, {}).get("name", "NONE")
    parameter_name = name or last_edited_name or label or "Parameter"
    value_text = get_value_text(value=value, text=text)
    base = get_edit_target_path(preset_name)

    if PRESET_5 == active_preset:
        parameter_name = drum_parameter_display_name(parameter_name)

    if value_text:
        return f"{base} > {parameter_name}: {value_text}"
    return f"{base} > {parameter_name}"

def describe_input(lookup_key, value=None, is_press=True):
    kind, number = lookup_key
    if kind == "cc":
        if value is not None:
            return f"CC {number}: {value}"
        return f"CC {number}"
    state = "ON" if is_press else "OFF"
    return f"Note {number}: {state}"

def write_overlay_text(overlay_text):
    if os.path.exists(OVERLAY_PIPE):
        try:
            fd = os.open(OVERLAY_PIPE, os.O_WRONLY | os.O_NONBLOCK)
            os.write(fd, overlay_text.encode())
            os.close(fd)
        except OSError:
            pass

def clear_overlay():
    # Send a blank overlay message. Requires render.c to treat empty/blank
    # overlay data as inactive, otherwise the background can still be drawn.
    write_overlay_text("\n")

def display_values_enabled():
    return PRESETS.get(active_preset, {}).get("display_values", True)

def is_matrix_control(lookup_key):
    """Return True for controls in the current 9x2 matrix.

    For scene 1 this is CC/Note 0-17. For scene 2 this is CC/Note 18-35,
    matching the existing scene offset logic used by the HUD matrix.
    """
    kind, number = lookup_key
    if kind not in ("cc", "note"):
        return False
    offset = (active_scene - 1) * 18
    return offset <= number < offset + 18

def get_condition_value(condition_key, track_level=False):
    if track_level:
        return param_states.get((active_track, "track", condition_key), 0)
    return param_states.get(
        (active_track, "track", condition_key),
        param_states.get((active_track, active_partial, condition_key), 0)
    )

def resolve_conditional_target(mapping):
    clean_mapping = strip_mapping_metadata(mapping)
    out_type = clean_mapping[0]
    condition_key = clean_mapping[1]
    condition_map = clean_mapping[2]

    cond_val = get_condition_value(condition_key, track_level=(out_type == "conditional_sysex_track"))
    target = condition_map.get(cond_val)

    if not target:
        return None

    clean_target = strip_mapping_metadata(target)
    if clean_target and clean_target[0] == "bank_dependent":
        bank_val = param_states.get(
            (active_track, "track", ("cc", 2)),
            param_states.get((active_track, active_partial, ("cc", 2)), 8)
        )
        target = clean_target[1].get(bank_val)

    return target

def get_mapping_label(mapping):
    if not mapping:
        return "---"

    clean_mapping = strip_mapping_metadata(mapping)
    out_type = clean_mapping[0]

    if out_type in ["conditional_sysex", "conditional_sysex_track"]:
        target = resolve_conditional_target(mapping)
        if not target:
            return "---"
        clean_target = strip_mapping_metadata(target)
        return clean_target[2] if len(clean_target) > 2 else "---"

    if out_type in ["track_select", "partial_select"]:
        return clean_mapping[2]
    if out_type == "mc101_scene_select":
        return mc101_scene_label(clean_mapping[1])
    if out_type == "mc101_scene_bank":
        return mc101_scene_bank_label(clean_mapping[1])
    if out_type == "drum_sysex_partial":
        return clean_mapping[3]
    if out_type == "drum_pad_key_select":
        return drum_key_short_name(shifted_drum_key(clean_mapping[2]))
    if out_type == "drum_scene_octave":
        return clean_mapping[3]
    if out_type == "drum_pad_velocity":
        return clean_mapping[1]
    if out_type == "param_mode_toggle":
        mode_key = clean_mapping[1]
        short_off = clean_mapping[2]
        short_on = clean_mapping[3]
        mode_value = param_states.get((active_track, active_partial, mode_key), 0)
        return short_on if mode_value else short_off
    if out_type == "drum_pad_select":
        return f"PD{(active_pad_bank * 4 + clean_mapping[1]):02d}"
    if out_type == "drum_pad_bank":
        return clean_mapping[2]
    if out_type == "keyboard_note":
        return clean_mapping[3]
    if out_type == "keyboard_octave":
        return clean_mapping[3]
    if out_type == "keyboard_velocity":
        return clean_mapping[1]
    if out_type == "cycle_sysex":
        return clean_mapping[3] if len(clean_mapping) > 3 else "---"

    for item in clean_mapping[3:]:
        if isinstance(item, str) and item != "toggle":
            return item
    return "---"

def get_mapping_name(mapping, fallback=None):
    if mapping:
        clean_mapping = strip_mapping_metadata(mapping)
        out_type = clean_mapping[0]
        if out_type == "mc101_scene_select":
            return mc101_scene_name(clean_mapping[1])
        if out_type == "mc101_scene_bank":
            return mc101_scene_bank_name(clean_mapping[1])
        if out_type == "keyboard_note":
            return midi_note_name(keyboard_output_note(clean_mapping[1], clean_mapping[2]))
        if out_type == "drum_pad_key_select":
            return drum_key_long_name(shifted_drum_key(clean_mapping[2]))
        if out_type in ("drum_pad_velocity", "drum_scene_octave", "param_mode_toggle"):
            return get_configured_parameter_name(mapping, fallback or get_mapping_label(mapping))
        if out_type in ("keyboard_octave", "keyboard_velocity", "cycle_sysex"):
            return get_configured_parameter_name(mapping, fallback or get_mapping_label(mapping))
    return get_configured_parameter_name(mapping, fallback or get_mapping_label(mapping))

def get_target_fields(mapping, out_type):
    clean_mapping = strip_mapping_metadata(mapping)

    if out_type in ["sysex", "sysex_track", "drum_sysex_partial"]:
        return clean_mapping[1:], get_configured_parameter_name(mapping, clean_mapping[3])

    if out_type == "dynamic_sysex_track":
        fields = (
            clean_mapping[1].get(active_partial, 0),
            clean_mapping[2],
            clean_mapping[3],
        ) + clean_mapping[4:]
        return fields, get_configured_parameter_name(mapping, clean_mapping[3])

    if out_type in ["conditional_sysex", "conditional_sysex_track"]:
        target = resolve_conditional_target(mapping)
        if not target:
            return None, None
        clean_target = strip_mapping_metadata(target)
        return clean_target, get_configured_parameter_name(target, clean_target[2] if len(clean_target) > 2 else None)

    return None, None

def parse_target_fields(fields, long_name):
    if not fields or fields[0] is None:
        return None

    offsets = fields[0] if isinstance(fields[0], list) else [fields[0]]
    max_value = fields[1]
    label = fields[2]
    size = fields[3] if len(fields) > 3 else 1

    value_list = None
    text_map = None
    for item in fields[4:]:
        if isinstance(item, list):
            value_list = item
        elif is_value_map_dict(item):
            text_map = item

    return offsets, max_value, label, size, value_list, text_map, long_name or label

def build_matrix_labels(control_type=None, highlight_current=True):
    scene_data = PRESETS.get(active_preset, {}).get("scenes", {}).get(active_scene, {})
    mappings = scene_data.get("mappings", {})
    labels = []
    offset = (active_scene - 1) * 18
    matrix_type = control_type or last_touched_type

    for i in range(18):
        key = (matrix_type, i + offset)
        label = get_mapping_label(mappings.get(key))
        if highlight_current and label == last_edited_label:
            core_str = ">X<"
        else:
            core_str = str(label).strip()[:3].upper().ljust(3, " ")
        labels.append(core_str)

    return labels


def write_overlay_matrix(line1, labels, separator):
    overlay_text = (
        f"{line1.ljust(45)}~"
        f"{separator.join(labels[:9]).ljust(55)}~"
        f"{separator.join(labels[9:18]).ljust(55)}\n"
    )
    write_overlay_text(overlay_text)


def update_overlay(force_title=False):
    preset_data = PRESETS.get(active_preset, {})
    line1 = current_line1 or preset_data.get("name", "NONE")

    if force_title:
        # Preset and scene selection should briefly show the title plus the
        # buttons available in the current scene, even when display_values is
        # disabled for normal parameter/button feedback.
        button_labels = build_matrix_labels(control_type="note", highlight_current=False)
        write_overlay_matrix(line1, button_labels, " : ")
        return

    if not preset_data.get("display_values", True):
        clear_overlay()
        return

    labels = build_matrix_labels()
    sep = " | " if last_touched_type == "cc" else " : "
    write_overlay_matrix(line1, labels, sep)

# --- PRESET AND TRANSPORT HANDLING ---
def remember_output_note(channel, note):
    ignored_output_notes[(channel, note)] = time.time() + LOOPBACK_IGNORE_SECONDS

def remember_output_note_on(channel, note):
    output_notes_held.add((channel, note))
    remember_output_note(channel, note)

def remember_output_note_off(channel, note):
    output_notes_held.discard((channel, note))
    remember_output_note(channel, note)

def is_ignored_output_note(msg):
    if msg.type not in ("note_on", "note_off"):
        return False

    key = (getattr(msg, "channel", None), msg.note)
    now = time.time()

    if key in output_notes_held:
        return True

    expiry = ignored_output_notes.get(key, 0)
    if expiry and now <= expiry:
        return True
    if expiry:
        ignored_output_notes.pop(key, None)
    return False

def send_m8_button_down(out_port, channel, note, velocity=127):
    """Hold an M8 button down until its matching release arrives.

    This is required for M8 key combinations, for example Shift + Left,
    and for cursor key repeat when an arrow button is held.
    """
    remember_output_note_on(channel, note)
    out_port.send(mido.Message("note_on", channel=channel, note=note, velocity=velocity))

def send_m8_button_up(out_port, channel, note):
    remember_output_note_off(channel, note)
    out_port.send(mido.Message("note_off", channel=channel, note=note, velocity=0))

def send_navigation_note_off(out_port, channel, note):
    send_m8_button_up(out_port, channel, note)

def release_all_navigation_notes(out_port):
    # Safety release for all M8 button notes used by this script.
    stop_all_arrow_repeats(out_port)
    for note in range(8):
        send_m8_button_up(out_port, M8_CHANNEL, note)

def release_all_keyboard_notes(out_port):
    keyboard_notes = list(set(keyboard_notes_held.values()))
    keyboard_notes_held.clear()
    for channel, note in keyboard_notes:
        out_port.send(mido.Message("note_off", channel=channel, note=note, velocity=0))

def send_keyboard_note(out_port, lookup_key, channel, base_note, is_press):
    held_key = (channel, lookup_key)

    if is_press:
        output_note = keyboard_output_note(channel, base_note)
        keyboard_notes_held[held_key] = (channel, output_note)
        out_port.send(mido.Message(
            "note_on",
            channel=channel,
            note=output_note,
            velocity=keyboard_velocity,
        ))
        return output_note

    output_channel, output_note = keyboard_notes_held.pop(
        held_key,
        (channel, keyboard_output_note(channel, base_note)),
    )
    out_port.send(mido.Message(
        "note_off",
        channel=output_channel,
        note=output_note,
        velocity=0,
    ))
    return output_note

def send_note_pulse(out_port, channel, note, velocity=127):
    """Send one short M8 button press: note-on followed by note-off."""
    send_m8_button_down(out_port, channel, note, velocity)
    time.sleep(SELECTOR_NOTE_PULSE_SECONDS)
    send_m8_button_up(out_port, channel, note)

def arrow_repeat_worker(out_port, control, channel, note, stop_event):
    """Emulate the M8 hardware arrow-key repeat while a selector is held.

    The M8 responds reliably to short note pulses. Holding a MIDI note does not
    always trigger repeat, so arrows are pulsed repeatedly. Modifier buttons
    such as Shift/Edit/Option stay held independently, allowing combos such as
    Shift + Left to repeat correctly.
    """
    send_note_pulse(out_port, channel, note)

    if stop_event.wait(ARROW_REPEAT_INITIAL_DELAY_SECONDS):
        return

    while not stop_event.is_set():
        send_note_pulse(out_port, channel, note)
        if stop_event.wait(ARROW_REPEAT_INTERVAL_SECONDS):
            break

def start_arrow_repeat(out_port, control, channel, note):
    with arrow_repeat_lock:
        existing = arrow_repeat_stops.get(control)
        if existing is not None and not existing.is_set():
            return

        stop_event = threading.Event()
        arrow_repeat_stops[control] = stop_event

    thread = threading.Thread(
        target=arrow_repeat_worker,
        args=(out_port, control, channel, note, stop_event),
        daemon=True,
    )
    thread.start()

def stop_arrow_repeat(out_port, control, channel, note):
    with arrow_repeat_lock:
        stop_event = arrow_repeat_stops.pop(control, None)
        if stop_event is not None:
            stop_event.set()

    # Safety release in case the M8 or ALSA saw a held note from an earlier run.
    send_m8_button_up(out_port, channel, note)

def stop_all_arrow_repeats(out_port):
    for control, (note, _name) in PRESET_SELECTOR_NOTES.items():
        stop_arrow_repeat(out_port, control, M8_CHANNEL, note)

def handle_selector_cc(out_port, control, value, suppress_navigation=False):
    """Handle one of the four selector/navigation CCs.

    Arrow buttons behave like the M8 hardware buttons: one step immediately,
    then repeated steps while held. Modifier buttons are handled separately as
    true held notes, so combinations such as Shift + Left work.

    No standalone HUD feedback is generated here.
    """
    note, _name = PRESET_SELECTOR_NOTES[control]

    if value > 0:
        if suppress_navigation:
            # A preset combo should not also move the M8 cursor.
            stop_arrow_repeat(out_port, control, M8_CHANNEL, note)
            return
        start_arrow_repeat(out_port, control, M8_CHANNEL, note)
        return

    stop_arrow_repeat(out_port, control, M8_CHANNEL, note)

def select_preset(preset_number, out_port=None):
    global active_preset, active_scene, active_track, active_partial, active_pad, active_pad_bank, active_mc101_scene_bank
    global last_edited_label, last_edited_name, last_edited_val, last_edited_text, current_line1

    if out_port is not None:
        release_all_keyboard_notes(out_port)

    active_preset = preset_number
    preset_data = PRESETS.get(active_preset, {})

    scenes = preset_data.get("scenes", {})
    if 1 in scenes:
        active_scene = 1
    elif scenes:
        active_scene = sorted(scenes.keys())[0]
    else:
        active_scene = 1

    if "default_track" in preset_data:
        active_track = preset_data["default_track"]

    active_partial = 1
    active_pad = 37 if preset_number == PRESET_5 else 1
    active_pad_bank = 0
    active_mc101_scene_bank = get_default_mc101_scene_bank(active_scene)

    last_edited_label = None
    last_edited_name = None
    last_edited_val = None
    last_edited_text = None
    if out_port is not None:
        release_all_navigation_notes(out_port)
    current_line1 = build_scene_line1()
    update_overlay(force_title=True)

def handle_preset_selection_cc(msg, out_port):
    global preset_prefix, preset_prefix_time, current_line1
    global last_edited_label, last_edited_name, last_edited_val, last_edited_text, last_touched_type

    if msg.type != "control_change":
        return False

    now = time.time()
    control = msg.control
    is_press = msg.value > 0

    if control in (PRESET_PREFIX_PRIMARY, PRESET_PREFIX_SECONDARY):
        if is_press:
            preset_prefix = control
            preset_prefix_time = now
        return True

    if control in PRESET_SELECTOR_NOTES:
        combo = (preset_prefix, control)
        prefix_is_valid = preset_prefix is not None and (now - preset_prefix_time) <= PRESET_PREFIX_TIMEOUT
        combo_is_valid = is_press and prefix_is_valid and combo in PRESET_COMBOS

        # These four selector/navigation buttons should not show standalone HUD
        # feedback. They only update the HUD when they complete a preset combo.
        # When used as a preset combo, suppress the navigation pulse so changing
        # presets does not also move the M8 cursor.
        handle_selector_cc(out_port, control, msg.value, suppress_navigation=combo_is_valid)

        if combo_is_valid:
            preset_prefix = None
            select_preset(PRESET_COMBOS[combo], out_port)

        return True

    if preset_prefix is not None and (now - preset_prefix_time) > PRESET_PREFIX_TIMEOUT:
        preset_prefix = None

    return False

def schedule_matrix_swap(preset_number, scene_number, trigger_time):
    time.sleep(2.5)
    if active_preset == preset_number and active_scene == scene_number and last_interaction_time <= trigger_time:
        global last_touched_type
        last_touched_type = "note"
        update_overlay()

def send_transport_message(transport_out_port, command):
    """Send MIDI transport only through the dedicated MC-101 transport port.

    MIDI Start/Stop are system realtime messages and have no MIDI channel, so
    they must not go through nanoRouterOUT. amidiminder should connect this
    dedicated virtual port only to the MC-101.
    """
    if transport_out_port is None:
        print(f"MC-101 transport output unavailable. Transport '{command}' was not sent.")
        return

    if command == "start":
        transport_out_port.send(mido.Message("start"))
    elif command == "stop":
        transport_out_port.send(mido.Message("stop"))
    else:
        print(f"Unknown MIDI transport command: {command}")

# --- MAIN MIDI ROUTER ---
def main():
    global active_scene, active_track, active_partial, active_pad, active_pad_bank, active_mc101_scene_bank, active_m8_row_note, active_drum_velocity
    global last_edited_label, last_edited_name, last_edited_val, last_edited_text
    global last_sysex_time, last_touched_type, last_interaction_time, current_line1

    in_port = None
    out_port = None
    transport_out_port = None

    try:
        in_port = mido.open_input("In", virtual=True, client_name="nanoRouterIN")
        out_port = mido.open_output("Out", virtual=True, client_name="nanoRouterOUT")
        transport_out_port = mido.open_output(
            MC101_TRANSPORT_PORT_NAME,
            virtual=True,
            client_name=MC101_TRANSPORT_CLIENT_NAME,
        )
    except Exception as exc:
        sys.exit(f"Failed: {exc}")

    if out_port is not None:
        release_all_navigation_notes(out_port)
    current_line1 = build_preset_line1()
    update_overlay()

    def midi_callback(msg):
        global active_scene, active_track, active_partial, active_pad, active_pad_bank, active_mc101_scene_bank, active_m8_row_note, active_drum_velocity
        global last_edited_label, last_edited_name, last_edited_val, last_edited_text
        global last_sysex_time, last_touched_type, last_interaction_time, current_line1

        if msg.type == "sysex" and msg.data[:8] == (66, 75, 0, 1, 4, 0, 95, 79):
            release_all_keyboard_notes(out_port)
            active_scene = msg.data[8] + 1
            if active_preset == PRESET_5 and 1 <= active_scene <= 4:
                active_track = active_scene
            active_mc101_scene_bank = get_default_mc101_scene_bank(active_scene)
            current_line1 = build_scene_line1()
            update_overlay(force_title=True)
            return

        if is_ignored_output_note(msg):
            return

        if msg.type == "control_change" and handle_preset_selection_cc(msg, out_port):
            return

        if msg.type == "control_change":
            lookup_key, val, last_touched_type = ("cc", msg.control), msg.value, "cc"
        elif msg.type in ["note_on", "note_off"]:
            lookup_key, val, last_touched_type = ("note", msg.note), getattr(msg, "velocity", 0), "note"
        else:
            return

        is_press = val > 0 if msg.type != "note_off" else False
        last_interaction_time = time.time()

        preset_data = PRESETS.get(active_preset, {})
        scene_data = preset_data.get("scenes", {}).get(active_scene, {})
        mappings = scene_data.get("mappings", {})

        if lookup_key not in mappings:
            if display_values_enabled() and is_matrix_control(lookup_key) and (msg.type == "control_change" or is_press):
                current_line1 = f"{build_preset_line1()} > {describe_input(lookup_key, value=val, is_press=is_press)}"
                update_overlay()
            elif not display_values_enabled():
                clear_overlay()
            return

        mapping = mappings[lookup_key]
        clean_mapping = strip_mapping_metadata(mapping)
        out_type = clean_mapping[0]
        is_track_level = out_type in ["sysex_track", "dynamic_sysex_track", "conditional_sysex_track"]
        is_toggle = "toggle" in clean_mapping

        if is_toggle:
            if not is_press:
                return

            if out_type == "dynamic_sysex_track":
                state_key = (active_preset, active_scene, lookup_key, active_partial)
            elif out_type == "drum_sysex_partial":
                state_key = (active_preset, active_scene, lookup_key, active_pad)
            elif is_track_level:
                state_key = (active_preset, active_scene, lookup_key, "track")
            else:
                state_key = (active_preset, active_scene, lookup_key, active_partial)

            new_state = not toggle_states.get(state_key, False)
            toggle_states[state_key] = new_state
            val = 127 if new_state else 0

        if out_type == "param_mode_toggle":
            if is_press:
                mode_key = clean_mapping[1]
                short_off = clean_mapping[2]
                short_on = clean_mapping[3]
                name_off = clean_mapping[4]
                name_on = clean_mapping[5]
                current_mode = param_states.get((active_track, active_partial, mode_key), 0)
                new_mode = 0 if current_mode else 1
                param_states[(active_track, active_partial, mode_key)] = new_mode
                last_edited_label = short_on if new_mode else short_off
                last_edited_name = name_on if new_mode else name_off
                last_edited_val = None
                last_edited_text = last_edited_label
                current_line1 = build_edit_line1(last_edited_label, text=last_edited_text, name=last_edited_name)
                update_overlay()
            return

        if out_type == "cycle_sysex":
            if is_press:
                target_fields = clean_mapping[1:]
                long_name = get_configured_parameter_name(mapping, clean_mapping[3] if len(clean_mapping) > 3 else "Parameter")
                target = parse_target_fields(target_fields, long_name)
                if not target:
                    return
                offsets, max_value, label, size, value_list, text_map, long_name = target
                state_key = (active_preset, active_scene, lookup_key, active_track, active_partial)
                current_value = param_states.get(state_key, -1)
                if value_list:
                    try:
                        idx = value_list.index(current_value)
                    except ValueError:
                        idx = -1
                    f_val = value_list[(idx + 1) % len(value_list)]
                else:
                    f_val = (int(current_value) + 1) % (int(max_value) + 1)
                param_states[state_key] = f_val

                for offset in offsets:
                    address = get_mc101_address(active_track, active_partial, offset)
                    send_sysex(out_port, address, f_val, size)

                last_sysex_time = time.time()
                last_edited_label = label
                last_edited_name = long_name
                last_edited_val = f_val
                last_edited_text = text_map.get(f_val) if text_map else None
                current_line1 = build_edit_line1(label, value=last_edited_val, text=last_edited_text, name=last_edited_name)
                update_overlay()
            return

        if out_type == "track_select" and is_press:
            active_track = clean_mapping[1]
            last_edited_label = clean_mapping[2]
            last_edited_name = get_mapping_name(mapping, "Track")
            last_edited_val = None
            last_edited_text = clean_mapping[2]
            current_line1 = build_edit_line1(last_edited_label, text=last_edited_text, name=last_edited_name)
            update_overlay()
            return

        if out_type == "partial_select" and is_press:
            active_partial = clean_mapping[1]
            last_edited_label = clean_mapping[2]
            last_edited_name = get_mapping_name(mapping, "Partial")
            last_edited_val = None
            last_edited_text = clean_mapping[2]
            current_line1 = build_edit_line1(last_edited_label, text=last_edited_text, name=last_edited_name)
            update_overlay()
            return

        if out_type == "drum_scene_octave":
            if is_press:
                scene_number = active_scene
                direction = clean_mapping[2]
                current_offset = drum_scene_octave_offsets.get(scene_number, 0)
                drum_scene_octave_offsets[scene_number] = max(-60, min(60, current_offset + direction))
                last_edited_label = clean_mapping[3]
                last_edited_name = get_mapping_name(mapping, "Drum Octave")
                last_edited_val = None
                last_edited_text = get_drum_octave_label(scene_number)
                current_line1 = build_drum_octave_line1(scene_number)
                update_overlay()
            return

        if out_type == "drum_pad_key_select":
            pad_track = clean_mapping[1]
            base_pad_key = clean_mapping[2]
            pad_key = shifted_drum_key(base_pad_key)
            play_note = clamp_midi_note(pad_key)
            pad_label = drum_key_short_name(pad_key)

            if is_press:
                active_track = pad_track
                active_pad = pad_key
                last_edited_label = pad_label
                last_edited_name = drum_key_long_name(pad_key)
                last_edited_val = None
                last_edited_text = pad_label
                current_line1 = get_drum_edit_target_path()
                drum_pad_notes_held[lookup_key] = (active_track - 1, play_note)
                out_port.send(mido.Message("note_on", channel=active_track - 1, note=play_note, velocity=active_drum_velocity))
                update_overlay()
            else:
                held = drum_pad_notes_held.pop(lookup_key, (pad_track - 1, play_note))
                out_port.send(mido.Message("note_off", channel=held[0], note=held[1], velocity=0))
            return

        if out_type == "drum_pad_select":
            selected_pad = active_pad_bank * 4 + clean_mapping[1]
            pad_note = PAD_NOTES[selected_pad - 1]

            if is_press:
                active_pad = selected_pad
                last_edited_label = f"PD{selected_pad:02d}"
                last_edited_name = get_mapping_name(mapping, "Pad")
                last_edited_val = None
                last_edited_text = f"PD{selected_pad:02d}"
                current_line1 = build_edit_line1(last_edited_label, text=last_edited_text, name=last_edited_name)
                out_port.send(mido.Message("note_on", channel=active_track - 1, note=pad_note, velocity=val))
                update_overlay()
            else:
                out_port.send(mido.Message("note_off", channel=active_track - 1, note=pad_note, velocity=0))
            return

        if out_type == "drum_pad_bank" and is_press:
            active_pad_bank = (active_pad_bank + clean_mapping[1]) % 4
            last_edited_label = clean_mapping[2]
            last_edited_name = get_mapping_name(mapping, "Pad Bank")
            last_edited_val = None
            last_edited_text = clean_mapping[2]
            current_line1 = build_edit_line1(last_edited_label, text=last_edited_text, name=last_edited_name)
            update_overlay()
            return

        if out_type == "drum_pad_velocity":
            if msg.type == "control_change":
                active_drum_velocity = max(1, min(127, int(val)))
                last_edited_label = get_mapping_label(mapping)
                last_edited_name = get_mapping_name(mapping, "Pad Velocity")
                last_edited_val = active_drum_velocity
                last_edited_text = str(active_drum_velocity)
                current_line1 = build_edit_line1(last_edited_label, value=active_drum_velocity, name=last_edited_name)
                update_overlay()
            return

        if out_type in ["sysex", "conditional_sysex", "sysex_track", "dynamic_sysex_track", "conditional_sysex_track", "drum_sysex_partial"]:
            target_fields, target_name = get_target_fields(mapping, out_type)
            target = parse_target_fields(target_fields, target_name)

            if not target:
                return

            offsets, max_value, label, size, value_list, text_map, long_name = target
            now = time.time()

            if is_toggle or (now - last_sysex_time) > 0.08:
                if value_list:
                    f_val = value_list[int(round((val / 127.0) * (len(value_list) - 1)))]
                else:
                    f_val = int(round((val / 127.0) * max_value))

                state_context = f"P{active_pad}" if out_type == "drum_sysex_partial" else ("track" if is_track_level else active_partial)
                param_states[(active_track, state_context, lookup_key)] = f_val

                if out_type == "drum_sysex_partial" and not drum_key_is_editable(active_pad):
                    last_sysex_time = now
                    last_edited_label = label
                    last_edited_name = long_name
                    last_edited_val = None
                    last_edited_text = "---"
                    current_line1 = get_drum_edit_target_path()
                    update_overlay()
                    return

                for offset in offsets:
                    if out_type == "drum_sysex_partial":
                        address = get_drum_partial_address(active_track, active_pad, offset)
                    else:
                        address = get_mc101_address(active_track, 1 if is_track_level else active_partial, offset)

                    send_sysex(out_port, address, f_val, size)

                if label in ["BNK", "WNO"]:
                    send_sysex(out_port, get_mc101_address(active_track, active_partial, 0x1B), 0, 1)

                last_sysex_time = now
                last_edited_label = label
                last_edited_name = long_name
                last_edited_val = f_val
                last_edited_text = text_map.get(f_val) if text_map else None
                current_line1 = build_edit_line1(label, value=last_edited_val, text=last_edited_text, name=last_edited_name)
                update_overlay()
            return

        if out_type == "keyboard_velocity":
            if msg.type == "control_change":
                velocity = set_keyboard_velocity(val)
                last_edited_label = get_mapping_label(mapping)
                last_edited_name = get_mapping_name(mapping, "Velocity")
                last_edited_val = velocity
                last_edited_text = None
                current_line1 = build_edit_line1(last_edited_label, value=velocity, name=last_edited_name)
                update_overlay()
            return

        if out_type == "keyboard_octave":
            if is_press:
                octave = change_keyboard_octave(clean_mapping[1], clean_mapping[2])
                last_edited_label = get_mapping_label(mapping)
                last_edited_name = get_mapping_name(mapping)
                last_edited_val = octave
                last_edited_text = f"+{octave}"
                current_line1 = build_edit_line1(last_edited_label, text=last_edited_text, name=last_edited_name)
                update_overlay()
            return

        if out_type == "mc101_scene_bank":
            if is_press:
                active_mc101_scene_bank = clean_mapping[1]
                last_edited_label = get_mapping_label(mapping)
                last_edited_name = get_mapping_name(mapping)
                last_edited_val = None
                last_edited_text = f"{active_mc101_scene_bank + 1:02d}"
                current_line1 = f"{build_scene_line1()} > {last_edited_name}"
                update_overlay()
            return

        if out_type == "mc101_scene_select":
            if is_press:
                scene_index = clean_mapping[1]
                program = mc101_scene_program(scene_index)

                # Select the scene on the MC-101. The MC-101 does not echo
                # this generated Program Change back out, so pc2note.py cannot
                # convert it into an M8 row cue. Launch the matching M8 row here
                # as well.
                out_port.send(mido.Message("program_change", channel=MC101_CONTROL_CHANNEL, program=program))
                launch_m8_song_row(out_port, program)

                last_edited_label = mc101_scene_label(scene_index)
                last_edited_name = mc101_scene_name(scene_index)
                last_edited_val = program
                last_edited_text = f"PC {program}"
                current_line1 = f"{build_scene_line1()} > {last_edited_name}"
                update_overlay()
            return

        label = get_mapping_label(mapping)
        mapping_name = get_mapping_name(mapping, label)

        if out_type == "keyboard_note":
            played_note = send_keyboard_note(out_port, lookup_key, clean_mapping[1], clean_mapping[2], is_press)
            if is_press:
                mapping_name = midi_note_name(played_note)
        elif out_type == "m8_toggle_note":
            # M8 mute/solo commands are toggle actions. The nanoKONTROL matrix
            # buttons can report the second physical press as note_off/velocity 0,
            # so every incoming edge for this mapping sends one short note pulse.
            send_note_pulse(out_port, clean_mapping[1], clean_mapping[2])
        elif out_type == "note":
            out_port.send(mido.Message("note_on" if val > 0 else "note_off", channel=clean_mapping[1], note=clean_mapping[2], velocity=val))
        elif out_type == "note_pulse":
            if is_press:
                send_note_pulse(out_port, clean_mapping[1], clean_mapping[2])
            else:
                send_navigation_note_off(out_port, clean_mapping[1], clean_mapping[2])
        elif out_type == "m8_button":
            if is_press:
                send_m8_button_down(out_port, clean_mapping[1], clean_mapping[2])
            else:
                send_m8_button_up(out_port, clean_mapping[1], clean_mapping[2])
        elif out_type == "midi_transport":
            if is_press:
                command = clean_mapping[1]
                send_transport_message(transport_out_port, command)
        elif out_type == "cc":
            out_port.send(mido.Message("control_change", channel=clean_mapping[1], control=clean_mapping[2], value=val))

        if msg.type == "control_change" or is_press or is_toggle:
            last_edited_label = label
            last_edited_name = mapping_name
            last_edited_val = val if out_type == "cc" else None
            last_edited_text = None if out_type == "cc" else ("ON" if val > 0 else "OFF")
            current_line1 = build_edit_line1(label, value=last_edited_val, text=last_edited_text, name=last_edited_name)
            update_overlay()

    in_port.callback = midi_callback

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        if out_port is not None:
            cleanup_m8_song_row(out_port)
            release_all_keyboard_notes(out_port)
            release_all_navigation_notes(out_port)
        if in_port is not None:
            in_port.close()
        if out_port is not None:
            out_port.close()
        if transport_out_port is not None:
            transport_out_port.close()

if __name__ == "__main__":
    main()