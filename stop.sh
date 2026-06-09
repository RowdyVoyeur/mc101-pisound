#!/bin/bash
# Copyright 2026 Ricardo Simoes
# SPDX-License-Identifier: MIT

echo "Stopping mc101-pisound module..."
killall -s SIGINT m8c python3 alsa_in alsa_out 2>/dev/null
echo "Module stopped."