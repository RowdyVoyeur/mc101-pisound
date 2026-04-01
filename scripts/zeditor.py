#!/usr/bin/env python3
import sys, mido, time, os

# --- CONFIG ---
NANO_CHANNEL = 11  # MIDI Channel 12
DEVICE_ID = 0x10
MODEL_ID = [0x00, 0x00, 0x00, 0x5E]
OVERLAY_PIPE = "/tmp/m8c_overlay"
TRACK_1_BASE = 0x30200000 

# CC: (Address, Max_Val, Byte_Size, "Label")
PARAMETER_MAP = {
    0: (TRACK_1_BASE + 0x2032, 1023, 4, "P1 CUTOFF"),       
    1: (TRACK_1_BASE + 0x203D, 1023, 4, "P1 RESO"),
    2: (TRACK_1_BASE + 0x001A, 127, 1, "OCTAVE"),
}

def compute_checksum(payload):
    return (128 - (sum(payload) % 128)) % 128

def send_sysex(out_port, address, value, size):
    header = [0x41, DEVICE_ID] + MODEL_ID + [0x12]
    addr_bytes = [(address >> 24) & 0x7F, (address >> 16) & 0x7F, (address >> 8) & 0x7F, address & 0x7F]
    
    if size == 4:
        data_bytes = [(value >> 12) & 0x0F, (value >> 8) & 0x0F, (value >> 4) & 0x0F, value & 0x0F]
    else:
        data_bytes = [value & 0x7F]
        
    payload = addr_bytes + data_bytes
    sysex_data = header + payload + [compute_checksum(payload)]
    out_port.send(mido.Message('sysex', data=sysex_data))

def main():
    # --- MIDI PORT SETUP ---
    try:
        out_name = next((p for p in mido.get_output_names() if "MC-101" in p), None)
        if not out_name:
            sys.exit("MC-101 hardware not found.")
        
        out_port = mido.open_output(out_name)
        
        # 1. Explicitly name this client "Zeditor" so amidiminder can plug the cable into it!
        in_port = mido.open_input('In', virtual=True, client_name='Zeditor')
        
        print(f"Zeditor Active: Virtual Input -> {out_name}")
    except Exception as e:
        sys.exit(f"Setup Error: {e}")

    last_send = 0
    throttle = 0.04  # Prevents MC-101 from freezing

    # 2. THE CALLBACK ENGINE (Fixes the Linux Virtual Port bug)
    def midi_callback(msg):
        nonlocal last_send
        
        if msg.type == 'control_change' and msg.channel == NANO_CHANNEL:
            if msg.control in PARAMETER_MAP:
                now = time.time()
                if (now - last_send) > throttle:
                    addr, max_val, size, label = PARAMETER_MAP[msg.control]
                    scaled_val = int((msg.value / 127.0) * max_val)
                    
                    send_sysex(out_port, addr, scaled_val, size)
                    last_send = now
                    
                    # Send to M8 Overlay
                    overlay_text = f"TONE EDITOR~{label}~VALUE: {scaled_val}"
                    if os.path.exists(OVERLAY_PIPE):
                        try:
                            fd = os.open(OVERLAY_PIPE, os.O_WRONLY | os.O_NONBLOCK)
                            os.write(fd, overlay_text.encode())
                            os.close(fd)
                        except: pass

    # Attach the callback listener
    in_port.callback = midi_callback

    # Keep script alive in the background
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