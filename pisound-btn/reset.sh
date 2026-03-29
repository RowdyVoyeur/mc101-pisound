#!/bin/sh

. /usr/local/pisound/scripts/common/common.sh

flash_leds 1
log "Preparing to reset audio connections."

# 1. Ruthlessly kill any frozen ALSA bridges (using -9 forces them to drop the USB ports)
killall -9 alsa_out alsa_in 2>/dev/null

# Give the Linux kernel 3 seconds to fully release the USB audio devices
sleep 3

# Helper function to easily connect ports as the 'patch' user
connect() {
    sudo -u patch jack_connect $1 $2 >/dev/null 2>&1
}

# 2. Check for MC101 and open bridges if present
if [ $(aplay -l | grep -c "MC101") -eq 0 ]; then
  echo "MC101 not detected. Audio will route to Pisound."
  MC101_CONNECTED=false
else
  echo "MC101 detected. Audio will route to MC101 only."
  MC101_CONNECTED=true
  # MUST run as patch user so JACK sees them
  sudo -u patch alsa_in -j "MC101_in" -d hw:MC101,DEV=0 -r 44100 -p 64 -n 4 -c 10 &
  sudo -u patch alsa_out -j "MC101_out" -d hw:MC101,DEV=0 -r 44100 -p 64 -n 4 -c 4 &
fi

# 3. Open M8 bridges (Always)
sudo -u patch alsa_in -j "M8_in" -d hw:M8,DEV=0 -r 44100 -p 64 -n 4 -c 2 &
sudo -u patch alsa_out -j "M8_out" -d hw:M8,DEV=0 -r 44100 -p 64 -n 4 -c 2 &

# Wait for the new hardware bridges to initialize inside JACK
sleep 4

# --- AUDIO ROUTING (Mirrored from m8c.sh) ---

if [ "$MC101_CONNECTED" = true ]; then
  # --- MC-101 MODE ---
  
  # Connect M8 Out to MC101 In (hear M8 through MC101)
  connect M8_in:capture_1 MC101_out:playback_3
  connect M8_in:capture_2 MC101_out:playback_4

else
  # --- PISOUND STANDALONE MODE ---

  # Connect Pisound In to M8 In (record mic/audio onto M8)
  connect system:capture_1 M8_out:playback_1
  connect system:capture_2 M8_out:playback_2
  
  # Connect M8 Out to System In (hear M8 through Pisound)
  connect M8_in:capture_1 system:playback_1
  connect M8_in:capture_2 system:playback_2
fi

log "Audio connections reset successfully."
flash_leds 100