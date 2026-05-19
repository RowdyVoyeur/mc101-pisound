#!/usr/bin/env python3
import sys
import time
import os
import mido
import threading

# --- CONFIGURATION ---
OVERLAY_PIPE = "/tmp/m8c_overlay"
M8_CHANNEL = 15  # MIDI channel 16 in mido's zero-based numbering.
MC101_CONTROL_CHANNEL = 12  # MIDI channel 13 in mido's zero-based numbering.
MC101_SCENE_BANK_COUNT = 8
MC101_SCENES_PER_BANK = 8

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

# --- VALUE MAPS ---
OSC_TYPE_LABELS = {0: "PCM", 1: "VA ", 2: "SYN", 3: "SAW", 4: "NOI"}
BANK_LABELS = {8: "A", 10: "B", 11: "C"}
VA_WAVE_LABELS = {0: "SAW", 1: "SQR", 2: "TRI", 3: "SIN", 4: "RMP", 5: "JUN", 6: "TR2", 7: "TR3", 8: "SI2"}
PWD_LABELS = {i: f"+{i-64}" if i > 64 else str(i-64) for i in range(1, 128)}
SYN_WAVE_LABELS = {i: f"{i+1:02d}" for i in range(48)}
CRS_LABELS = {i: f"+{i-64}" if i > 64 else str(i-64) for i in range(16, 113)}
FIN_LABELS = {i: f"+{i-64}" if i > 64 else str(i-64) for i in range(14, 115)}
PAN_LABELS = {i: f"R{i-64}" if i > 64 else (f"L{64-i}" if i < 64 else "C") for i in range(128)}
ST1_LABELS = {0: "OFF", 1: "SNC", 2: "RNG", 3: "XMD", 4: "XM2"}
TVF_TYP_LABELS = {0: "OFF", 1: "LPF", 2: "BPF", 3: "HPF", 4: "PKG", 5: "LP2", 6: "LP3"}
ENV_LABELS = {i: f"+{i-64}" if i > 64 else str(i-64) for i in range(1, 128)}
FILTER_TYPE_LABELS = {0: "TVF", 1: "VCF"}
SLP_LABELS = {0: "-12", 1: "-18", 2: "-24"}
KF_LABELS = {i: f"+{i-1024}" if i > 1024 else str(i-1024) for i in range(824, 1225)}

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

PRESETS = {
    PRESET_1: {
        "name": "M8 & MC-101",
        "context": "m8",
        "display_values": False,
        "scenes": {
            1: {
                "name": "CONTROLLER",
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
                    ("note", 0): named(("midi_transport", "stop", "STOP", "MST"), "MC-101 Stop"),
                    ("note", 9): named(("midi_transport", "start", "START", "MPL"), "MC-101 Play"),
                }
            }
        }
    },
    PRESET_2: {
        "name": "M8",
        "context": "none",
        "display_values": False,
        "scenes": {
            1: {
                "name": "MIXER",
                "mappings": {

                    ("cc", 0): named(("cc", M8_CHANNEL, 1, "001"), "CC 001"),
                    ("cc", 1): named(("cc", M8_CHANNEL, 2, "002"), "CC 002"),
                    ("note", 0): named(("note", M8_CHANNEL, 12, "toggle", "M01"), "M8 Macro 01"),
                    ("note", 1): named(("note", M8_CHANNEL, 13, "toggle", "M02"), "M8 Macro 02"),

                }
            }
        }
    },
    PRESET_3: {
        "name": "EMPTY",
        "context": "none",
        "display_values": False,
        "scenes": {1: {"name": "EMPTY", "mappings": {}}}
    },
    PRESET_4: {
        "name": "EMPTY",
        "context": "none",
        "display_values": False,
        "scenes": {1: {"name": "EMPTY", "mappings": {}}}
    },
PRESET_5: {
        "name": "MC-101",
        "context": "track",
        "default_track": 2,
        "display_values": True,
        "scenes": {
            1: {
                "name": "TRACK 2",
                "mappings": {
                    ("cc", 0): named(("cc", 1, 74, "CUT"), "Cutoff"),
                    ("cc", 1): named(("cc", 1, 71, "RES"), "Resonance"),
                }
            }
        }
    },
    PRESET_6: {
        "name": "MC-101",
        "context": "drum",
        "default_track": 1,
        "display_values": True,
        "scenes": {
            1: {
                "name": "DRUM TRACK",
                "mappings": {
                    ("note", 0): named(("track_select", 1, "T01"), "Track"),
                    ("note", 1): named(("track_select", 2, "T02"), "Track"),
                    ("note", 2): named(("track_select", 3, "T03"), "Track"),
                    ("note", 3): named(("track_select", 4, "T04"), "Track"),
                    ("note", 5): named(("drum_pad_select", 1), "Pad"),
                    ("note", 6): named(("drum_pad_select", 2), "Pad"),
                    ("note", 7): named(("drum_pad_select", 3), "Pad"),
                    ("note", 8): named(("drum_pad_select", 4), "Pad"),
                    ("note", 16): named(("drum_pad_bank", -1, "B-1"), "Pad Bank"),
                    ("note", 17): named(("drum_pad_bank", 1, "B+1"), "Pad Bank"),
                    ("cc", 5): named(("drum_sysex_partial", 0x0009, 127, "LEV", 1), "Level"),
                    ("cc", 6): named(("drum_sysex_partial", 0x000A, 127, "PAN", 1, None, PAN_LABELS), "Pan"),
                    ("cc", 7): named(("drum_sysex_partial", 0x000B, 127, "CHO", 1), "Chorus Send"),
                    ("cc", 8): named(("drum_sysex_partial", 0x000C, 127, "REV", 1), "Reverb Send"),
                }
            }
        }
    },
    PRESET_7: {
        "name": "MC-101",
        "context": "partial",
        "default_track": 1,
        "display_values": True,
        "scenes": {
            1: {
                "name": "OSC & COM",
                "mappings": {
                    ("cc", 0): named(("sysex", 0x3E00, 4, "OTY", 1, OSC_TYPE_LABELS), "Oscillator Type"),
                    ("cc", 1): ("conditional_sysex", ("cc", 0), {
                        0: named((None, 0, "---", 1), "Unavailable"),
                        1: named((0x3E01, 8, "WAV", 1, None, VA_WAVE_LABELS), "Wave"),
                        2: named((None, 0, "---", 1), "Unavailable"),
                        3: named((None, 0, "---", 1), "Unavailable")
                    }),
                    ("cc", 2): ("conditional_sysex", ("cc", 0), {
                        0: named(([0x201C, 0x2034], 2, "BNK", 4, [8, 10, 11], BANK_LABELS), "Bank"),
                        1: named((0x3E06, 127, "PW ", 1), "Pulse Width"),
                        2: named((0x3E02, 47, "WAV", 4, None, SYN_WAVE_LABELS), "Wave"),
                        3: named((0x3E08, 127, "DET", 1), "Detune")
                    }),
                    ("cc", 3): ("conditional_sysex", ("cc", 0), {
                        0: ("bank_dependent", {
                            8: named(([0x2020, 0x2038], 963, "WAV", 4), "Wave"),
                            10: named(([0x2020, 0x2038], 257, "WAV", 4), "Wave"),
                            11: named(([0x2020, 0x2038], 620, "WAV", 4), "Wave")
                        }),
                        1: named((0x3E07, 126, "PWD", 1, list(range(1, 128)), PWD_LABELS), "Pulse Width Depth"),
                        2: named((None, 0, "---", 1), "Unavailable"),
                        3: named((None, 0, "---", 1), "Unavailable")
                    }),
                    ("cc", 4): named(("sysex_track", 0x3D00, 4, "ST1", 1, ST1_LABELS), "Structure 1"),
                    ("cc", 5): ("conditional_sysex_track", ("cc", 4), {
                        0: named((None, 0, "---", 1), "Unavailable"),
                        1: named((None, 0, "---", 1), "Unavailable"),
                        2: named((0x3D02, 127, "RNG", 1), "Ring Mod Range"),
                        3: named((0x3D08, 10800, "MOD", 4), "Modulation"),
                        4: named((0x3D15, 127, "MOD", 1), "Modulation")
                    }),
                    ("cc", 13): ("conditional_sysex_track", ("cc", 4), {
                        0: named((None, 0, "---", 1), "Unavailable"),
                        1: named((None, 0, "---", 1), "Unavailable"),
                        2: named((0x3D04, 127, "LV1", 1), "Level 1"),
                        3: named((0x3D10, 127, "LV1", 1), "Level 1"),
                        4: named((0x3D10, 127, "LV1", 1), "Level 1")
                    }),
                    ("cc", 14): ("conditional_sysex_track", ("cc", 4), {
                        0: named((None, 0, "---", 1), "Unavailable"),
                        1: named((None, 0, "---", 1), "Unavailable"),
                        2: named((0x3D05, 127, "LV2", 1), "Level 2"),
                        3: named((0x3D11, 127, "LV2", 1), "Level 2"),
                        4: named((0x3D11, 127, "LV2", 1), "Level 2")
                    }),
                    ("cc", 6): named(("sysex_track", 0x3D01, 4, "ST3", 1, ST1_LABELS), "Structure 3"),
                    ("cc", 7): ("conditional_sysex_track", ("cc", 6), {
                        0: named((None, 0, "---", 1), "Unavailable"),
                        1: named((None, 0, "---", 1), "Unavailable"),
                        2: named((0x3D03, 127, "RNG", 1), "Ring Mod Range"),
                        3: named((0x3D0C, 10800, "MOD", 4), "Modulation"),
                        4: named((0x3D16, 127, "MOD", 1), "Modulation")
                    }),
                    ("cc", 15): ("conditional_sysex_track", ("cc", 6), {
                        0: named((None, 0, "---", 1), "Unavailable"),
                        1: named((None, 0, "---", 1), "Unavailable"),
                        2: named((0x3D06, 127, "LV3", 1), "Level 3"),
                        3: named((0x3D12, 127, "LV3", 1), "Level 3"),
                        4: named((0x3D12, 127, "LV3", 1), "Level 3")
                    }),
                    ("cc", 16): ("conditional_sysex_track", ("cc", 6), {
                        0: named((None, 0, "---", 1), "Unavailable"),
                        1: named((None, 0, "---", 1), "Unavailable"),
                        2: named((0x3D07, 127, "LV4", 1), "Level 4"),
                        3: named((0x3D13, 127, "LV4", 1), "Level 4"),
                        4: named((0x3D13, 127, "LV4", 1), "Level 4")
                    }),
                    ("cc", 8): named(("sysex_track", 0x001C, 127, "ANL", 1), "Analog Feel"),
                    ("cc", 17): named(("sysex_track", 0x0024, 1023, "TIM", 4), "Portamento Time"),
                    ("note", 8): named(("sysex_track", 0x001D, 1, "M/P", 1, {0: "MNO", 1: "PLY"}, "toggle"), "Mono/Poly"),
                    ("note", 16): named(("sysex_track", 0x0021, 1, "PRM", 1, {0: "NRM", 1: "LGT"}, "toggle"), "Portamento Mode"),
                    ("note", 17): named(("sysex_track", 0x0020, 1, "PRT", 1, {0: "OFF", 1: "ON"}, "toggle"), "Portamento"),
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
                "name": "FIL & ENV",
                "mappings": {
                    ("cc", 18): named(("sysex", 0x2031, 6, "TYP", 1, TVF_TYP_LABELS), "Filter Type"),
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
                    ("note", 18): named(("track_select", 1, "T01"), "Track"),
                    ("note", 19): named(("track_select", 2, "T02"), "Track"),
                    ("note", 20): named(("track_select", 3, "T03"), "Track"),
                    ("note", 21): named(("track_select", 4, "T04"), "Track"),
                    ("note", 27): named(("partial_select", 1, "P01"), "Partial"),
                    ("note", 28): named(("partial_select", 2, "P02"), "Partial"),
                    ("note", 29): named(("partial_select", 3, "P03"), "Partial"),
                    ("note", 30): named(("partial_select", 4, "P04"), "Partial"),
                    ("note", 31): named(("dynamic_sysex_track", {1: 0x1002, 2: 0x100B, 3: 0x1014, 4: 0x101D}, 1, "PSW", 1, {0: "OFF", 1: "ON"}, "toggle"), "Partial Switch"),
                }
            }
        }
    },
    PRESET_8: {
        "name": "MC-101",
        "context": "none",
        "display_values": True,
        "scenes": {
            1: {
                "name": "SCENES",
                "mappings": {
                    # Scene trigger buttons. The selected bank decides which
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

                    # Scene bank selectors. A-1 selects Scene Bank 01,
                    # A#-1 selects Scene Bank 02, through E0 = Scene Bank 08.
                    ("note", 9): named(("mc101_scene_bank", 0), "Scene Bank 01"),
                    ("note", 10): named(("mc101_scene_bank", 1), "Scene Bank 02"),
                    ("note", 11): named(("mc101_scene_bank", 2), "Scene Bank 03"),
                    ("note", 12): named(("mc101_scene_bank", 3), "Scene Bank 04"),
                    ("note", 13): named(("mc101_scene_bank", 4), "Scene Bank 05"),
                    ("note", 14): named(("mc101_scene_bank", 5), "Scene Bank 06"),
                    ("note", 15): named(("mc101_scene_bank", 6), "Scene Bank 07"),
                    ("note", 16): named(("mc101_scene_bank", 7), "Scene Bank 08"),

                    # MC-101 transport controls.
                    # MIDI note numbers use C-1 = 0:
                    #   G#-1 = 8  -> MIDI Stop
                    #   F0  = 17 -> MIDI Start
                    ("note", 8): named(("midi_transport", "stop", "STOP", "STP"), "STOP"),
                    ("note", 17): named(("midi_transport", "start", "START", "PLA"), "PLAY"),
                }
            }
        }
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
    pad_key = PAD_NOTES[pad - 1]
    pad_offset_int = to_7bit_int(0x001600) + (pad_key - 21) * 128
    return add_roland_address(base, to_7bit_hex(pad_offset_int), param_offset)

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

def get_edit_target_path(preset_name):
    preset_data = PRESETS.get(active_preset, {})
    context = preset_data.get("context", "none")
    parts = [preset_name]

    if context in ("track", "partial", "drum"):
        parts.append(f"T{active_track:02d}")

    if context == "partial":
        parts.append(f"P{active_partial:02d}")
    elif context == "drum":
        parts.append(f"PD{active_pad:02d}")

    return " > ".join(parts)

def build_preset_line1():
    return PRESETS.get(active_preset, {}).get("name", "NONE")

def build_scene_line1():
    preset_data = PRESETS.get(active_preset, {})
    scene_data = preset_data.get("scenes", {}).get(active_scene, {})
    return f"{preset_data.get('name', 'NONE')} > {scene_data.get('name', f'S{active_scene}')}"

def mc101_scene_program(scene_index):
    return active_mc101_scene_bank * MC101_SCENES_PER_BANK + scene_index

def mc101_scene_label(scene_index):
    return f"S{active_mc101_scene_bank + 1}{scene_index + 1}"

def mc101_scene_name(scene_index):
    return f"Scene {active_mc101_scene_bank + 1:02d}-{scene_index + 1:02d}"

def mc101_scene_bank_label(bank_index):
    return f"B{bank_index + 1:02d}"

def mc101_scene_bank_name(bank_index):
    return f"Scene Bank {bank_index + 1:02d}"

def build_edit_line1(label=None, value=None, text=None, name=None):
    preset_name = PRESETS.get(active_preset, {}).get("name", "NONE")
    parameter_name = name or last_edited_name or label or "Parameter"
    value_text = get_value_text(value=value, text=text)
    base = get_edit_target_path(preset_name)

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
    if out_type == "drum_pad_select":
        return f"PD{(active_pad_bank * 4 + clean_mapping[1]):02d}"
    if out_type == "drum_pad_bank":
        return clean_mapping[2]

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
    active_pad = 1
    active_pad_bank = 0
    active_mc101_scene_bank = 0

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

# --- MAIN MIDI ROUTER ---
def main():
    global active_scene, active_track, active_partial, active_pad, active_pad_bank, active_mc101_scene_bank
    global last_edited_label, last_edited_name, last_edited_val, last_edited_text
    global last_sysex_time, last_touched_type, last_interaction_time, current_line1

    try:
        in_port = mido.open_input("In", virtual=True, client_name="nanoRouterIN")
        out_port = mido.open_output("Out", virtual=True, client_name="nanoRouterOUT")
    except Exception as exc:
        sys.exit(f"Failed: {exc}")

    if out_port is not None:
        release_all_navigation_notes(out_port)
    current_line1 = build_preset_line1()
    update_overlay()

    def midi_callback(msg):
        global active_scene, active_track, active_partial, active_pad, active_pad_bank, active_mc101_scene_bank
        global last_edited_label, last_edited_name, last_edited_val, last_edited_text
        global last_sysex_time, last_touched_type, last_interaction_time, current_line1

        if msg.type == "sysex" and msg.data[:8] == (66, 75, 0, 1, 4, 0, 95, 79):
            active_scene = msg.data[8] + 1
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
                out_port.send(mido.Message("program_change", channel=MC101_CONTROL_CHANNEL, program=program))
                last_edited_label = mc101_scene_label(scene_index)
                last_edited_name = mc101_scene_name(scene_index)
                last_edited_val = program
                last_edited_text = f"PC {program}"
                current_line1 = f"{build_scene_line1()} > {last_edited_name}"
                update_overlay()
            return

        label = get_mapping_label(mapping)
        mapping_name = get_mapping_name(mapping, label)

        if out_type == "note":
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
                if command == "start":
                    out_port.send(mido.Message("start"))
                elif command == "stop":
                    out_port.send(mido.Message("stop"))
                else:
                    print(f"Unknown MIDI transport command: {command}")
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
            release_all_navigation_notes(out_port)
        in_port.close()
        out_port.close()

if __name__ == "__main__":
    main()