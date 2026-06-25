import sqlite3
import os
import shutil

if not os.path.exists("test_db"):
    os.makedirs("test_db")
shutil.copy("backend/cryptograph.db-wal", "test_db/")
shutil.copy("backend/cryptograph.db-shm", "test_db/")

conn = sqlite3.connect("test_db/cryptograph.db")
print("Tables:", conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall())
conn.close()
