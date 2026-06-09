#!/bin/sh
# Copyright 2026 Ricardo Simoes
# SPDX-License-Identifier: MIT

. /usr/local/pisound/scripts/common/common.sh

LOG_FILE="/tmp/mc101-pisound-reset.log"
PATCH_USER="patch"

log_reset() {
    message="$1"
    log "$message"
    echo "$(date '+%Y-%m-%d %H:%M:%S') $message" >> "$LOG_FILE"
}

as_patch() {
    su "$PATCH_USER" -c "$1"
}

port_exists() {
    as_patch "jack_lsp '$1' >/dev/null 2>&1"
}

connection_exists() {
    as_patch "jack_lsp -c '$1' 2>/dev/null | grep -q '^   $2$'"
}

connect() {
    source_port="$1"
    destination_port="$2"

    if as_patch "jack_connect '$source_port' '$destination_port' >/dev/null 2>&1"; then
        log_reset "Connected: $source_port -> $destination_port"
        return 0
    fi

    # jack_connect returns failure if the connection already exists. Treat that as OK.
    if connection_exists "$source_port" "$destination_port"; then
        log_reset "Already connected: $source_port -> $destination_port"
        return 0
    fi

    log_reset "ERROR: Could not connect: $source_port -> $destination_port"
    return 1
}

require_port() {
    port="$1"

    if port_exists "$port"; then
        return 0
    fi

    log_reset "ERROR: Required JACK port is missing: $port"
    return 1
}

reset_connections() {
    log_reset "Clearing current JACK audio connections."

    su "$PATCH_USER" -c '
        jack_lsp -c | awk '\''
            /^[^[:space:]]/ { source = $0; next }
            /^[[:space:]]/ {
                destination = $0
                sub(/^[[:space:]]+/, "", destination)
                if (source != "" && destination != "") {
                    print source "|" destination
                }
            }
        '\'' | while IFS="|" read -r source destination; do
            jack_disconnect "$source" "$destination" >/dev/null 2>&1
        done
    '
}

mc101_present() {
    aplay -l 2>/dev/null | grep -q "MC101"
}

prepare_mc101_default_route() {
    missing=0

    require_port "M8_in:capture_1" || missing=1
    require_port "M8_in:capture_2" || missing=1
    require_port "MC101_out:playback_3" || missing=1
    require_port "MC101_out:playback_4" || missing=1

    [ "$missing" -eq 0 ]
}

prepare_standalone_default_route() {
    missing=0

    require_port "system:capture_1" || missing=1
    require_port "system:capture_2" || missing=1
    require_port "system:playback_1" || missing=1
    require_port "system:playback_2" || missing=1
    require_port "M8_in:capture_1" || missing=1
    require_port "M8_in:capture_2" || missing=1
    require_port "M8_out:playback_1" || missing=1
    require_port "M8_out:playback_2" || missing=1

    [ "$missing" -eq 0 ]
}

connect_mc101_default_route() {
    connect M8_in:capture_1 MC101_out:playback_3
    connect M8_in:capture_2 MC101_out:playback_4
}

connect_standalone_default_route() {
    connect system:capture_1 M8_out:playback_1
    connect system:capture_2 M8_out:playback_2
    connect M8_in:capture_1 system:playback_1
    connect M8_in:capture_2 system:playback_2
}

flash_leds 1
: > "$LOG_FILE"
log_reset "Resetting JACK connections only. Bridges and JACK server will not be restarted."

if ! as_patch "jack_lsp >/dev/null 2>&1"; then
    log_reset "ERROR: JACK is not reachable from user $PATCH_USER. Connections were not changed."
    flash_leds 3
    exit 1
fi

if mc101_present; then
    log_reset "MC101 detected. Preparing m8c.sh default MC-101 route."

    if ! prepare_mc101_default_route; then
        log_reset "ERROR: Cannot apply MC-101 default route because one or more bridge ports are missing."
        log_reset "This reset script only clears and reconnects JACK connections. It does not recreate alsa_in/alsa_out bridges."
        log_reset "Current JACK ports:"
        as_patch "jack_lsp" >> "$LOG_FILE" 2>&1
        flash_leds 3
        exit 1
    fi

    reset_connections
    sleep 0.5
    connect_mc101_default_route
else
    log_reset "MC101 not detected. Preparing m8c.sh standalone Pisound/M8 route."

    if ! prepare_standalone_default_route; then
        log_reset "ERROR: Cannot apply standalone route because one or more bridge ports are missing."
        log_reset "This reset script only clears and reconnects JACK connections. It does not recreate alsa_in/alsa_out bridges."
        log_reset "Current JACK ports:"
        as_patch "jack_lsp" >> "$LOG_FILE" 2>&1
        flash_leds 3
        exit 1
    fi

    reset_connections
    sleep 0.5
    connect_standalone_default_route
fi

log_reset "Current JACK connections:"
as_patch "jack_lsp -c" >> "$LOG_FILE" 2>&1
log_reset "JACK connections reset successfully."
flash_leds 100