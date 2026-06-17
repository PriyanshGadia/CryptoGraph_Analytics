#!/bin/bash

echo "==================================================="
echo "    CryptoGraph Analytics macOS/Linux Setup & Run"
echo "==================================================="
echo ""

# Detect OS
OS="$(uname -s)"
case "${OS}" in
    Linux*)     machine=Linux;;
    Darwin*)    machine=Mac;;
    *)          machine="UNKNOWN:${OS}"
esac

install_mac() {
    if ! command -v brew >/dev/null; then
        echo "[!] Homebrew not found. Installing Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    fi
    if ! command -v python3 >/dev/null; then
        echo "[*] Installing Python3 via Homebrew..."
        brew install python
    fi
    if ! command -v node >/dev/null; then
        echo "[*] Installing Node.js via Homebrew..."
        brew install node
    fi
}

install_linux() {
    if command -v apt-get >/dev/null; then
        sudo apt-get update
        if ! command -v python3 >/dev/null; then
            echo "[*] Installing Python3..."
            sudo apt-get install -y python3 python3-pip python3-venv
        fi
        if ! command -v node >/dev/null; then
            echo "[*] Installing Node.js..."
            curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
            sudo apt-get install -y nodejs
        fi
    else
        echo "[!] Unsupported Linux package manager. Please manually install Python3 and Node.js."
    fi
}

if [ "$machine" == "Mac" ]; then
    install_mac
elif [ "$machine" == "Linux" ]; then
    install_linux
fi

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

echo "[*] Setting up Backend..."
cd "${DIR}/backend"
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
deactivate

echo "[*] Setting up Frontend..."
cd "${DIR}/frontend"
if [ ! -d "node_modules" ]; then
    npm install
fi

echo ""
echo "[*] Launching Servers..."

# Start Backend
export PYTHONPATH="${DIR}/backend:${DIR}"
cd "${DIR}/backend"
source venv/bin/activate
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# Start Frontend
cd "${DIR}/frontend"
npm run dev &
FRONTEND_PID=$!

echo "[*] Waiting for servers to initialize..."
sleep 8

if command -v xdg-open > /dev/null; then
    xdg-open http://localhost:3000
elif command -v open > /dev/null; then
    open http://localhost:3000
fi

echo "==================================================="
echo "  All systems running! Press CTRL+C to stop servers."
echo "==================================================="

trap "kill $BACKEND_PID $FRONTEND_PID" EXIT
wait
