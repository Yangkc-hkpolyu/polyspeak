#!/bin/sh
set -eu
cd "$(dirname "$0")"
export PYTHONNOUSERSITE=1
export TEMP="$PWD/speaking-runtime/temp"
export TMP="$TEMP"
export NUMBA_CACHE_DIR="$PWD/speaking-runtime/numba-cache"
export MPLCONFIGDIR="$PWD/speaking-runtime/matplotlib"
export TORCH_HOME="$PWD/speaking-runtime/torch-cache"
mkdir -p "$TEMP"
if [ ! -x .venv/bin/python ]; then
    printf '%s\n' 'Create a macOS Python environment following START_HERE.md first.'
    exit 1
fi
exec .venv/bin/python -s run-speaking.py
