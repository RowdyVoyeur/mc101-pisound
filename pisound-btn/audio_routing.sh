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
        # Routing 1: M8 to MC101
        if [ "$MC101_ALIVE" = true ]; then
            connect M8_in:capture_1 MC101_out:playback_3
            connect M8_in:capture_2 MC101_out:playback_4
        else
            connect system:capture_1 M8_out:playback_1
            connect system:capture_2 M8_out:playback_2
            connect M8_in:capture_1 system:playback_1
            connect M8_in:capture_2 system:playback_2
        fi
        ;;

    "2")
        # Routing 2: M8 to MC101 and Pisound In to MC101
        if [ "$MC101_ALIVE" = true ]; then
            connect system:capture_1 MC101_out:playback_3
            connect system:capture_2 MC101_out:playback_4
            connect M8_in:capture_1 MC101_out:playback_3
            connect M8_in:capture_2 MC101_out:playback_4
        else
            connect system:capture_1 M8_out:playback_1
            connect system:capture_2 M8_out:playback_2
            connect M8_in:capture_1 system:playback_1
            connect M8_in:capture_2 system:playback_2
        fi
        ;;

    "3")
        # Routing 3: MC101 to Pisound Out and M8 to Pisound Out
        if [ "$MC101_ALIVE" = true ]; then
            connect MC101_in:capture_1 system:playback_1
            connect MC101_in:capture_2 system:playback_2
        fi
            connect M8_in:capture_1 system:playback_1
            connect M8_in:capture_2 system:playback_2
        ;;
        
    "4")
        # Routing 4: MC101 to M8 to Pisound Out
        if [ "$MC101_ALIVE" = true ]; then
            connect MC101_in:capture_1 M8_out:playback_1
            connect MC101_in:capture_2 M8_out:playback_2
        fi
            connect M8_in:capture_1 system:playback_1
            connect M8_in:capture_2 system:playback_2
        ;;
        
    "5")
        # Routing 5: Pisound In to MC101 to M8 to Pisound Out
        if [ "$MC101_ALIVE" = true ]; then
            connect system:capture_1 MC101_out:playback_3
            connect system:capture_2 MC101_out:playback_4
            connect MC101_in:capture_1 M8_out:playback_1
            connect MC101_in:capture_2 M8_out:playback_2
        fi
            connect M8_in:capture_1 system:playback_1
            connect M8_in:capture_2 system:playback_2
        ;;
        
    "6")
        # Routing 6: Pisound In to MC101 to Pisound Out and Pisound In to M8 to Pisound Out
        if [ "$MC101_ALIVE" = true ]; then
            connect system:capture_1 MC101_out:playback_3
            connect system:capture_2 MC101_out:playback_4
            connect MC101_in:capture_1 system:playback_1
            connect MC101_in:capture_2 system:playback_2
        fi
            connect system:capture_1 M8_out:playback_1
            connect system:capture_2 M8_out:playback_2
            connect M8_in:capture_1 system:playback_1
            connect M8_in:capture_2 system:playback_2
        ;;
        
    "7")
        # Routing 7: Pisound In to M8 to MC101 to Pisound Out
        connect system:capture_1 M8_out:playback_1
        connect system:capture_2 M8_out:playback_2
        if [ "$MC101_ALIVE" = true ]; then
            connect M8_in:capture_1 MC101_out:playback_3
            connect M8_in:capture_2 MC101_out:playback_4
            connect MC101_in:capture_1 system:playback_1
            connect MC101_in:capture_2 system:playback_2
        else
            connect M8_in:capture_1 system:playback_1
            connect M8_in:capture_2 system:playback_2
        fi
        ;;
        
    "8")
        # Routing 8: Pisound In to MC101 (Left Channel) and M8 to MC101 (Right Channel)
        if [ "$MC101_ALIVE" = true ]; then
            connect system:capture_1 MC101_out:playback_3
            connect system:capture_2 MC101_out:playback_3
            connect M8_in:capture_1 MC101_out:playback_4
            connect M8_in:capture_2 MC101_out:playback_4
        else
            connect M8_in:capture_1 system:playback_1
            connect M8_in:capture_2 system:playback_2
        fi
        ;;
esac

# Flash the Pisound LEDs to confirm the routing changed successfully
flash_leds 100