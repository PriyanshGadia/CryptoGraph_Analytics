#!/data/data/com.termux/files/usr/bin/bash

echo "==================================================="
echo "    CryptoGraph Analytics Termux (Android) Setup"
echo "==================================================="
echo ""

echo "[*] Requesting storage permissions..."
termux-setup-storage || true

echo "[*] Updating package list..."
pkg update -y && pkg upgrade -y

echo "[*] Installing required binaries (Python, Node.js, Rust, Git, Build-essentials)..."
pkg install python nodejs rust git binutils make clang libffi openssl cmake ninja pkg-config -y

# Install prebuilt scientific packages into Termux's system Python
# (avoids compiling numpy/pandas/cryptography from source — saves 30+ min)
echo "[*] Installing system-level Python packages..."
pip install numpy pandas cryptography 2>/dev/null || true

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Use Termux's $TMPDIR (writable), NOT /tmp (permission denied on Android)
TERMUX_TMP="${TMPDIR:-$PREFIX/tmp}"
mkdir -p "$TERMUX_TMP"

# ===================================================================
# BACKEND SETUP
# ===================================================================
echo "[*] Setting up Backend Virtual Environment..."
cd "${DIR}/backend"

# If venv exists but was NOT created with --system-site-packages
# (e.g. from a previous install_unix.sh run), nuke it and recreate.
NEEDS_RECREATE=false
if [ -d "venv" ]; then
    if [ -f "venv/pyvenv.cfg" ]; then
        SSP=$(grep -i "include-system-site-packages" venv/pyvenv.cfg | awk -F= '{print $2}' | tr -d ' ')
        if [ "$SSP" != "true" ]; then
            echo "    [!] Existing venv lacks system-site-packages. Recreating..."
            NEEDS_RECREATE=true
        fi
    else
        NEEDS_RECREATE=true
    fi
fi

if [ "$NEEDS_RECREATE" = true ]; then
    rm -rf venv
fi

if [ ! -d "venv" ]; then
    echo "    Creating virtual environment with --system-site-packages..."
    python -m venv venv --system-site-packages
fi

source venv/bin/activate
pip install --upgrade pip

# Create a Termux-compatible requirements file:
#   - Remove 'prophet' (requires CmdStan C++ toolchain, not viable on Android)
#   - Remove 'ccxt' (depends on coincurve which fails to build on ARM64)
#   - Remove packages already provided by Termux system (numpy, pandas, cryptography)
echo "[*] Generating Termux-compatible requirements..."
grep -viE '^(prophet|ccxt|numpy|pandas|cryptography)' requirements.txt > "${TERMUX_TMP}/requirements_termux.txt"

echo "[*] Installing Python requirements (this may take a while)..."
MATHLIB=m pip install -r "${TERMUX_TMP}/requirements_termux.txt"
rm -f "${TERMUX_TMP}/requirements_termux.txt"

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

if [ ! -d "node_modules" ]; then
    npm install
fi

# ---------------------------------------------------------------
# CRITICAL: Fix Next.js SWC on Android ARM64
# ---------------------------------------------------------------
# Next.js 14.2.x fatal crashes on Android if it cannot load a native SWC binary.
# We fixed this by explicitly adding @next/swc-wasm-nodejs to package.json.
# Next.js will automatically detect and load this WebAssembly fallback.
# ---------------------------------------------------------------
export NEXT_PRIVATE_SKIP_SWC_DOWNLOAD=1

# Clean up any old .babelrc to ensure SWC WASM is strictly used
rm -f .babelrc

echo ""
echo "[*] Launching Servers..."

export PYTHONPATH="${DIR}/backend:${DIR}"

# Start backend in background
cd "${DIR}/backend"
source venv/bin/activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Start frontend in background
cd "${DIR}/frontend"
npm run dev -- -H 0.0.0.0 --webpack &
FRONTEND_PID=$!

echo "[*] Servers are starting..."
echo "[*] Open your mobile browser and navigate to: http://localhost:3000"
echo ""
echo "Press CTRL+C to stop."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT
wait
