# mc101-pisound

A portable device to add an Audio Input to the Roland MC-101, using Raspberry Pi 4, Blokas Pisound, M8C and a few additional scripts.

M8C is a client for [Dirtywave M8](https://dirtywave.com/) headless mode. While the original [application](https://github.com/laamaa/m8c) is cross-platform and can be built for Linux, Windows, macOS, and Android, **this specific fork is optimized and tested exclusively for the Raspberry Pi 4** (running 64-bit Raspberry Pi OS Bookworm) and is tailored for integration with the Roland MC-101 and PiSound.

## Prepare to Install

First, update your system and install the required tools and dependencies (including CMake, ALSA, Serial Port, and RtMidi libraries):

```bash
sudo apt update
sudo apt install -y build-essential cmake git pkg-config libasound2-dev libserialport-dev librtmidi-dev
```

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
