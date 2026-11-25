"""Apply numbered migrations using an operator-provided database URL."""
import os
from pathlib import Path

FILES = [
    "migrations/001_init.sql",
    "migrations/002_phase2.sql",
    "migrations/003_phase3.sql",
    "migrations/004_phase4.sql",
    "migrations/005_phase5.sql",
    "migrations/006_phase6.sql",
    "migrations/007_object_key_rename.sql",
]

def main():
    import psycopg
    conn = psycopg.connect(os.environ["DATABASE_URL"])
    conn.autocommit = True
    cur = conn.cursor()
    for path in FILES:
        sql = Path(path).read_text(encoding="utf-8")
        print(f"--> {path} ({len(sql)} bytes)")
        cur.execute(sql)
        print(f"    ok")
    cur.close()
    conn.close()
    print("ALL MIGRATIONS APPLIED")


if __name__ == "__main__":
    main()
