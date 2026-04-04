#!/bin/bash

# 1. Hardware detection
# Check for MC-101
if [ $(aplay -l | grep -c "MC101") -eq 0 ]; then
  MC101_CONNECTED=false
  echo "MC101 not detected."
else
  MC101_CONNECTED=true
  echo "MC101 detected."
fi

# Check for nanoKONTROL
if [ $(amidi -l | grep -ic "nanoKONTROL") -eq 0 ]; then
  NANO_CONNECTED=false
  echo "nanoKONTROL not detected."
else
  NANO_CONNECTED=true
  echo "nanoKONTROL detected."
fi

# 2. Start audio bridges
if [ "$MC101_CONNECTED" = true ]; then
  alsa_in -j "MC101_in" -d hw:MC101,DEV=0 -r 44100 -p 64 -n 4 -q 0 -c 10 &
  alsa_out -j "MC101_out" -d hw:MC101,DEV=0 -r 44100 -p 64 -n 4 -q 0 -c 4 &
fi

alsa_in -j "M8_in" -d hw:M8,DEV=0 -r 44100 -p 64 -n 4 -q 0 -c 2 &
alsa_out -j "M8_out" -d hw:M8,DEV=0 -r 44100 -p 64 -n 4 -q 0 -c 2 &

# Wait for audio bridges to initialize inside JACK safely
sleep 4

# 3. Start audio routing
if [ "$MC101_CONNECTED" = true ]; then
  # MC-101 mode
  jack_connect M8_in:capture_1 MC101_out:playback_3 2>/dev/null
  jack_connect M8_in:capture_2 MC101_out:playback_4 2>/dev/null
else
  # Pisound standalone mode
  jack_connect system:capture_1 M8_out:playback_1 2>/dev/null
  jack_connect system:capture_2 M8_out:playback_2 2>/dev/null
  jack_connect M8_in:capture_1 system:playback_1 2>/dev/null
  jack_connect M8_in:capture_2 system:playback_2 2>/dev/null
fi

# 4. Start visuals
# Now that USB audio is stable, launch the display
pushd /home/patch/mc101-pisound
./m8c &
M8C_PID=$!
popd

# 5. Conditional Python scripts
# Define empty PID variables for safe cleanup later
PC2NOTE_PID=""
NANO_PID=""

# Script that requires ONLY the MC-101
if [ "$MC101_CONNECTED" = true ]; then
  python3 /home/patch/mc101-pisound/scripts/pc2note.py &
  PC2NOTE_PID=$!
fi

# The Master Script: Requires the nanoKONTROL
if [ "$NANO_CONNECTED" = true ]; then
  python3 /home/patch/mc101-pisound/scripts/nanokontroller.py &
  NANO_PID=$!
fi

# 6. Hold script open
# Pause here and wait until the user quits M8C
wait $M8C_PID

# 7. Cleanup
# Kill only the python scripts that were actually launched
[ -n "$PC2NOTE_PID" ] && kill $PC2NOTE_PID 2>/dev/null
[ -n "$NANO_PID" ] && kill $NANO_PID 2>/dev/null

# Clean up audio routing
killall -s SIGINT alsa_out alsa_in 2>/dev/null

# 8. Shutdown
# Shutdown after quitting M8C
sleep 2
sudo shutdown now