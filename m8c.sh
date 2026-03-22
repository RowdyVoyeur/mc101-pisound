#!/bin/bash

# Check if the Instrument with the Card Name "MC101" is connected
if [ $(aplay -l | grep -c "MC101") -eq 0 ]; then
  echo "MC101 not detected, skipping connection."
else
  echo "MC101 detected, connecting."
  # Open audio interface between MC101 Out and System In
  alsa_in -j "MC101_in" -d hw:MC101,DEV=0 -r 44100 -p 64 -n 4 -c 10 &
  # Open audio interface between System Out and MC101 In
  alsa_out -j "MC101_out" -d hw:MC101,DEV=0 -r 44100 -p 64 -n 4 -c 4 &
fi

# Open audio interface between M8 Out and System In
alsa_in -j "M8_in" -d hw:M8,DEV=0 -r 44100 -p 64 -n 4 -c 2 &
# Open audio interface between System Out and M8 In
alsa_out -j "M8_out" -d hw:M8,DEV=0 -r 44100 -p 64 -n 4 -c 2 &

sleep 4

# Connect audio of M8 Out to MC101 In (Allows hearing M8 through MC101)
jack_connect M8_in:capture_1 MC101_out:playback_3 2>/dev/null
jack_connect M8_in:capture_2 MC101_out:playback_4 2>/dev/null

# Connect audio of M8 Out to System In (Allows hearing M8 through Pisound)
jack_connect M8_in:capture_1 system:playback_1
jack_connect M8_in:capture_2 system:playback_2

# Connect audio of System In to M8 In (Allows sampling into M8)
jack_connect system:capture_1 M8_out:playback_1
jack_connect system:capture_2 M8_out:playback_2

# Start M8C IN THE BACKGROUND FIRST (so it creates the overlay pipe)
pushd /home/patch/m8c-rpi4
./m8c &
popd

# Wait 3 seconds, then start Zeditor in the foreground (NO SUDO)
sleep 3
python3 /home/patch/mc101-pisound/scripts/zeditor.py

# Clean up audio routing (added python3 and m8c so they close cleanly)
killall -s SIGINT alsa_out alsa_in m8c python3 2>/dev/null

# Shutdown after quitting M8C
# sleep 2
# sudo shutdown now