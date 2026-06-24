#!/bin/bash

# CryptoGraph Analytics Launcher for macOS / Linux / Termux

echo "==================================================="
echo "    Starting CryptoGraph Analytics Environment"
echo "==================================================="
echo ""

# Get the absolute path of the script directory
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Auto-detect Termux (Android) vs standard Unix
if [ -d "/data/data/com.termux" ]; then
    echo "[*] Termux (Android) detected. Handing off to Termux-specific installer..."
    bash "${DIR}/termux_start.sh"
else
    echo "[*] Handing off to the robust Bash installer/runner..."
    bash "${DIR}/install_unix.sh"
fi

