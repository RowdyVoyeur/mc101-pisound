import time
import sys
import rtmidi
from rtmidi.midiconstants import PROGRAM_CHANGE, NOTE_ON, NOTE_OFF

# MIDI configuration (0-indexed in Python)
# MC-101 Source Channel: 13 (index 12)
# M8 Target Channel: 15 (index 14)
SOURCE_CHANNEL = 12
TARGET_CHANNEL = 14

# M8 song row cue hold configuration.
# CC64 >= 64 keeps the queued/launched row held. The note is only released
# when another row is selected or when this script exits.
CONTROL_CHANGE = 0xB0
M8_ROW_HOLD_CC = 64
M8_ROW_HOLD_ON_VALUE = 127
M8_ROW_HOLD_OFF_VALUE = 0
M8_ROW_NOTE_VELOCITY = 100

def send_cc(midi_out, channel, control, value):
    midi_out.send_message([
        CONTROL_CHANGE | channel,
        control & 0x7F,
        value & 0x7F,
    ])

def send_note_on(midi_out, channel, note, velocity):
    midi_out.send_message([
        NOTE_ON | channel,
        note & 0x7F,
        velocity & 0x7F,
    ])

def send_note_off(midi_out, channel, note):
    midi_out.send_message([
        NOTE_OFF | channel,
        note & 0x7F,
        0,
    ])

def main():
    midi_in = rtmidi.MidiIn()
    midi_out = rtmidi.MidiOut()
    held_row_note = None

    in_ports = midi_in.get_ports()
    out_ports = midi_out.get_ports()

    # Find the dynamic port indexes
    mc101_idx = next((i for i, name in enumerate(in_ports) if "MC-101" in name), None)
    m8_idx = next((i for i, name in enumerate(out_ports) if "M8" in name), None)

    # Fail silently if ports aren't found (m8c.sh handles the logic now)
    if mc101_idx is None or m8_idx is None:
        sys.exit(0)

    # Open the ports
    midi_in.open_port(mc101_idx)
    midi_out.open_port(m8_idx)

    def launch_m8_row(row_note):
        nonlocal held_row_note

        # Release the previous row only when a different row is selected.
        if held_row_note is not None and held_row_note != row_note:
            send_note_off(midi_out, TARGET_CHANNEL, held_row_note)

        # Keep the M8 row cue held, then send the row note without an immediate
        # note-off. This matches the working nanokontroller.py scene-launch logic.
        send_cc(midi_out, TARGET_CHANNEL, M8_ROW_HOLD_CC, M8_ROW_HOLD_ON_VALUE)
        send_note_on(midi_out, TARGET_CHANNEL, row_note, M8_ROW_NOTE_VELOCITY)
        held_row_note = row_note

    def midi_callback(event, data=None):
        message, timestamp = event
        if not message:
            return

        status = message[0] & 0xF0
        channel = message[0] & 0x0F

        # Filter for Program Change on Source Channel
        if status == PROGRAM_CHANGE and channel == SOURCE_CHANNEL and len(message) >= 2:
            pc_value = message[1]
            launch_m8_row(pc_value)

    # Attach the callback listener
    midi_in.set_callback(midi_callback)

    # Keep the script alive in the background
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        if held_row_note is not None:
            send_note_off(midi_out, TARGET_CHANNEL, held_row_note)
        send_cc(midi_out, TARGET_CHANNEL, M8_ROW_HOLD_CC, M8_ROW_HOLD_OFF_VALUE)
        midi_in.close_port()
        midi_out.close_port()

if __name__ == "__main__":
    main()