import time
import os
import sys

# Add project root and backend to path
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from app.db.database import SessionLocal
from app.api.routes.correlations import precompute_correlations_sync

print("Connecting to DB...")
db = SessionLocal()

print("Running precompute_correlations_sync...")
start = time.time()
matrix_data, sector_data = precompute_correlations_sync(db)
end = time.time()

print(f"Finished in {end - start:.2f} seconds.")
if matrix_data:
    print(f"Matrix symbols count: {len(matrix_data.get('symbols', []))}")
else:
    print("Matrix data is None")

db.close()
