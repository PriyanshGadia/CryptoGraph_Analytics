$env:PYTHONPATH = "G:\Programming\CryptoGraph_Analytics\backend;G:\Programming\CryptoGraph_Analytics"
$env:API_KEY = "dev_default_secure_key_1234567890"
$env:DATABASE_PATH = "G:\Programming\CryptoGraph_Analytics\cryptograph.db"
$env:LOW_MEM = "true"
$env:PYTHONUNBUFFERED = "1"
& "G:\Programming\CryptoGraph_Analytics\backend\venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-use-colors
