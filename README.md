# mc101-pisound

A portable device to add an Audio Input to the Roland MC-101, using Raspberry Pi 4, Blokas Pisound, M8C and a few additional scripts.

M8C is a client for [Dirtywave M8](https://dirtywave.com/) headless mode. While the original [application](https://github.com/laamaa/m8c) is cross-platform and can be built for Linux, Windows, macOS, and Android, **this specific fork is optimized and tested exclusively for the Raspberry Pi 4** (running 64-bit Raspberry Pi OS Bookworm) and is tailored for integration with the Roland MC-101 and PiSound.

## 1. Install Dependencies

Install the libraries required by SLD3 and m8c:

```
sudo apt update
sudo apt install -y \
  build-essential cmake git pkg-config \
  libwayland-dev wayland-protocols libxkbcommon-dev \
  libegl1-mesa-dev libgles2-mesa-dev libdrm-dev \
  libgbm-dev libudev-dev libdbus-1-dev \
  libusb-1.0-0-dev librtmidi-dev gh
  libsdl3-ttf-dev
```
Install the Font Engines
SDL3_ttf relies on FreeType to actually read the .ttf files. Run this to ensure your Pi has those foundational tools:

```
sudo apt update
sudo apt install -y cmake libfreetype-dev libharfbuzz-dev
```

Build SDL3_ttf from Source
Run these commands one by one to clone the extension, build it, and install it into your system's library folder.

```
# 1. Go back to your home folder
cd ~

# 2. Download the SDL3_ttf source code
git clone https://github.com/libsdl-org/SDL_ttf.git

# 3. Move into the folder and prepare the build
cd SDL_ttf
mkdir build
cd build

# 4. Configure and compile (using all 4 cores of the Pi)
cmake ..
make -j4

# 5. Install it to the system
sudo make install

# 6. Refresh the system's library cache
sudo ldconfig
```


## 2. Download SDL3

Run the following to clone SDL3:

```
cd ~
# If the folder already exists, just enter it; otherwise, clone.
[ -d "sdl3" ] || git clone --depth 1 https://github.com/libsdl-org/SDL.git sdl3
cd sdl3
mkdir -p build && cd build
```

## 3. Configure SDL3

This command tells SDL3 to use the hardware acceleration of the Pi 4 and the low-latency audio of Patchbox.

```
cmake -DCMAKE_BUILD_TYPE=Release \
      -DSDL_VIDEO_DRIVER_KMSDRM=ON \
      -DSDL_VIDEO_DRIVER_X11=ON \
      -DSDL_VIDEO_DRIVER_WAYLAND=ON \
      -DSDL_OPENGL=OFF \
      -DSDL_OPENGLES=ON \
      -DSDL_ALSA=ON \
      -DSDL_JACK=ON \
      -DSDL_PULSEAUDIO=OFF ..
```

## 4. Compile and Install SDL3

Run the following to compile and install SDL3:

```
make -j4
sudo make install
sudo ldconfig
```

## 5. Verification

Run this command to see if the system can find the SDL3:


```
pkg-config --modversion sdl3
```

## 6. Clone mc101-pisound repository

```
cd ~
git clone https://github.com/RowdyVoyeur/mc101-pisound.git
cd mc101-pisound
```

## 7. Run the build

```
make clean
make
```

## 8. Install udev Rules

By default, Linux blocks regular users from talking directly to USB hardware for security. You need to tell the Pi that the user is allowed to talk to the M8.

### Create a new rules file:

```
sudo nano /etc/udev/rules.d/50-m8.rules
```

### Paste this exact line into the file

```
SUBSYSTEM=="usb", ATTR{idVendor}=="16c0", ATTR{idProduct}=="048a", MODE="0666", GROUP="plugdev"
```

### Reload the rules:

```
sudo udevadm control --reload-rules
sudo udevadm trigger
```

### Reboot and check system visibility

```
lsusb
```
If you see something like "Van Ooijen Technische Informatica M8", it should be working fine.

## 9. Run as Root

```
sudo ./m8c
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
