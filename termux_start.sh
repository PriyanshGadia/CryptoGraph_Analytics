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
pkg install python nodejs rust git binutils make clang libffi openssl -y

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

echo "[*] Setting up Backend Virtual Environment..."
cd "${DIR}/backend"
if [ ! -d "venv" ]; then
    python -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip

# Termux might struggle with pre-built wheels for some ML libraries.
# Installing requirements...
MATHLIB=m pip install -r requirements.txt

echo "[*] Setting up Frontend..."
cd "${DIR}/frontend"
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

# Start frontend in background
cd "${DIR}/frontend"
npm run dev &
FRONTEND_PID=$!

echo "[*] Servers are starting..."
echo "[*] Open your mobile browser and navigate to: http://localhost:3000"
echo ""
echo "Press CTRL+C to stop."

trap "kill $BACKEND_PID $FRONTEND_PID" EXIT
wait
