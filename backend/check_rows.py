import sqlite3

def check_rows():
    conn = sqlite3.connect('cryptograph.db')
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    for t in tables:
        name = t[0]
        try:
            count = cursor.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
            print(f"Table {name}: {count} rows")
        except Exception as e:
            print(f"Table {name}: Error {e}")
    conn.close()

if __name__ == "__main__":
    check_rows()
