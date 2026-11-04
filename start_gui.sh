#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
export LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libstdc++.so.6
export LD_LIBRARY_PATH="$PWD/lib:${LD_LIBRARY_PATH:-}"
exec python3 work_time_gui.py
