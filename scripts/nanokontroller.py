#!/usr/bin/env python3
import sys, time, os, mido
import threading

# --- CONFIGURATION ---
OVERLAY_PIPE = "/tmp/m8c_overlay"

# Transport Buttons
PRESET_1 = 127 # Rewind
PRESET_4 = 124 # Loop
PRESET_5 = 123 # Play
PRESET_6 = 122 # Rec

# Global State
active_preset = PRESET_1
active_scene = 1
active_track = 1
active_partial = 1
active_pad = 1
active_wave = 1
active_pad_bank = 0

last_edited_label = None
last_edited_val = None
last_edited_text = None  
last_sysex_time = 0
last_interaction_time = 0
last_touched_type = "cc" 
toggle_states = {}  
param_states = {}  

# --- VALUE MAPS ---
OSC_TYPE_LABELS = {0: "PCM", 1: "VA ", 2: "SYN", 3: "SAW", 4: "NOI"}
BANK_LABELS = {8: "A", 10: "B", 11: "C"}
VA_WAVE_LABELS = {0:"SAW", 1:"SQR", 2:"TRI", 3:"SIN", 4:"RMP", 5:"JUN", 6:"TR2", 7:"TR3", 8:"SI2"}
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
WAVE_TYPE_LABELS = {0: "INT", 1: "EXP", 2: "SMP"}

PAD_NOTES = [37, 39, 42, 46, 49, 51, 54, 56, 36, 38, 41, 45, 48, 62, 63, 64]

PRESETS = {
    PRESET_1: {
        "name": "M8",
        "display_values": False, 
        "scenes": {
            1: {
                "name": "MIXER",
                "mappings": {
                    ("cc", 0): ("cc", 15, 1, "001"),
                    ("cc", 1): ("cc", 15, 2, "002"),
                    ("note", 0): ("note", 15, 12, "toggle", "M01"),
                    ("note", 1): ("note", 15, 13, "toggle", "M02"),
                }    
            }
        }
    },
    PRESET_4: {
        "name": "MC-101",
        "display_values": True, 
        "scenes": {
            1: {
                "name": "TRACK 2",
                "mappings": {
                    ("cc", 0): ("cc", 1, 74, "CUT"),
                    ("cc", 1): ("cc", 1, 71, "RES"),
                }    
            }
        }
    },
    PRESET_5: {
        "name": "MC-101",
        "display_values": True, 
        "scenes": {
            1: {
                "name": "DRUM TRACK",
                "mappings": {
                    ("note", 0): ("track_select", 1, "T01"),
                    ("note", 1): ("track_select", 2, "T02"),
                    ("note", 2): ("track_select", 3, "T03"),
                    ("note", 3): ("track_select", 4, "T04"),
                    ("note", 5): ("drum_pad_select", 1),
                    ("note", 6): ("drum_pad_select", 2),
                    ("note", 7): ("drum_pad_select", 3),
                    ("note", 8): ("drum_pad_select", 4),
                    ("note", 16): ("drum_pad_bank", -1, "B-1"),
                    ("note", 17): ("drum_pad_bank", 1, "B+1"),
                    ("note", 9):  ("drum_wave_select", 1, "W1"),
                    ("note", 10): ("drum_wave_select", 2, "W2"),
                    ("note", 11): ("drum_wave_select", 3, "W3"),
                    ("note", 12): ("drum_wave_select", 4, "W4"),
                    ("note", 13): ("drum_sysex_inst", {1: 0x001D, 2: 0x0040, 3: 0x0063, 4: 0x0106}, 1, "WSW", 1, {0: "OFF", 1: "ON"}, "toggle"),
                    ("cc", 0): ("drum_sysex_inst", {1: 0x001E, 2: 0x0041, 3: 0x0064, 4: 0x0107}, 2, "WTY", 1, WAVE_TYPE_LABELS),
                    ("cc", 1): ("drum_sysex_inst", {1: 0x001F, 2: 0x0042, 3: 0x0065, 4: 0x0108}, 16383, "WID", 4),
                    ("cc", 5): ("drum_sysex_partial", 0x0009, 127, "LEV", 1),
                    ("cc", 6): ("drum_sysex_partial", 0x000A, 127, "PAN", 1, None, PAN_LABELS),
                    ("cc", 7): ("drum_sysex_partial", 0x000B, 127, "CHO", 1),
                    ("cc", 8): ("drum_sysex_partial", 0x000C, 127, "REV", 1),
                }
            }
        }
    },
    PRESET_6: {
        "name": "MC-101",
        "display_values": True, 
        "scenes": {
            1: {
                "name": "OSC & COM",
                "mappings": {
                    ("cc", 0): ("sysex", 0x3E00, 4, "OTY", 1, OSC_TYPE_LABELS),       
                    ("cc", 1): ("conditional_sysex", ("cc", 0), {
                        0: (None, 0, "---", 1),              
                        1: (0x3E01, 8, "WAV", 1, None, VA_WAVE_LABELS),
                        2: (None, 0, "---", 1),  
                        3: (None, 0, "---", 1)   
                    }),
                    ("cc", 2): ("conditional_sysex", ("cc", 0), {
                        0: ([0x201C, 0x2034], 2, "BNK", 4, [8, 10, 11], BANK_LABELS), 
                        1: (0x3E06, 127, "PW ", 1),
                        2: (0x3E02, 47, "WAV", 4, None, SYN_WAVE_LABELS),  
                        3: (0x3E08, 127, "DET", 1) 
                    }),
                    ("cc", 3): ("conditional_sysex", ("cc", 0), {
                        0: ("bank_dependent", {
                             8: ([0x2020, 0x2038], 963, "WAV", 4),
                            10: ([0x2020, 0x2038], 257, "WAV", 4),
                            11: ([0x2020, 0x2038], 620, "WAV", 4)
                        }),
                        1: (0x3E07, 126, "PWD", 1, list(range(1, 128)), PWD_LABELS),
                        2: (None, 0, "---", 1),  
                        3: (None, 0, "---", 1)   
                    }),
                    ("cc", 4): ("sysex_track", 0x3D00, 4, "ST1", 1, ST1_LABELS),
                    ("cc", 5): ("conditional_sysex_track", ("cc", 4), {
                        0: (None, 0, "---", 1),
                        1: (None, 0, "---", 1),
                        2: (0x3D02, 127, "RNG", 1),           
                        3: (0x3D08, 10800, "MOD", 4),         
                        4: (0x3D15, 127, "MOD", 1)            
                    }),
                    ("cc", 13): ("conditional_sysex_track", ("cc", 4), {
                        0: (None, 0, "---", 1),
                        1: (None, 0, "---", 1),
                        2: (0x3D04, 127, "LV1", 1),           
                        3: (0x3D10, 127, "LV1", 1),           
                        4: (0x3D10, 127, "LV1", 1)            
                    }),
                    ("cc", 14): ("conditional_sysex_track", ("cc", 4), {
                        0: (None, 0, "---", 1),
                        1: (None, 0, "---", 1),
                        2: (0x3D05, 127, "LV2", 1),           
                        3: (0x3D11, 127, "LV2", 1),           
                        4: (0x3D11, 127, "LV2", 1)            
                    }),
                    ("cc", 6): ("sysex_track", 0x3D01, 4, "ST3", 1, ST1_LABELS),
                    ("cc", 7): ("conditional_sysex_track", ("cc", 6), {
                        0: (None, 0, "---", 1),
                        1: (None, 0, "---", 1),
                        2: (0x3D03, 127, "RNG", 1),           
                        3: (0x3D0C, 10800, "MOD", 4),         
                        4: (0x3D16, 127, "MOD", 1)            
                    }),
                    ("cc", 15): ("conditional_sysex_track", ("cc", 6), {
                        0: (None, 0, "---", 1),
                        1: (None, 0, "---", 1),
                        2: (0x3D06, 127, "LV3", 1),           
                        3: (0x3D12, 127, "LV3", 1),           
                        4: (0x3D12, 127, "LV3", 1)            
                    }),
                    ("cc", 16): ("conditional_sysex_track", ("cc", 6), {
                        0: (None, 0, "---", 1),
                        1: (None, 0, "---", 1),
                        2: (0x3D07, 127, "LV4", 1),           
                        3: (0x3D13, 127, "LV4", 1),           
                        4: (0x3D13, 127, "LV4", 1)            
                    }),
                    ("cc", 8): ("sysex_track", 0x001C, 127, "ANL", 1), 
                    ("cc", 17): ("sysex_track", 0x0024, 1023, "TIM", 4), 
                    ("note", 8): ("sysex_track", 0x001D, 1, "M/P", 1, {0: "MNO", 1: "PLY"}, "toggle"),
                    ("note", 16): ("sysex_track", 0x0021, 1, "PRM", 1, {0: "NRM", 1: "LGT"}, "toggle"),
                    ("note", 17): ("sysex_track", 0x0020, 1, "PRT", 1, {0: "OFF", 1: "ON"}, "toggle"),
                    ("note", 7): ("sysex_track", 0x3C00, 1, "UNS", 1, {0: "OFF", 1: "ON"}, "toggle"),
                    ("cc", 9): ("sysex", 0x2001, 96, "CRS", 1, list(range(16, 113)), CRS_LABELS),
                    ("cc", 10): ("sysex", 0x2002, 100, "FIN", 1, list(range(14, 115)), FIN_LABELS),
                    ("cc", 11): ("sysex", 0x2000, 127, "LEV", 1), 
                    ("cc", 12): ("sysex", 0x2007, 127, "PAN", 1, None, PAN_LABELS),
                    ("note", 0): ("track_select", 1, "T01"),
                    ("note", 1): ("track_select", 2, "T02"),
                    ("note", 2): ("track_select", 3, "T03"),
                    ("note", 3): ("track_select", 4, "T04"),
                    ("note", 4): ("conditional_sysex_track", ("cc", 4), {
                        0: (None, 0, "---", 1), 1: (None, 0, "---", 1), 2: (None, 0, "---", 1),
                        3: (0x3D14, 1, "LCK", 1, None, {0: "OFF", 1: "ON"}),
                        4: (0x3D14, 1, "LCK", 1, None, {0: "OFF", 1: "ON"}),
                    }, "toggle"),
                    ("note", 6): ("conditional_sysex_track", ("cc", 6), {
                        0: (None, 0, "---", 1), 1: (None, 0, "---", 1), 2: (None, 0, "---", 1),
                        3: (0x3D14, 1, "LCK", 1, None, {0: "OFF", 1: "ON"}),
                        4: (0x3D14, 1, "LCK", 1, None, {0: "OFF", 1: "ON"}),
                    }, "toggle"),
                    ("note", 9): ("partial_select", 1, "P01"),
                    ("note", 10): ("partial_select", 2, "P02"),
                    ("note", 11): ("partial_select", 3, "P03"),
                    ("note", 12): ("partial_select", 4, "P04"),
                    ("note", 13): ("dynamic_sysex_track", {1: 0x1002, 2: 0x100B, 3: 0x1014, 4: 0x101D}, 1, "PSW", 1, {0: "OFF", 1: "ON"}, "toggle"),
                }
            },
            2: {
                "name": "FIL & ENV",
                "mappings": {
                    ("cc", 18): ("sysex", 0x2031, 6, "TYP", 1, TVF_TYP_LABELS),
                    ("cc", 19): ("sysex", 0x2032, 1023, "CUT", 4),
                    ("cc", 20): ("sysex", 0x203D, 1023, "RES", 4),
                    ("cc", 21): ("sysex", 0x2800, 126, "ENV", 1, list(range(1, 128)), ENV_LABELS),
                    ("cc", 22): ("sysex", 0x3E0E, 1, "FLT", 1, FILTER_TYPE_LABELS),
                    ("cc", 23): ("sysex", 0x2036, 400, "KF ", 4, list(range(824, 1225)), KF_LABELS),
                    ("cc", 24): ("sysex", 0x3E0F, 2, "SLP", 1, SLP_LABELS),
                    ("cc", 25): ("conditional_sysex", ("cc", 22), {0: (None, 0, "---", 1), 1: (0x3E0A, 1023, "HPF", 4)}),
                    ("note", 18): ("track_select", 1, "T01"),
                    ("note", 19): ("track_select", 2, "T02"),
                    ("note", 20): ("track_select", 3, "T03"),
                    ("note", 21): ("track_select", 4, "T04"),
                    ("note", 27): ("partial_select", 1, "P01"),
                    ("note", 28): ("partial_select", 2, "P02"),
                    ("note", 29): ("partial_select", 3, "P03"),
                    ("note", 30): ("partial_select", 4, "P04"),
                    ("note", 31): ("dynamic_sysex_track", {1: 0x1002, 2: 0x100B, 3: 0x1014, 4: 0x101D}, 1, "PSW", 1, {0: "OFF", 1: "ON"}, "toggle"),
                }
            }
        }
    }
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
    for off in offsets: val += to_7bit_int(off)
    return to_7bit_hex(val)

def compute_checksum(payload):
    return (128 - (sum(payload) % 128)) % 128

def send_sysex(out_port, address, value, size):
    DEVICE_ID, MODEL_ID = 0x10, [0x00, 0x00, 0x00, 0x5E]
    header = [0x41, DEVICE_ID] + MODEL_ID + [0x12]
    addr_bytes = [(address >> 24) & 0x7F, (address >> 16) & 0x7F, (address >> 8) & 0x7F, address & 0x7F]
    if size == 4: data_bytes = [(value >> 12) & 0x0F, (value >> 8) & 0x0F, (value >> 4) & 0x0F, value & 0x0F]
    elif size == 2: data_bytes = [(value >> 7) & 0x7F, value & 0x7F]
    else: data_bytes = [value & 0x7F]
    payload = addr_bytes + data_bytes
    sysex_data = header + payload + [compute_checksum(payload)]
    out_port.send(mido.Message('sysex', data=sysex_data))

# --- ADDRESS GENERATORS ---
def get_mc101_address(track, partial, param_offset):
    track_bases = {1: 0x30200000, 2: 0x30420000, 3: 0x30640000, 4: 0x31060000}
    base = track_bases.get(track, 0x30200000)
    partial_offset_int = (partial - 1) * 128
    return add_roland_address(base, to_7bit_hex(partial_offset_int), param_offset)

def get_drum_partial_address(track, pad, param_offset):
    # Verified Drum Bases: Track 1 (32 40 00 00), Track 2 (32 73 00 00)
    # Calculated Gap: 0x33 in the second byte.
    drum_bases = {1: 0x32400000, 2: 0x32730000, 3: 0x33260000, 4: 0x33590000}
    base = drum_bases.get(track, 0x32400000)
    pad_key = PAD_NOTES[pad - 1]
    # Spacing is 0x0100 (128 bytes). Key 21 starts at 0x1600.
    # Logic: Note 37 (C#1) = 37-21 = 16. Offset = 0x1600 + (16 * 128) = 0x2600.
    pad_offset_int = to_7bit_int(0x001600) + (pad_key - 21) * 128
    return add_roland_address(base, to_7bit_hex(pad_offset_int), param_offset)

def get_drum_inst_address(track, pad, param_offset):
    # Verified Bases used for Inst section as well.
    drum_bases = {1: 0x32400000, 2: 0x32730000, 3: 0x33260000, 4: 0x33590000}
    base = drum_bases.get(track, 0x32400000)
    pad_key = PAD_NOTES[pad - 1]
    # Spacing for Inst is 0x0200 (256 bytes). Key 21 starts at 0x010000.
    pad_offset_int = to_7bit_int(0x010000) + (pad_key - 21) * 256
    return add_roland_address(base, to_7bit_hex(pad_offset_int), param_offset)

def get_mapping_label(m):
    if not m: return "---"
    out_type = m[0]
    if out_type in ["conditional_sysex", "conditional_sysex_track"]:
        cond_val = param_states.get((active_track, 'track', m[1]), param_states.get((active_track, active_partial, m[1]), 0))
        target = m[2].get(cond_val)
        if target:
            if target[0] == "bank_dependent":
                bank_val = param_states.get((active_track, 'track', ("cc", 2)), param_states.get((active_track, active_partial, ("cc", 2)), 8))
                res = target[1].get(bank_val)
                return res[2] if res else "---"
            return target[2]
        return "---"
    elif out_type in ["track_select", "partial_select"]: return m[2]
    elif out_type in ["drum_sysex_partial", "drum_sysex_inst"]: return m[3]
    elif out_type == "drum_pad_select": return f"PD{(active_pad_bank * 4 + m[1]):02d}"
    elif out_type in ["drum_pad_bank", "drum_wave_select"]: return m[2]
    for item in m[3:]:
        if isinstance(item, str) and item != "toggle": return item
    return "---"

def schedule_matrix_swap(p_num, s_num, t_time):
    time.sleep(2.5)
    if active_preset == p_num and active_scene == s_num and last_interaction_time <= t_time:
        global last_touched_type
        last_touched_type = "note"; update_overlay()

def clear_overlay():
    if os.path.exists(OVERLAY_PIPE):
        try:
            fd = os.open(OVERLAY_PIPE, os.O_WRONLY | os.O_NONBLOCK)
            os.write(fd, b" \n"); os.close(fd)
        except: pass

def update_overlay():
    preset_data = PRESETS.get(active_preset, {})
    scene_data = preset_data.get("scenes", {}).get(active_scene, {})
    disp_vals, s_name, p_name = preset_data.get("display_values", True), scene_data.get("name", f"S{active_scene}"), preset_data.get('name', 'NONE')
    tr_str = f"T{active_track:02d}"
    if active_preset == PRESET_6:
        pa_str = f"P{active_partial:02d}"
        l1 = f"{p_name} > {s_name} > {tr_str} > {pa_str} > {last_edited_label} {last_edited_text or (last_edited_val if last_edited_val is not None else '')}" if disp_vals else f"{p_name} > {s_name} > {tr_str} > {pa_str}"
    elif active_preset == PRESET_5:
        l1 = f"{p_name} > {s_name} > {tr_str} > PD{active_pad:02d} > W{active_wave} > {last_edited_label} {last_edited_text or (last_edited_val if last_edited_val is not None else '')}" if disp_vals else f"{p_name} > {s_name} > {tr_str} > PD{active_pad:02d} > W{active_wave}"
    else:
        l1 = f"{p_name} > {s_name} > {last_edited_label} {last_edited_text or (last_edited_val if last_edited_val is not None else '')}" if disp_vals else f"{p_name} > {s_name} "
    
    mappings, all_labels, offset = scene_data.get("mappings", {}), [], (active_scene - 1) * 18
    for i in range(18):
        key = (last_touched_type, i + offset)
        label = get_mapping_label(mappings.get(key))
        core_str = ">X<" if label == last_edited_label else str(label).strip()[:3].upper().ljust(3, " ")
        all_labels.append(core_str)

    sep = " | " if last_touched_type == "cc" else " : "
    overlay_text = f"{l1.ljust(45)}~{sep.join(all_labels[:9]).ljust(55)}~{sep.join(all_labels[9:18]).ljust(55)}\n"
    if os.path.exists(OVERLAY_PIPE):
        try:
            fd = os.open(OVERLAY_PIPE, os.O_WRONLY | os.O_NONBLOCK)
            os.write(fd, overlay_text.encode()); os.close(fd)
        except: pass

def main():
    global active_preset, active_scene, active_track, active_partial, active_pad, active_wave, active_pad_bank
    global last_edited_label, last_edited_val, last_edited_text, last_sysex_time, toggle_states, param_states, last_touched_type, last_interaction_time
    try:
        in_port = mido.open_input('In', virtual=True, client_name='nanoRouterIN')
        out_port = mido.open_output('Out', virtual=True, client_name='nanoRouterOUT')
    except Exception as e: sys.exit(f"Failed: {e}")
    update_overlay()

    def midi_callback(msg):
        global active_preset, active_scene, active_track, active_partial, active_pad, active_wave, active_pad_bank
        global last_edited_label, last_edited_val, last_edited_text, last_sysex_time, toggle_states, param_states, last_touched_type, last_interaction_time
        if msg.type == 'sysex' and msg.data[:8] == (66, 75, 0, 1, 4, 0, 95, 79):
            active_scene = msg.data[8] + 1; update_overlay(); return
        if msg.type == 'control_change' and msg.control in PRESETS:
            if msg.value > 0:
                active_preset = msg.control
                p_info, last_edited_label, last_edited_val, last_edited_text = PRESETS.get(active_preset, {}), None, None, None
                t_trigger = time.time(); last_interaction_time = t_trigger
                if not p_info.get("display_values", True):
                    last_touched_type = "cc"
                    threading.Thread(target=schedule_matrix_swap, args=(active_preset, active_scene, t_trigger), daemon=True).start()
                update_overlay(); return
        if msg.type == 'control_change': lookup_key, val, last_touched_type = ("cc", msg.control), msg.value, "cc"
        elif msg.type in ['note_on', 'note_off']: lookup_key, val, last_touched_type = ("note", msg.note), getattr(msg, 'velocity', 0), "note"
        else: return
        is_press = (val > 0 if msg.type != 'note_off' else False)
        last_interaction_time = time.time()
        p_info = PRESETS.get(active_preset, {})
        mappings = p_info.get("scenes", {}).get(active_scene, {}).get("mappings", {})
        if lookup_key in mappings:
            m = mappings[lookup_key]; out_type = m[0]; is_track_level = out_type in ["sysex_track", "dynamic_sysex_track", "conditional_sysex_track"]
            if is_toggle := ("toggle" in m):
                if not is_press: return
                if out_type == "dynamic_sysex_track": s_key = (active_preset, active_scene, lookup_key, active_partial)
                elif out_type in ["drum_sysex_partial", "drum_sysex_inst"]: s_key = (active_preset, active_scene, lookup_key, active_pad, active_wave)
                elif is_track_level: s_key = (active_preset, active_scene, lookup_key, 'track')
                else: s_key = (active_preset, active_scene, lookup_key, active_partial)
                new_state = not toggle_states.get(s_key, False)
                toggle_states[s_key] = new_state; val = 127 if new_state else 0
            if out_type == "track_select" and is_press:
                active_track, last_edited_label, last_edited_val, last_edited_text = m[1], m[2], None, None
                update_overlay() if p_info.get("display_values", True) else clear_overlay(); return
            if out_type == "partial_select" and is_press:
                active_partial, last_edited_label, last_edited_val, last_edited_text = m[1], m[2], None, None
                update_overlay() if p_info.get("display_values", True) else clear_overlay(); return
            if out_type == "drum_pad_select":
                c_pad = active_pad_bank * 4 + m[1]; p_key = PAD_NOTES[c_pad - 1]
                if is_press:
                    active_pad, last_edited_label, last_edited_val, last_edited_text = c_pad, f"PD{c_pad:02d}", None, None
                    out_port.send(mido.Message('note_on', channel=active_track - 1, note=p_key, velocity=val))
                    update_overlay() if p_info.get("display_values", True) else clear_overlay()
                else: out_port.send(mido.Message('note_off', channel=active_track - 1, note=p_key, velocity=0)); return
            if out_type == "drum_pad_bank" and is_press:
                active_pad_bank, last_edited_label, last_edited_val, last_edited_text = (active_pad_bank + m[1]) % 4, m[2], None, None
                update_overlay() if p_info.get("display_values", True) else clear_overlay(); return
            if out_type == "drum_wave_select" and is_press:
                active_wave, last_edited_label, last_edited_val, last_edited_text = m[1], m[2], None, None
                update_overlay() if p_info.get("display_values", True) else clear_overlay(); return
            if out_type in ["sysex", "conditional_sysex", "sysex_track", "dynamic_sysex_track", "conditional_sysex_track", "drum_sysex_partial", "drum_sysex_inst"]:
                if out_type in ["sysex", "sysex_track"]: target = (m[1], m[2], m[3], m[4] if len(m) > 4 else 1, m[5] if len(m) > 5 and isinstance(m[5], list) else None, m[6] if len(m) > 6 and isinstance(m[6], dict) else (m[5] if len(m) > 5 and isinstance(m[5], dict) else None))
                elif out_type == "dynamic_sysex_track": target = (m[1].get(active_partial, 0), m[2], m[3], m[4] if len(m) > 4 else 1, m[5] if len(m) > 5 and isinstance(m[5], list) else None, m[6] if len(m) > 6 and isinstance(m[6], dict) else (m[5] if len(m) > 5 and isinstance(m[5], dict) else None))
                elif out_type in ["drum_sysex_partial", "drum_sysex_inst"]: target = (m[1].get(active_wave, 0) if isinstance(m[1], dict) else m[1], m[2], m[3], m[4] if len(m) > 4 else 1, m[5] if len(m) > 5 and isinstance(m[5], list) else None, m[6] if len(m) > 6 and isinstance(m[6], dict) else (m[5] if len(m) > 5 and isinstance(m[5], dict) else None))
                else:
                    cv = param_states.get((active_track, 'track', m[1]), param_states.get((active_track, active_partial, m[1]), 0))
                    target = m[2].get(cv)
                    if target and target[0] == "bank_dependent": target = target[1].get(param_states.get((active_track, 'track', ("cc", 2)), 8))
                if not target or target[0] is None: return
                offs, max_v, lbl, size, v_list, t_map = (target[0] if isinstance(target[0], list) else [target[0]]), target[1], target[2], target[3], (target[4] if len(target) > 4 else None), (target[5] if len(target) > 5 else None)
                now = time.time()
                if is_toggle or (now - last_sysex_time) > 0.08:
                    f_val = v_list[int(round((val/127.0)*max_v))] if v_list else int(round((val/127.0)*max_v))
                    param_states[(active_track, (f"P{active_pad}_W{active_wave}" if out_type in ["drum_sysex_partial", "drum_sysex_inst"] else ('track' if is_track_level else active_partial)), lookup_key)] = f_val
                    for o in offs:
                        if out_type == "drum_sysex_partial": addr = get_drum_partial_address(active_track, active_pad, o)
                        elif out_type == "drum_sysex_inst": addr = get_drum_inst_address(active_track, active_pad, o)
                        else: addr = get_mc101_address(active_track, (1 if is_track_level else active_partial), o)
                        send_sysex(out_port, addr, f_val, size)
                    if lbl in ["BNK", "WNO"]: send_sysex(out_port, get_mc101_address(active_track, active_partial, 0x1B), 0, 1)
                    last_sysex_time, last_edited_label, last_edited_val, last_edited_text = now, lbl, f_val, (t_map.get(f_val) if t_map else None)
                    update_overlay() if p_info.get("display_values", True) else clear_overlay()
            else:
                lbl = get_mapping_label(m)
                if out_type == "note": out_port.send(mido.Message('note_on' if val > 0 else 'note_off', channel=m[1], note=m[2], velocity=val))
                elif out_type == "cc": out_port.send(mido.Message('control_change', channel=m[1], control=m[2], value=val))
                if p_info.get("display_values", True):
                    if msg.type == 'control_change' or is_press or is_toggle:
                        last_edited_label, last_edited_val, last_edited_text = lbl, (val if out_type == "cc" else None), (None if out_type == "cc" else ("ON" if val > 0 else "OFF"))
                        update_overlay()
                else: clear_overlay() if (msg.type == 'control_change' or is_press or is_toggle) else None

    in_port.callback = midi_callback
    try:
        while True: time.sleep(1) 
    except KeyboardInterrupt: pass
    finally: in_port.close(); out_port.close()

if __name__ == "__main__": main()