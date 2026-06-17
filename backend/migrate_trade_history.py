"""One-time migration to add missing columns to trade_history."""
from app.db.database import engine
from sqlalchemy import text, inspect

inspector = inspect(engine)
existing = [c['name'] for c in inspector.get_columns('trade_history')]
print(f"Current columns: {existing}")

conn = engine.connect()

if 'status' not in existing:
    conn.execute(text("ALTER TABLE trade_history ADD COLUMN status TEXT DEFAULT 'EXECUTED'"))
    print("Added: status")

if 'overseer_grade' not in existing:
    conn.execute(text("ALTER TABLE trade_history ADD COLUMN overseer_grade INTEGER"))
    print("Added: overseer_grade")

if 'overseer_notes' not in existing:
    conn.execute(text("ALTER TABLE trade_history ADD COLUMN overseer_notes TEXT"))
    print("Added: overseer_notes")

conn.commit()
conn.close()

# Verify
inspector2 = inspect(engine)
final = [c['name'] for c in inspector2.get_columns('trade_history')]
print(f"Final columns: {final}")
