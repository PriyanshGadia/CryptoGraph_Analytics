#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#    CryptoGraph Analytics — Universal Unix Setup & Run
# ═══════════════════════════════════════════════════════════════
# Highly reproducible setup for macOS, Linux, and Android (via Proot)

echo "==================================================="
echo "    CryptoGraph Analytics Setup & Run"
echo "==================================================="
echo ""

# Termux detection (Redirect to proot launcher)
if [ -d "/data/data/com.termux" ] || [ -n "$TERMUX_VERSION" ]; then
    if [ "$RUNNING_IN_PROOT" != "true" ]; then
        echo "[!] Native Termux detected. Redirecting to highly reproducible Proot setup..."
        DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
        bash "${DIR}/termux_start.sh"
        exit $?
    fi
fi

OS="$(uname -s)"
case "${OS}" in
    Linux*)     machine=Linux;;
    Darwin*)    machine=Mac;;
    *)          machine="UNKNOWN:${OS}"
esac

# ─── 1. System Dependencies ──────────────────────────────────
# (Skipped if running inside Termux proot because termux_start.sh handles it)
if [ "$RUNNING_IN_PROOT" != "true" ]; then
    if [ "$machine" == "Mac" ]; then
        if ! command -v brew >/dev/null; then
            echo "[!] Homebrew not found. Installing Homebrew..."
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        fi
        command -v python3 >/dev/null || brew install python
        command -v node >/dev/null || brew install node
    elif [ "$machine" == "Linux" ]; then
        if command -v apt-get >/dev/null; then
            SUDO=""
            command -v sudo >/dev/null && SUDO="sudo"
            $SUDO apt-get update -y
            command -v python3 >/dev/null || $SUDO apt-get install -y python3 python3-pip python3-venv build-essential
            if ! command -v node >/dev/null; then
                curl -fsSL https://deb.nodesource.com/setup_20.x | $SUDO bash -
                $SUDO apt-get install -y nodejs
            fi
        fi
    fi
fi

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Copy env files if missing
if [ ! -f "${DIR}/backend/.env" ] && [ -f "${DIR}/backend/.env.example" ]; then
    echo "    Creating backend .env file from .env.example..."
    cp "${DIR}/backend/.env.example" "${DIR}/backend/.env"
fi

# ─── 2. Backend Setup ────────────────────────────────────────
echo "[*] Setting up Backend..."
cd "${DIR}/backend"
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
if [ -f "requirements-optional.txt" ]; then
    pip install -r requirements-optional.txt -q 2>/dev/null || true
fi
deactivate

# Copy frontend env file if missing
if [ ! -f "${DIR}/frontend/.env.local" ] && [ -f "${DIR}/frontend/.env.example" ]; then
    echo "    Creating frontend .env.local file from .env.example..."
    cp "${DIR}/frontend/.env.example" "${DIR}/frontend/.env.local"
fi

# ─── 3. Frontend Setup & Build ───────────────────────────────
echo "[*] Setting up Frontend..."
cd "${DIR}/frontend"
if [ ! -d "node_modules" ]; then
    npm install --quiet
fi

# Build for production to avoid RAM/SWC issues in dev mode
echo "[*] Building Next.js for production (Highly Reproducible mode)..."
npm run build

echo ""
echo "[*] Launching Servers..."

# ─── 4. Run Servers ──────────────────────────────────────────
export PYTHONPATH="${DIR}/backend:${DIR}"

cd "${DIR}/backend"
source venv/bin/activate
# Fast startup, no reload in production
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

cd "${DIR}/frontend"
# Start the production server with proper parameter forwarding
npm run start -- -H 0.0.0.0 -p 3000 &
FRONTEND_PID=$!

echo "[*] Waiting for servers to initialize..."
sleep 8

if command -v xdg-open > /dev/null; then
    xdg-open http://localhost:3000 || true
elif command -v open > /dev/null; then
    open http://localhost:3000 || true
fi

echo "==================================================="
echo "  All systems running natively! Press CTRL+C to stop."
echo "  Backend:  http://localhost:8000"
echo "  Frontend: http://localhost:3000"
echo "==================================================="

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" EXIT INT TERM
wait
