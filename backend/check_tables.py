import sqlite3

def check_tables():
    conn = sqlite3.connect('cryptograph.db')
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print("Tables in cryptograph.db:", tables)
    conn.close()

if __name__ == "__main__":
    check_tables()
