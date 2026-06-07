#!/bin/sh

. /usr/local/pisound/scripts/common/common.sh

PATCH_USER="patch"
PATCH_HOME="/home/patch"
PATCH_UID="$(id -u "$PATCH_USER" 2>/dev/null || echo 1000)"
PATCH_RUNTIME="/run/user/$PATCH_UID"

SAMPLE_RATE=44100
PERIOD_SIZE=64
PERIODS=4

# Set to 1 to restart the JACK user service before rebuilding the audio bridge ports.
# This is useful after major audio glitches. If JACK cannot be restarted through
# systemd, the script falls back to using the currently running JACK server.
RESET_JACK_SERVER="${RESET_JACK_SERVER:-1}"

flash_leds 1
log "Rebuilding audio connections from scratch."

run_as_patch() {
    sudo -u "$PATCH_USER" env \
        HOME="$PATCH_HOME" \
        USER="$PATCH_USER" \
        XDG_RUNTIME_DIR="$PATCH_RUNTIME" \
        JACK_NO_START_SERVER=1 \
        "$@"
}

jack_cmd() {
    run_as_patch "$@"
}

jack_is_running() {
    jack_cmd jack_lsp >/dev/null 2>&1
}

wait_for_jack() {
    timeout="${1:-12}"
    elapsed=0

    while [ "$elapsed" -lt "$timeout" ]; do
        if jack_is_running; then
            return 0
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done

    return 1
}

try_restart_jack() {
    if [ "$RESET_JACK_SERVER" != "1" ]; then
        return 1
    fi

    log "Attempting to restart JACK."

    run_as_patch systemctl --user restart jack.service >/dev/null 2>&1 && wait_for_jack 15 && return 0
    run_as_patch systemctl --user restart jackd.service >/dev/null 2>&1 && wait_for_jack 15 && return 0
    run_as_patch jack_control stop >/dev/null 2>&1
    sleep 2
    run_as_patch jack_control start >/dev/null 2>&1 && wait_for_jack 15 && return 0

    return 1
}

try_start_jack() {
    log "Ensuring JACK is running."

    jack_is_running && return 0

    run_as_patch systemctl --user start jack.service >/dev/null 2>&1 && wait_for_jack 15 && return 0
    run_as_patch systemctl --user start jackd.service >/dev/null 2>&1 && wait_for_jack 15 && return 0
    run_as_patch jack_control start >/dev/null 2>&1 && wait_for_jack 15 && return 0

    return 1
}

wait_for_alsa_card() {
    card_name="$1"
    timeout="${2:-8}"
    elapsed=0

    while [ "$elapsed" -lt "$timeout" ]; do
        if aplay -l 2>/dev/null | grep -q "$card_name"; then
            return 0
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done

    return 1
}

launch_bridge() {
    sudo systemd-run \
        --quiet \
        --collect \
        -p Type=simple \
        --uid="$PATCH_USER" \
        --setenv=HOME="$PATCH_HOME" \
        --setenv=USER="$PATCH_USER" \
        --setenv=XDG_RUNTIME_DIR="$PATCH_RUNTIME" \
        --setenv=JACK_NO_START_SERVER=1 \
        -- "$@"
}

wait_for_port() {
    port="$1"
    timeout="${2:-15}"
    elapsed=0

    while [ "$elapsed" -lt "$timeout" ]; do
        if jack_cmd jack_lsp "$port" >/dev/null 2>&1; then
            return 0
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done

    log "WARNING: JACK port not available: $port"
    return 1
}

connect_ports() {
    source_port="$1"
    destination_port="$2"
    timeout="${3:-10}"
    elapsed=0

    while [ "$elapsed" -lt "$timeout" ]; do
        if jack_cmd jack_connect "$source_port" "$destination_port" >/dev/null 2>&1; then
            log "Connected: $source_port -> $destination_port"
            return 0
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done

    log "WARNING: Could not connect: $source_port -> $destination_port"
    return 1
}

# 1. Stop old audio bridges.
log "Stopping old ALSA/JACK bridges."
killall -s SIGINT alsa_out alsa_in 2>/dev/null
sleep 2
killall -9 alsa_out alsa_in 2>/dev/null
sleep 2

# 2. Restart or start JACK.
if ! try_restart_jack; then
    log "JACK restart was not available or did not complete."
fi

if ! try_start_jack; then
    log "ERROR: JACK is not running. Audio reset aborted."
    flash_leds 3
    exit 1
fi

# 3. Detect hardware after the reset attempt.
if wait_for_alsa_card "MC101" 3; then
    MC101_CONNECTED=true
    log "MC101 detected."
else
    MC101_CONNECTED=false
    log "MC101 not detected. Using Pisound standalone routing."
fi

if ! wait_for_alsa_card "M8" 10; then
    log "ERROR: M8 audio device not detected. Audio reset aborted."
    flash_leds 3
    exit 1
fi

log "M8 detected."

# 4. Recreate audio bridges to match m8c.sh.
if [ "$MC101_CONNECTED" = true ]; then
    launch_bridge alsa_in -j "MC101_in" -d hw:MC101,DEV=0 -r "$SAMPLE_RATE" -p "$PERIOD_SIZE" -n "$PERIODS" -q 0 -c 10
    sleep 0.5
    launch_bridge alsa_out -j "MC101_out" -d hw:MC101,DEV=0 -r "$SAMPLE_RATE" -p "$PERIOD_SIZE" -n "$PERIODS" -q 0 -c 4
    sleep 0.5
fi

launch_bridge alsa_in -j "M8_in" -d hw:M8,DEV=0 -r "$SAMPLE_RATE" -p "$PERIOD_SIZE" -n "$PERIODS" -q 0 -c 2
sleep 0.5
launch_bridge alsa_out -j "M8_out" -d hw:M8,DEV=0 -r "$SAMPLE_RATE" -p "$PERIOD_SIZE" -n "$PERIODS" -q 0 -c 2

# Wait for the new hardware bridges to initialise inside JACK.
sleep 4

# 5. Wait for the required ports, then recreate the same routing as m8c.sh.
wait_for_port "M8_in:capture_1" 15
wait_for_port "M8_in:capture_2" 15

if [ "$MC101_CONNECTED" = true ]; then
    wait_for_port "MC101_out:playback_3" 15
    wait_for_port "MC101_out:playback_4" 15

    connect_ports M8_in:capture_1 MC101_out:playback_3
    connect_ports M8_in:capture_2 MC101_out:playback_4
else
    wait_for_port "system:capture_1" 15
    wait_for_port "system:capture_2" 15
    wait_for_port "system:playback_1" 15
    wait_for_port "system:playback_2" 15
    wait_for_port "M8_out:playback_1" 15
    wait_for_port "M8_out:playback_2" 15

    connect_ports system:capture_1 M8_out:playback_1
    connect_ports system:capture_2 M8_out:playback_2
    connect_ports M8_in:capture_1 system:playback_1
    connect_ports M8_in:capture_2 system:playback_2
fi

log "Audio connections rebuilt successfully."
flash_leds 100