#!/bin/sh

. /usr/local/pisound/scripts/common/common.sh

flash_leds 1
log "Preparing to reset audio connections."

# 1. Kill old bridges
killall -s SIGINT alsa_out alsa_in 2>/dev/null
sleep 2
killall -9 alsa_out alsa_in 2>/dev/null
sleep 3

# 2. Setup strict JACK environment variables
# This stops root/systemd from getting lost and forces it into the patch user's audio session
export HOME=/home/patch
export USER=patch
export XDG_RUNTIME_DIR=/run/user/1000
export JACK_NO_START_SERVER=1

# Helper function for connections (Preserves the environment variables)
connect() {
    sudo -E -u patch jack_connect "$1" "$2" >/dev/null 2>&1
}

# Helper function for bridges (Escapes Pisound button shutdown trap AND injects env vars)
launch_bridge() {
    sudo systemd-run -p Type=simple --uid=patch --setenv=HOME=/home/patch --setenv=USER=patch --setenv=XDG_RUNTIME_DIR=/run/user/1000 --setenv=JACK_NO_START_SERVER=1 --quiet "$@"
}

# 3. Check for MC101 and open bridges if present
MC101_CONNECTED=false
if [ $(aplay -l | grep -c "MC101") -ne 0 ]; then
  MC101_CONNECTED=true
  launch_bridge alsa_in -j "MC101_in" -d hw:MC101,DEV=0 -r 44100 -p 64 -n 4 -c 10
  launch_bridge alsa_out -j "MC101_out" -d hw:MC101,DEV=0 -r 44100 -p 64 -n 4 -c 4
fi

# 4. Open M8 bridges (Always)
launch_bridge alsa_in -j "M8_in" -d hw:M8,DEV=0 -r 44100 -p 64 -n 4 -c 2
launch_bridge alsa_out -j "M8_out" -d hw:M8,DEV=0 -r 44100 -p 64 -n 4 -c 2

# Wait for the new hardware bridges to initialize inside JACK
sleep 5

# --- AUDIO ROUTING ---
if [ "$MC101_CONNECTED" = true ]; then
  connect M8_in:capture_1 MC101_out:playback_3
  connect M8_in:capture_2 MC101_out:playback_4
else
  connect system:capture_1 M8_out:playback_1
  connect system:capture_2 M8_out:playback_2
  connect M8_in:capture_1 system:playback_1
  connect M8_in:capture_2 system:playback_2
fi

log "Audio connections reset successfully."
flash_leds 100