# pisound-mc101
A portable device to add an Audio Input to the Roland MC-101, using Raspberry Pi 4 and Blokas Pisound.

## Settings

### Pisound Button
- [1](https://github.com/RowdyVoyeur/midi-tools/blob/main/midi-to-command/audioconfig03.sh) Click

### M8 Headless Settings
- Firmware [6.2.1](https://github.com/Dirtywave/M8HeadlessFirmware/blob/main/Releases/M8_V6_2_1_HEADLESS.hex)
- Live Quantitize: 10 (16 Steps)

### M8 Headless MIDI Settings
- SYNC IN:  CLK + TRASNP
- SYNC OUT: OFF
- REC. NOTE CHAN: 14
- CC MAP CHAN: 16
- SONGROW CUE CH: 15

### Roland MC-101 System (MIDI) Settings
- Sync Src: AUTO
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
