#!/bin/sh

. /usr/local/pisound/scripts/common/common.sh

# Helper function to easily connect ports as the 'patch' user
connect() {
    su patch -c "jack_connect $1 $2 >/dev/null 2>&1"
}

# This finds every active connection and disconnects it dynamically
reset_connections() {
    su patch -c '
    connected_ports=$(jack_lsp -c | grep -v "^ ")
    if [[ -n "$connected_ports" ]]; then
        while read -r port; do
            connections=$(jack_lsp -c "$port" | grep "^ ")
            if [[ -n "$connections" ]]; then
                while read -r connection; do
                    jack_disconnect "$port" "${connection#*> }" >/dev/null 2>&1
                done <<< "$connections"
            fi
        done <<< "$connected_ports"
    fi
    '
}

# Check if MC-101 is physically plugged in
if [ $(aplay -l | grep -c "MC101") -eq 0 ]; then
    MC101_ALIVE=false
else
    MC101_ALIVE=true
fi

# Wipe the slate clean before applying the requested route
reset_connections
sleep 0.5 # Give JACK a half-second to clear the board

case "$1" in
    "1")
        # State 1: M8 -> MC101 -> OUT
        if [ "$MC101_ALIVE" = true ]; then
            connect MC101_in:capture_1 system:playback_1
            connect MC101_in:capture_2 system:playback_2
        fi
        # Even if MC101 is missing, M8 still routes safely
        connect M8_in:capture_1 MC101_out:playback_3
        connect M8_in:capture_2 MC101_out:playback_4
        ;;
        
    "2")
        # State 2: MC101 -> OUT / M8 -> OUT
        if [ "$MC101_ALIVE" = true ]; then
            connect MC101_in:capture_1 system:playback_1
            connect MC101_in:capture_2 system:playback_2
        fi
        connect M8_in:capture_1 system:playback_1
        connect M8_in:capture_2 system:playback_2
        ;;
        
    "3")
        # State 3: MC101 -> M8 -> OUT
        if [ "$MC101_ALIVE" = true ]; then
            connect MC101_in:capture_1 M8_out:playback_1
            connect MC101_in:capture_2 M8_out:playback_2
        fi
        connect M8_in:capture_1 system:playback_1
        connect M8_in:capture_2 system:playback_2
        ;;
        
    "4")
        # State 4: IN -> MC101 -> M8 -> OUT
        # Add your lines here using the connect() function
        ;;
        
    "5")
        # State 5: IN -> MC101 -> OUT / IN -> M8 -> OUT
        # Add your lines here
        ;;
        
    "6")
        # State 6: IN -> M8 -> MC101 -> OUT
        # Add your lines here
        ;;
        
    "7")
        # State 7: M8 -> MC101 / IN -> MC101
        connect M8_in:capture_1 MC101_out:playback_3
        connect M8_in:capture_2 MC101_out:playback_4
        connect system:capture_1 MC101_out:playback_3
        connect system:capture_2 MC101_out:playback_4
        ;;
        
    "8")
        # State 8: IN -> MC101(L) / M8 -> MC101(R)
        # Add your lines here
        ;;
esac

# Flash the Pisound LEDs to confirm the routing changed successfully
flash_leds 100