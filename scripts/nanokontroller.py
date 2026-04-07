# =========================================================================================
# --- nanoKONTROL TO ROLAND MC-101: MASTER MAPPING CHEAT SHEET & REFERENCE ---
# =========================================================================================
#
# --- 1. PRESET HIERARCHY & SETTINGS ---
# PRESETS = { 
#     PRESET_ID: { 
#         "name": "Preset Name", 
#         "display_values": True/False, # True = Show Param Values. False = Show Matrix & Auto-Swap
#         "scenes": { 
#             SCENE_ID: { 
#                 "name": "Scene Name", 
#                 "mappings": { ... } 
#             } 
#         } 
#     } 
# }
#
# --- 2. THE UI MATRIX ---
# - The overlay operates as a 9x2 Matrix (Line 2 and Line 3).
# - Input Type decides the visual style:
#   > CCs (Knobs/Faders) display as padded text: " WAV "
#   > Notes (Buttons) display with brackets:     "[T01]"
# - The active parameter is highlighted as ">X<". Unmapped parameters show "---".
#
# --- 3. STANDARD MAPPING SYNTAX ---
# ("in_type", number): ("out_type", channel/offset, target/max_val, [options...])
#
# Supported "out_type" targets:
# - "cc": Standard MIDI CC out.
# - "note": Standard MIDI Note out.
# - "track_select": Internal script logic to change the active MC-101 Track (1-4).
# - "partial_select": Internal script logic to change the active MC-101 Partial (1-4).
# - "sysex": Direct Roland Zen-Core memory writing.
# - "conditional_sysex": Dynamic memory writing based on the state of another parameter.
#
# Standard Options (Any order for CC/Note. Order matters for SysEx):
# - Label: String (e.g., "VOL", "CUT"). Max 3 chars. 
# - Scale: Tuple (min, max) (e.g., (0, 50)). Standard CC/Note only.
# - Toggle: The string "toggle". Standard CC/Note only.
#
# --- 4. SYSEX OPTIONS & SYNTAX ---
# ("in_type", number): ("sysex", offset(s), max_val, "LBL", byte_size, {Value_Map})
#
# - offset(s): Hex address (e.g., 0x3E00). Use a list [0x1C, 0x34] for Stereo Sync (L+R).
# - max_val: Integer. The maximum hardware value. Fader is scaled 0 to this number.
# - "LBL": 3-character string for the overlay.
# - byte_size: Integer (e.g., 4 or 1). Roland high-res params use 4.
# - {Value_Map}: (Optional) Dictionary translating raw numbers to overlay text.
#                Example: {0: "PCM", 1: "VA"} -> Displays "PCM" instead of "0".
#
# --- 5. CONDITIONAL SYSEX SYNTAX ---
# ("cc", 1): ("conditional_sysex", condition_cc_number, {
#     condition_val: (offset(s), max_val, "LBL", byte_size, [val_list], {Value_Map}),
#     ...
# })
# - If 'offset' is 'None', the mapping acts as a UI placeholder and sends no MIDI.
# - [val_list]: (Optional) List translating 0-127 fader steps to specific hardware jumps.
#               Example: [8, 10, 11] turns a 3-step fader into hardware values 8, 10, and 11.
# - "bank_dependent": Special routing keyword to change max_vals based on MC-101 Wave Bank.
#
# =========================================================================================
# --- EXAMPLES ---
# =========================================================================================
# 1. Standard CC: 
#    ("cc", 0): ("cc", 14, 10, "VOL"),
#
# 2. Track / Partial Selection (Buttons):
#    ("note", 0): ("track_select", 1, "T01"),
#    ("note", 9): ("partial_select", 2, "P02"),
#
# 3. SysEx w/ Text Value Map (Displays "PCM" or "VA" on screen):
#    ("cc", 0): ("sysex", 0x3E00, 4, "OTY", 1, {0: "PCM", 1: "VA"}),
#
# 4. Conditional SysEx w/ Stereo Sync & Hardware Value Jumps (Bank Select):
#    ("cc", 2): ("conditional_sysex", 0, {
#        0: ([0x201C, 0x2034], 2, "BNK", 4, [8, 10, 11], {8: "A", 10: "B", 11: "C"}), 
#        1: (0x3E06, 127, "PW ", 1)
#    }),
# =========================================================================================

#!/usr/bin/env python3
import sys, time, os, mido
import threading

# --- CONFIGURATION ---
OVERLAY_PIPE = "/tmp/m8c_overlay"

# Transport Buttons
PRESET_1 = 127 # Rewind
PRESET_4 = 124 # Loop
PRESET_6 = 122 # Rec

# Global State
active_preset = PRESET_1
active_scene = 1
active_track = 1
active_partial = 1

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
    PRESET_6: {
        "name": "MC-101",
        "display_values": True, 
        "scenes": {
            1: {
                "name": "OSC & COMMON",
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
                    
                    # --- TONE SYNTH PMT MAPPINGS (Base 0x3D00) ---
                    # Structure 1-2
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

                    # Structure 3-4
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

                    # --- TONE PARTIAL MAPPINGS (Base 0x2000) ---
                    ("cc", 9): ("sysex", 0x2001, 96, "CRS", 1, list(range(16, 113)), CRS_LABELS),
                    ("cc", 10): ("sysex", 0x2002, 100, "FIN", 1, list(range(14, 115)), FIN_LABELS),
                    ("cc", 11): ("sysex", 0x2000, 127, "LEV", 1), 
                    ("cc", 12): ("sysex", 0x2007, 127, "PAN", 1, None, PAN_LABELS),

                    ("note", 0): ("track_select", 1, "T01"),
                    ("note", 1): ("track_select", 2, "T02"),
                    ("note", 2): ("track_select", 3, "T03"),
                    ("note", 3): ("track_select", 4, "T04"),
                    
                    # Partial Phase Lock (Conditioned on Structure 1-2)
                    ("note", 4): ("conditional_sysex_track", ("cc", 4), {
                        0: (None, 0, "---", 1),
                        1: (None, 0, "---", 1),
                        2: (None, 0, "---", 1),
                        3: (0x3D14, 1, "LCK", 1, None, {0: "OFF", 1: "ON"}),
                        4: (0x3D14, 1, "LCK", 1, None, {0: "OFF", 1: "ON"})
                    }, "toggle"),

                    # Partial Phase Lock (Conditioned on Structure 3-4)
                    ("note", 6): ("conditional_sysex_track", ("cc", 6), {
                        0: (None, 0, "---", 1),
                        1: (None, 0, "---", 1),
                        2: (None, 0, "---", 1),
                        3: (0x3D14, 1, "LCK", 1, None, {0: "OFF", 1: "ON"}),
                        4: (0x3D14, 1, "LCK", 1, None, {0: "OFF", 1: "ON"})
                    }, "toggle"),

                    ("note", 9): ("partial_select", 1, "P01"),
                    ("note", 10): ("partial_select", 2, "P02"),
                    ("note", 11): ("partial_select", 3, "P03"),
                    ("note", 12): ("partial_select", 4, "P04"),
                    
                    # --- TONE COMMON PARAMETERS (Base 0x1000) ---
                    ("note", 13): ("dynamic_sysex_track", {1: 0x1002, 2: 0x100B, 3: 0x1014, 4: 0x101D}, 1, "PSW", 1, {0: "OFF", 1: "ON"}, "toggle"),
                }
            }
        }
    }
}

# --- ROLAND SYSEX HELPERS ---
def compute_checksum(payload):
    return (128 - (sum(payload) % 128)) % 128

def send_sysex(out_port, address, value, size):
    DEVICE_ID = 0x10
    MODEL_ID = [0x00, 0x00, 0x00, 0x5E]
    header = [0x41, DEVICE_ID] + MODEL_ID + [0x12]
    addr_bytes = [(address >> 24) & 0x7F, (address >> 16) & 0x7F, (address >> 8) & 0x7F, address & 0x7F]
    if size == 4: data_bytes = [(value >> 12) & 0x0F, (value >> 8) & 0x0F, (value >> 4) & 0x0F, value & 0x0F]
    else: data_bytes = [value & 0x7F]
    payload = addr_bytes + data_bytes
    sysex_data = header + payload + [compute_checksum(payload)]
    out_port.send(mido.Message('sysex', data=sysex_data))

def get_mc101_address(track, partial, param_offset):
    track_bases = {1: 0x30200000, 2: 0x30420000, 3: 0x30640000, 4: 0x31060000}
    base = track_bases.get(track, 0x30200000)
    partial_offset = (partial - 1) * 0x00000100
    return base + partial_offset + param_offset

def get_mapping_label(m):
    if not m: return "---"
    out_type = m[0]
    
    if out_type in ["conditional_sysex", "conditional_sysex_track"]:
        # FIX: Look for track-level states first, then partial-level states
        cond_val = param_states.get((active_track, 'track', m[1]), param_states.get((active_track, active_partial, m[1]), 0))
        target = m[2].get(cond_val)
        if target:
            if target[0] == "bank_dependent":
                bank_val = param_states.get((active_track, 'track', ("cc", 2)), param_states.get((active_track, active_partial, ("cc", 2)), 8))
                res = target[1].get(bank_val)
                return res[2] if res else "---"
            return target[2]
        return "---"
    elif out_type in ["track_select", "partial_select"]:
        return m[2]
    else:
        for item in m[3:]:
            if isinstance(item, str) and item != "toggle": return item
    return "---"

def schedule_matrix_swap(preset_num, scene_num, trigger_time):
    time.sleep(2.5)
    if active_preset == preset_num and active_scene == scene_num:
        if last_interaction_time <= trigger_time:
            global last_touched_type
            last_touched_type = "note"
            update_overlay()

def clear_overlay():
    if os.path.exists(OVERLAY_PIPE):
        try:
            fd = os.open(OVERLAY_PIPE, os.O_WRONLY | os.O_NONBLOCK)
            os.write(fd, b" \n")
            os.close(fd)
        except: pass

# --- OVERLAY ENGINE ---
def update_overlay():
    preset_data = PRESETS.get(active_preset, {})
    scene_data = preset_data.get("scenes", {}).get(active_scene, {})
    display_vals = preset_data.get("display_values", True)
    scene_name = scene_data.get("name", f"S{active_scene}")
    preset_name = preset_data.get('name', 'NONE')
    
    if active_preset == PRESET_6:
        tr_str = f"T{active_track:02d}"
        pa_str = f"P{active_partial:02d}"
        if display_vals:
            lbl_str = last_edited_label if last_edited_label else "READY"
            val_display = last_edited_text if last_edited_text else (str(last_edited_val) if last_edited_val is not None else "")
            line1 = f"{preset_name} > {tr_str} > {pa_str} > {scene_name} > {lbl_str} {val_display}"
        else:
            line1 = f"{preset_name} > {tr_str} > {pa_str} > {scene_name} "
    else:
        if display_vals:
            lbl_str = last_edited_label if last_edited_label else "READY"
            val_display = last_edited_text if last_edited_text else (str(last_edited_val) if last_edited_val is not None else "")
            line1 = f"{preset_name} > {scene_name} > {lbl_str} {val_display}"
        else:
            line1 = f"{preset_name} > {scene_name} "
    
    mappings = scene_data.get("mappings", {})
    all_labels = []
    
    for i in range(18):
        key = (last_touched_type, i) 
        label = get_mapping_label(mappings.get(key))
        
        if label.strip() == "":
            core_str = "   "
        elif label == last_edited_label:
            core_str = ">X<"
        else:
            core_str = str(label).strip()[:3].upper().ljust(3, " ")
            if core_str == "---" and key not in mappings:
                core_str = "---"

        all_labels.append(core_str)

    if last_touched_type == "cc":
        line2 = " | ".join(all_labels[:9])
        line3 = " | ".join(all_labels[9:18])
    else:
        line2 = " : ".join(all_labels[:9])
        line3 = " : ".join(all_labels[9:18])

    overlay_text = f"{line1.ljust(45)}~{line2.ljust(55)}~{line3.ljust(55)}\n"
    if os.path.exists(OVERLAY_PIPE):
        try:
            fd = os.open(OVERLAY_PIPE, os.O_WRONLY | os.O_NONBLOCK)
            os.write(fd, overlay_text.encode()); os.close(fd)
        except: pass

def main():
    global active_preset, active_scene, active_track, active_partial
    global last_edited_label, last_edited_val, last_edited_text, last_sysex_time
    global toggle_states, param_states, last_touched_type, last_interaction_time

    try:
        in_port = mido.open_input('In', virtual=True, client_name='nanoRouterIN')
        out_port = mido.open_output('Out', virtual=True, client_name='nanoRouterOUT')
    except Exception as e: sys.exit(f"Failed: {e}")

    update_overlay()

    def midi_callback(msg):
        global active_preset, active_scene, active_track, active_partial
        global last_edited_label, last_edited_val, last_edited_text, last_sysex_time
        global toggle_states, param_states, last_touched_type, last_interaction_time
        
        if msg.type == 'sysex' and msg.data[:8] == (66, 75, 0, 1, 4, 0, 95, 79):
            active_scene = msg.data[8] + 1
            update_overlay()
            return
            
        if msg.type == 'control_change' and msg.control in PRESETS:
            if msg.value > 0: 
                active_preset = msg.control
                preset_info = PRESETS.get(active_preset, {})
                last_edited_label, last_edited_val, last_edited_text = None, None, None
                
                trigger_time = time.time()
                last_interaction_time = trigger_time
                
                if preset_info.get("display_values", True) == False:
                    last_touched_type = "cc"
                    threading.Thread(target=schedule_matrix_swap, args=(active_preset, active_scene, trigger_time), daemon=True).start()
                
                update_overlay()
            return 

        if msg.type == 'control_change':
            lookup_key = ("cc", msg.control)
            val = msg.value
            is_press = val > 0
            last_touched_type = "cc"
        elif msg.type in ['note_on', 'note_off']:
            lookup_key = ("note", msg.note)
            val = getattr(msg, 'velocity', 0)
            is_press = (msg.type == 'note_on' and val > 0)
            last_touched_type = "note"
        else:
            return

        last_interaction_time = time.time()
        preset_info = PRESETS.get(active_preset, {})
        scene_mappings = preset_info.get("scenes", {}).get(active_scene, {}).get("mappings", {})

        if lookup_key in scene_mappings:
            m = scene_mappings[lookup_key]
            out_type = m[0]
            is_track_level = out_type in ["sysex_track", "dynamic_sysex_track", "conditional_sysex_track"]
            
            # --- UNIFIED TOGGLE ENGINE ---
            is_toggle = ("toggle" in m)
            if is_toggle:
                if not is_press: return 
                
                if out_type == "dynamic_sysex_track":
                    state_key = (active_preset, active_scene, lookup_key, active_partial)
                elif is_track_level:
                    state_key = (active_preset, active_scene, lookup_key, 'track')
                else:
                    state_key = (active_preset, active_scene, lookup_key, active_partial)
                    
                new_state = not toggle_states.get(state_key, False)
                toggle_states[state_key] = new_state
                val = 127 if new_state else 0
            
            # --- INTERNAL ROUTING ---
            if out_type == "track_select" and is_press:
                active_track = m[1]
                last_edited_label = m[2]
                last_edited_val, last_edited_text = None, None
                if preset_info.get("display_values", True): update_overlay()
                else: clear_overlay()
                return
                
            if out_type == "partial_select" and is_press:
                active_partial = m[1]
                last_edited_label = m[2]
                last_edited_val, last_edited_text = None, None
                if preset_info.get("display_values", True): update_overlay()
                else: clear_overlay()
                return

            # --- EXTERNAL MIDI ROUTING ---
            if out_type in ["sysex", "conditional_sysex", "sysex_track", "dynamic_sysex_track", "conditional_sysex_track"]:
                target = None
                
                if out_type in ["sysex", "sysex_track"]:
                    v_list = m[5] if len(m) > 5 and isinstance(m[5], list) else None
                    t_map = m[6] if len(m) > 6 and isinstance(m[6], dict) else (m[5] if len(m) > 5 and isinstance(m[5], dict) else None)
                    target = (m[1], m[2], m[3], m[4] if len(m) > 4 else 1, v_list, t_map)
                elif out_type == "dynamic_sysex_track":
                    offset_dict = m[1]
                    offset = offset_dict.get(active_partial, 0x0000)
                    v_list = m[5] if len(m) > 5 and isinstance(m[5], list) else None
                    t_map = m[6] if len(m) > 6 and isinstance(m[6], dict) else (m[5] if len(m) > 5 and isinstance(m[5], dict) else None)
                    target = (offset, m[2], m[3], m[4] if len(m) > 4 else 1, v_list, t_map)
                else: # handles both conditional_sysex and conditional_sysex_track
                    # FIX: Look for track-level states first, then partial-level states
                    cond_val = param_states.get((active_track, 'track', m[1]), param_states.get((active_track, active_partial, m[1]), 0))
                    target = m[2].get(cond_val)
                    if target and target[0] == "bank_dependent":
                        bank_val = param_states.get((active_track, 'track', ("cc", 2)), param_states.get((active_track, active_partial, ("cc", 2)), 8))
                        target = target[1].get(bank_val)

                if not target or target[0] is None: return

                offsets = target[0] if isinstance(target[0], list) else [target[0]]
                max_val, lbl, size = target[1], target[2], target[3]
                val_list = target[4] if len(target) > 4 else None
                txt_map = target[5] if len(target) > 5 else None

                now = time.time()
                if is_toggle or (now - last_sysex_time) > 0.08:
                    scaled_val = int(round((val / 127.0) * max_val))
                    final_val = val_list[scaled_val] if val_list else scaled_val
                    
                    # FIX: Store using the entire lookup_key tuple, and respect track-level scope
                    eff_partial = 'track' if is_track_level else active_partial
                    param_states[(active_track, eff_partial, lookup_key)] = final_val
                    
                    for off in offsets:
                        eff_partial_sys = 1 if is_track_level else active_partial
                        send_sysex(out_port, get_mc101_address(active_track, eff_partial_sys, off), final_val, size)
                    
                    if lbl in ["BNK", "WNO"]:
                        send_sysex(out_port, get_mc101_address(active_track, active_partial, 0x1B), 0, 1)

                    last_sysex_time = now
                    last_edited_label, last_edited_val = lbl, final_val
                    last_edited_text = txt_map.get(final_val) if txt_map else None
                    
                    if preset_info.get("display_values", True): update_overlay()
                    else: clear_overlay()
            
            else: # Standard CC / Note Mapping Engine
                lbl = get_mapping_label(m)
                
                if out_type == "note":
                    out_port.send(mido.Message('note_on' if val > 0 else 'note_off', channel=m[1], note=m[2], velocity=val))
                elif out_type == "cc":
                    out_port.send(mido.Message('control_change', channel=m[1], control=m[2], value=val))
                
                if preset_info.get("display_values", True):
                    if msg.type == 'control_change' or is_press or is_toggle:
                        if out_type == "cc":
                            last_edited_label, last_edited_val, last_edited_text = lbl, val, None
                        else:
                            last_edited_label, last_edited_val, last_edited_text = lbl, None, "ON" if val > 0 else "OFF"
                        update_overlay()
                else:
                    if msg.type == 'control_change' or is_press or is_toggle: 
                        clear_overlay()

    in_port.callback = midi_callback
    try:
        while True: time.sleep(1) 
    except KeyboardInterrupt: pass
    finally: in_port.close(); out_port.close()

if __name__ == "__main__": main()