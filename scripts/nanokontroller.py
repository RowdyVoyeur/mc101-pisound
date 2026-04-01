# =========================================================================
# --- MAPPING CHEAT SHEET & REFERENCE ---
# =========================================================================
# Incoming Key: ("cc", cc_number) OR ("note", note_number)
# Outgoing Val: ("type", channel, target, [optional_scale], [optional_behavior])
# Note: channel must be target-1, i.e. if the target channel is 16, must use 15
#
# --- EXAMPLES ---
# 1. Standard (0-127, Momentary)
#    ("cc", 0): ("cc", 14, 10),
#
# 2. SCALED (Restricting the range)
#    ("cc", 1): ("cc", 14, 11, (0, 50)),
#
# 3. TOGGLE BEHAVIOR (Press once for 127, press again for 0)
#    ("note", 24): ("note", 14, 60, "toggle"),
#
# 4. SCALED + TOGGLE (Press once for 50, press again for 10)
#    ("cc", 2): ("cc", 14, 12, (10, 50), "toggle"),
#
# 5. Program Change
#    ("note", 0): ("pc", 12, 5),
# =========================================================================

#!/usr/bin/env python3
import sys, time, os, mido

# --- CONFIGURATION ---
OVERLAY_PIPE = "/tmp/m8c_overlay"

# Transport Buttons (Used to switch presets)
PRESET_1_CC = 127 # Rewind
PRESET_2_CC = 126 # Play
PRESET_3_CC = 125 # FastFwd
PRESET_4_CC = 124 # Loop
PRESET_5_CC = 123 # Stop
PRESET_6_CC = 122 # Rec

# Global State
active_preset = PRESET_1_CC
toggle_states = {}  

PRESETS = {
    PRESET_1_CC: {
        "name": "M8 MIXER",
        "description": "Allows to mix, mute and solo M8 tracks",
        "mappings": {
            ("cc", 0): ("cc", 15, 3),               
            ("cc", 1): ("cc", 15, 14),  
            ("cc", 2): ("cc", 15, 21),    
            ("note", 0): ("note", 15, 12),           # Momentary
            ("note", 1): ("note", 15, 13, "toggle"), # Toggle
            ("note", 2): ("note", 15, 14, "toggle"), # Toggle
        }
    },
PRESET_4_CC: {
        "name": "MC-101 PARTIAL EDITOR",
        "description": "Allows to edit several parameters of the tone partial editor",
        "mappings": {
            ("cc", 0): ("cc", 11, 0),  # Fader 1 (CC 0) -> Zeditor CC 0
            ("cc", 1): ("cc", 11, 1),  # Fader 2 (CC 1) -> Zeditor CC 1
            ("cc", 2): ("cc", 11, 2),  # Fader 3 (CC 2) -> Zeditor CC 2
        }
    }
}

def update_overlay(action_text=""):
    preset_data = PRESETS.get(active_preset, {})
    preset_name = preset_data.get("name", "UNKNOWN PRESET")
    preset_desc = preset_data.get("description", "")
    
    overlay_text = f"nanoKONTROL Preset: {preset_name}~{preset_desc}~{action_text}"
    
    if os.path.exists(OVERLAY_PIPE):
        try:
            fd = os.open(OVERLAY_PIPE, os.O_WRONLY | os.O_NONBLOCK)
            os.write(fd, overlay_text.encode())
            os.close(fd)
        except:
            pass
    print(overlay_text.replace("~", " | ")) 

def scale_value(val, out_min, out_max):
    scaled = out_min + (val / 127.0) * (out_max - out_min)
    return int(round(scaled))

def main():
    global active_preset, toggle_states

    try:
        in_port = mido.open_input('In', virtual=True, client_name='nanoRouterIN')
        out_port = mido.open_output('Out', virtual=True, client_name='nanoRouterOUT')
        print("Router Active: Virtual Ports Opened.")
    except Exception as e:
        sys.exit(f"Failed to open virtual ports: {e}")

    update_overlay("ROUTER INITIALIZED")

    # --- THE CALLBACK ENGINE ---
    def midi_callback(msg):
        global active_preset, toggle_states
        
        # 1. CHECK FOR PRESET CHANGES
        if msg.type == 'control_change' and msg.control in PRESETS:
            if msg.value > 0: 
                active_preset = msg.control
                update_overlay("PRESET LOADED")
            return 

        # 2. ROUTE THE MIDI DATA
        mappings = PRESETS.get(active_preset, {}).get("mappings", {})
        
        lookup_key = None
        if msg.type == 'control_change':
            lookup_key = ("cc", msg.control)
        elif msg.type in ['note_on', 'note_off']:
            lookup_key = ("note", msg.note)

        if lookup_key and lookup_key in mappings:
            mapped_data = mappings[lookup_key]
            out_type = mapped_data[0]
            out_channel = mapped_data[1]
            out_target = mapped_data[2]
            
            # --- PROPERLY DETECT PRESS VS RELEASE ---
            if msg.type == 'control_change':
                val_to_send = msg.value
                is_press = msg.value > 0
            elif msg.type == 'note_on':
                val_to_send = msg.velocity
                is_press = msg.velocity > 0
            elif msg.type == 'note_off':
                val_to_send = 0  # Force weird release velocities (like 64) to 0
                is_press = False
            
            out_min, out_max = None, None
            is_toggle = False
            
            if len(mapped_data) > 3:
                for opt in mapped_data[3:]:
                    if isinstance(opt, tuple) and len(opt) == 2:
                        out_min, out_max = opt
                    elif opt == "toggle":
                        is_toggle = True

            # --- TOGGLE LOGIC ---
            if is_toggle:
                if not is_press:
                    return # Completely ignore the physical button release
                
                state_key = (active_preset, lookup_key)
                current_state = toggle_states.get(state_key, False)
                new_state = not current_state
                toggle_states[state_key] = new_state
                
                val_to_send = 127 if new_state else 0

            # --- SCALING LOGIC ---
            if out_min is not None and out_max is not None:
                val_to_send = scale_value(val_to_send, out_min, out_max)
            
            # --- OUTPUT DISPATCHER ---
            if out_type == "cc":
                val_to_send = max(0, min(127, val_to_send))
                out_msg = mido.Message('control_change', channel=out_channel, control=out_target, value=val_to_send)
                out_port.send(out_msg)

            elif out_type == "note":
                if is_toggle or msg.type == 'control_change':
                    # If we are artificially generating the state, force clean Note On/Off commands
                    note_type = 'note_on' if val_to_send > 0 else 'note_off'
                    vel = val_to_send if val_to_send > 0 else 0
                    out_msg = mido.Message(note_type, channel=out_channel, note=out_target, velocity=vel)
                    out_port.send(out_msg)
                else:
                    # Standard Momentary pass-through
                    out_msg = mido.Message(msg.type, channel=out_channel, note=out_target, velocity=val_to_send)
                    out_port.send(out_msg)

            elif out_type == "pc":
                if is_press: # Only trigger Program Changes when you push down!
                    out_msg = mido.Message('program_change', channel=out_channel, program=out_target)
                    out_port.send(out_msg)

    # Attach the callback listener
    in_port.callback = midi_callback

    try:
        while True:
            time.sleep(1) 
    except KeyboardInterrupt:
        pass
    finally:
        in_port.close()
        out_port.close()

if __name__ == "__main__":
    main()