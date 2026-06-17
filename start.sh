#!/bin/bash

# CryptoGraph Analytics Launcher for macOS / Linux

echo "==================================================="
echo "    Starting CryptoGraph Analytics Environment"
echo "==================================================="
echo ""

# Get the absolute path of the script directory
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

echo "[*] Handing off to the robust Bash installer/runner..."
bash "${DIR}/install_unix.sh"
