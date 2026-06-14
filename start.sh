#!/bin/bash

# CryptoGraph Analytics Launcher for macOS / Linux

echo "==================================================="
echo "    Starting CryptoGraph Analytics Environment"
echo "==================================================="
echo ""

# Get the absolute path of the script directory
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Start Backend in a new terminal session or background
echo "[*] Initializing Backend Server (FastAPI)..."
export PYTHONPATH="${DIR}/backend:${DIR}"
cd "${DIR}/backend" || exit

# Attempt to use gnome-terminal or xterm on Linux, open on macOS, or run in background
if command -v open > /dev/null; then
    # macOS
    osascript -e "tell app \"Terminal\" to do script \"cd '${DIR}/backend' && export PYTHONPATH='${DIR}/backend:${DIR}' && python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload\""
elif command -v gnome-terminal > /dev/null; then
    # Linux (GNOME)
    gnome-terminal -- bash -c "export PYTHONPATH='${DIR}/backend:${DIR}'; python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload; exec bash"
elif command -v xterm > /dev/null; then
    # Linux (Xterm)
    xterm -e "export PYTHONPATH='${DIR}/backend:${DIR}'; python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
else
    # Fallback to background process
    python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
fi

# Start Frontend
echo "[*] Initializing Frontend Server (Next.js)..."
cd "${DIR}/frontend" || exit

if command -v open > /dev/null; then
    # macOS
    osascript -e "tell app \"Terminal\" to do script \"cd '${DIR}/frontend' && npm run dev\""
elif command -v gnome-terminal > /dev/null; then
    gnome-terminal -- bash -c "npm run dev; exec bash"
elif command -v xterm > /dev/null; then
    xterm -e "npm run dev"
else
    npm run dev &
fi

echo "[*] Waiting for servers to initialize..."
sleep 5

echo "[*] Launching Browser..."
if command -v xdg-open > /dev/null; then
    xdg-open http://localhost:3000
elif command -v open > /dev/null; then
    open http://localhost:3000
else
    echo "Please open http://localhost:3000 in your browser."
fi

echo ""
echo "==================================================="
echo "   All systems running!"
echo "==================================================="
