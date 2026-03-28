# mc101-pisound

A portable device to add an Audio Input to the Roland MC-101, using Raspberry Pi 4, Blokas Pisound, M8C and a few additional scripts.

M8C is a client for [Dirtywave M8](https://dirtywave.com/) headless mode. While the original [application](https://github.com/laamaa/m8c) is cross-platform and can be built for Linux, Windows, macOS, and Android, **this specific fork is optimized and tested exclusively for the Raspberry Pi 4** (running 64-bit Raspberry Pi OS Bookworm) and is tailored for integration with the Roland MC-101 and PiSound.

## 1. Install Dependencies

Install the libraries required by SLD3 and m8c:

```
sudo apt update
sudo apt install -y \
  build-essential cmake git pkg-config \
  libusb-1.0-0-dev \
  libudev-dev libdbus-1-dev \
  libegl1-mesa-dev libgles2-mesa-dev libdrm-dev libgbm-dev \
  libasound2-dev libjack-jackd2-dev libfreetype-dev
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
      -DSDL_UNIX_CONSOLE_BUILD=ON \
      -DSDL_VIDEO_DRIVER_KMSDRM=ON \
      -DSDL_X11=OFF \
      -DSDL_WAYLAND=OFF \
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

## 6. Install SDL3_ttf (Font Support)

The M8 visual overlay requires the TrueType Font add-on to draw text. Run the following to download and compile it:

```
cd ~
git clone --depth 1 https://github.com/libsdl-org/SDL_ttf.git
cd SDL_ttf
mkdir -p build && cd build
cmake -DCMAKE_BUILD_TYPE=Release ..
make -j4
sudo make install
sudo ldconfig
```

## 7. Clone mc101-pisound repository

```
cd ~
git clone https://github.com/RowdyVoyeur/mc101-pisound.git
cd mc101-pisound
```

## 8. Run the build

```
make clean
make
```

## 9. Install udev Rules

By default, Linux blocks regular users from talking directly to USB hardware for security. You need to tell the Pi that the system is allowed to talk to the M8 without requiring root privileges.

### Create a new rules file:

Copy and paste this entire line into the terminal and press Enter. This creates the configuration file and writes the correct permissions:

```
echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="16c0", ATTR{idProduct}=="048a", MODE="0666", GROUP="plugdev"' | sudo tee /etc/udev/rules.d/50-m8.rules > /dev/null
```

### Reload the rules

Tell the system to read the new permissions you just added:

```
sudo udevadm control --reload-rules
sudo udevadm trigger
```

### Apply and verify

Instead of rebooting the entire system, you can just physically reset the connection.

Unplug the M8 USB cable from the Raspberry Pi.

Plug it back in (this forces the Pi to apply the new rules to the device).

Run the following command to check if the system sees it:

```
lsusb
```
If you see something like "Van Ooijen Technische Informatica M8", it should be working fine.

## 10. Run the application

```
./m8c
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
