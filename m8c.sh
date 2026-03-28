#!/bin/bash

# 1. Check for MC101 and open bridges if present
if [ $(aplay -l | grep -c "MC101") -eq 0 ]; then
  echo "MC101 not detected. Audio will route to Pisound."
  MC101_CONNECTED=false
else
  echo "MC101 detected. Audio will route to MC101 only."
  MC101_CONNECTED=true
  alsa_in -j "MC101_in" -d hw:MC101,DEV=0 -r 44100 -p 64 -n 4 -c 10 &
  alsa_out -j "MC101_out" -d hw:MC101,DEV=0 -r 44100 -p 64 -n 4 -c 4 &
fi

# 2. Open M8 bridges (Always)
alsa_in -j "M8_in" -d hw:M8,DEV=0 -r 44100 -p 64 -n 4 -c 2 &
alsa_out -j "M8_out" -d hw:M8,DEV=0 -r 44100 -p 64 -n 4 -c 2 &

# Wait for hardware to initialize
sleep 4

# --- AUDIO ROUTING ---

if [ "$MC101_CONNECTED" = true ]; then
  # --- MC-101 MODE ---
  
  # Connect M8 Out to MC101 In (Hear M8 through MC101)
  jack_connect M8_in:capture_1 MC101_out:playback_3 2>/dev/null
  jack_connect M8_in:capture_2 MC101_out:playback_4 2>/dev/null

  # Connect Pisound In to MC101 In (Record mic/audio onto MC101)
  jack_connect system:capture_1 MC101_out:playback_3 2>/dev/null
  jack_connect system:capture_2 MC101_out:playback_4 2>/dev/null

else
  # --- PISOUND STANDALONE MODE ---

  # Connect M8 Out to System In (Hear M8 through Pisound)
  jack_connect M8_in:capture_1 system:playback_1 2>/dev/null
  jack_connect M8_in:capture_2 system:playback_2 2>/dev/null

  # Connect Pisound In to M8 In (Record mic/audio onto M8)
  jack_connect system:capture_1 M8_out:playback_1 2>/dev/null
  jack_connect system:capture_2 M8_out:playback_2 2>/dev/null
fi

# --- START APPLICATIONS ---

# Start M8C in the background and save its Process ID
pushd /home/patch/mc101-pisound
./m8c &
M8C_PID=$!
popd

# Wait for M8C to completely initialize the display and overlay pipe
sleep 5

# Start Zeditor in the background
python3 /home/patch/mc101-pisound/scripts/zeditor.py &
ZEDITOR_PID=$!

# The script pauses here and waits until you close M8C
wait $M8C_PID

# --- CLEANUP ---
# When M8C closes, kill Zeditor and audio bridges
kill $ZEDITOR_PID 2>/dev/null
killall -s SIGINT alsa_out alsa_in 2>/dev/null

# Shutdown after quitting M8C
# sleep 2
# sudo shutdown now