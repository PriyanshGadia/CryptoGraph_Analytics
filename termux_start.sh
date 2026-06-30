#!/data/data/com.termux/files/usr/bin/bash
# ═══════════════════════════════════════════════════════════════
#    CryptoGraph Analytics — Termux (Android) Proot Setup
# ═══════════════════════════════════════════════════════════════
# This script creates a highly reproducible Ubuntu environment 
# inside Termux using proot-distro, completely bypassing Android's
# libc restrictions. It then executes the standard install script.
# ═══════════════════════════════════════════════════════════════

set -e

echo "==================================================="
echo "    CryptoGraph Analytics Termux Proot Setup"
echo "==================================================="
echo ""

echo "[*] Requesting storage permissions..."
termux-setup-storage || true

echo "[*] Updating Termux packages..."
pkg update -y && pkg upgrade -y

echo "[*] Installing proot-distro..."
pkg install proot-distro -y

# Ensure Ubuntu is installed
if ! proot-distro list | grep -q "ubuntu.*installed"; then
    echo "[*] Installing Ubuntu inside Termux..."
    proot-distro install ubuntu
fi

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Register a cleanup trap to remove the temporary wrapper script on exit
trap 'rm -f "${DIR}/run_in_proot.sh"' EXIT INT TERM

# To avoid issues with Termux permissions inside Ubuntu, we'll
# copy a startup script that runs inside the chroot.
cat << 'EOF' > "${DIR}/run_in_proot.sh"
#!/bin/bash
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y sudo tzdata curl wget git python3 python3-pip python3-venv build-essential
# Ensure Node is installed
if ! command -v node >/dev/null; then
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
    apt-get install -y nodejs
fi
cd /app
# Pass a flag to tell the script it's running inside termux-ubuntu
export RUNNING_IN_PROOT=true
bash install_unix.sh
EOF
chmod +x "${DIR}/run_in_proot.sh"

echo "[*] Entering Ubuntu environment to build and run..."
echo "[!] This will use standard Linux binaries and avoid all Termux build errors."

# Execute the runner script inside Ubuntu, binding the project directory to /app
proot-distro login ubuntu --bind "$DIR:/app" -- bash /app/run_in_proot.sh
