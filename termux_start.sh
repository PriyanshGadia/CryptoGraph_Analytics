#!/data/data/com.termux/files/usr/bin/bash

echo "==================================================="
echo "    CryptoGraph Analytics Termux (Android) Setup"
echo "==================================================="
echo ""

echo "[*] Requesting storage permissions..."
termux-setup-storage

echo "[*] Updating package list..."
pkg update -y && pkg upgrade -y

echo "[*] Installing required binaries (Python, Node.js, Rust, Git, Build-essentials)..."
# Rust and binutils are required on ARM to compile python wheels like cryptography or tokenizers
# python-numpy and python-pandas are prebuilt Termux packages — much faster than pip
pkg install python nodejs rust git binutils make clang libffi openssl cmake ninja pkg-config -y

# Install prebuilt scientific packages from Termux repos (avoids compiling from source)
pip install numpy pandas cryptography 2>/dev/null || true

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# ===================================================================
# BACKEND SETUP
# ===================================================================
echo "[*] Setting up Backend Virtual Environment..."
cd "${DIR}/backend"

# Use --system-site-packages so Termux's prebuilt numpy/pandas/cryptography are available
if [ ! -d "venv" ]; then
    python -m venv venv --system-site-packages
fi
source venv/bin/activate
pip install --upgrade pip

# Create a Termux-compatible requirements file:
#   - Remove 'prophet' (requires CmdStan C++ toolchain, not viable on Android)
#   - Remove 'ccxt' (depends on coincurve which fails to build on ARM64)
#   - Remove packages already provided by Termux system (numpy, pandas, cryptography)
echo "[*] Generating Termux-compatible requirements..."
grep -viE '^(prophet|ccxt|numpy|pandas|cryptography)' requirements.txt > /tmp/requirements_termux.txt

echo "[*] Installing Python requirements (this may take a while)..."
MATHLIB=m pip install -r /tmp/requirements_termux.txt
rm -f /tmp/requirements_termux.txt

# Install ccxt WITHOUT coincurve (coincurve is only needed for certain exchange auth)
echo "[*] Installing ccxt without native crypto dependencies..."
pip install ccxt --no-deps 2>/dev/null || true
# Install ccxt's Python-only dependencies manually
pip install aiohttp aiodns setuptools certifi 2>/dev/null || true

deactivate

# ===================================================================
# FRONTEND SETUP
# ===================================================================
echo "[*] Setting up Frontend..."
cd "${DIR}/frontend"

# Next.js 14.2.x tries to download @next/swc-android-arm64 which doesn't exist.
# We must:
#   1. Set NEXT_PRIVATE_SKIP_SWC_DOWNLOAD to prevent the fatal 404 download
#   2. Create a .babelrc to tell Next.js to use Babel instead of SWC
# NOTE: .babelrc is NOT checked into git — it's only created on Termux at runtime.
export NEXT_PRIVATE_SKIP_SWC_DOWNLOAD=1

if [ ! -f ".babelrc" ]; then
    echo "[*] Creating Babel config for Termux compatibility (SWC unavailable on ARM64)..."
    echo '{ "presets": ["next/babel"] }' > .babelrc
fi

if [ ! -d "node_modules" ]; then
    npm install
fi

echo ""
echo "[*] Launching Servers..."

export PYTHONPATH="${DIR}/backend:${DIR}"

# Start backend in background
cd "${DIR}/backend"
source venv/bin/activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Start frontend in background (with SWC download disabled)
cd "${DIR}/frontend"
NEXT_PRIVATE_SKIP_SWC_DOWNLOAD=1 npm run dev &
FRONTEND_PID=$!

echo "[*] Servers are starting..."
echo "[*] Open your mobile browser and navigate to: http://localhost:3000"
echo ""
echo "Press CTRL+C to stop."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT
wait
