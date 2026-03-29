#!/bin/sh

. /usr/local/pisound/scripts/common/common.sh

flash_leds 1
log "Preparing to reset audio connections."

# 1. Gracefully ask ALSA bridges to close so they unregister their ports from JACK cleanly
killall -s SIGINT alsa_out alsa_in 2>/dev/null
sleep 2

# 2. Ruthlessly kill any bridges that were completely frozen and ignored the first command
killall -9 alsa_out alsa_in 2>/dev/null
sleep 2

# Helper function 
connect() {
    su patch -c "jack_connect $1 $2 >/dev/null 2>&1"
}

# 3. Check for MC101 and open bridges if present
if [ $(aplay -l | grep -c "MC101") -eq 0 ]; then
  echo "MC101 not detected. Audio will route to Pisound."
  MC101_CONNECTED=false
else
  echo "MC101 detected. Audio will route to MC101 only."
  MC101_CONNECTED=true
  
  # Use systemd-run to launch bridges safely outside the button's control trap
  sudo systemd-run --uid=patch alsa_in -j "MC101_in" -d hw:MC101,DEV=0 -r 44100 -p 64 -n 4 -c 10
  sudo systemd-run --uid=patch alsa_out -j "MC101_out" -d hw:MC101,DEV=0 -r 44100 -p 64 -n 4 -c 4
fi

# 4. Open M8 bridges (Always)
sudo systemd-run --uid=patch alsa_in -j "M8_in" -d hw:M8,DEV=0 -r 44100 -p 64 -n 4 -c 2
sudo systemd-run --uid=patch alsa_out -j "M8_out" -d hw:M8,DEV=0 -r 44100 -p 64 -n 4 -c 2

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