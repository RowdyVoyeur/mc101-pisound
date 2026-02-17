# pisound-mc101
A portable device to add an Audio Input to the Roland MC-101, using Raspberry Pi 4 and Blokas Pisound.

## Settings

### Pisound Button
- [1](https://github.com/RowdyVoyeur/midi-tools/blob/main/midi-to-command/audioconfig03.sh) Clicks

### M8 Headless MIDI Settings
- Firmware [6.2.1](https://github.com/Dirtywave/M8HeadlessFirmware/blob/main/Releases/M8_V6_2_1_HEADLESS.hex)
- SYNC IN:  CLK + TRASNP + SPP
- SYNC OUT: OFF
- REC. NOTE CHAN: 08
- CC MAP CHAN: 16

### Roland MC-101 System (MIDI) Settings
- Sync Src: AUTO
- Sync Out: ON
- SyncOut USB: ON
- RX SartStop: ON
- RS Start USB: ON
- Ctrl Ch: CH14
- Ctrl Tx OUT: ON
- Ctrl Tx USB: ON
- Ctrl Rx: ON
- Rx Scatter: ON
