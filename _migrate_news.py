import sys, os
sys.path.insert(0, '/opt/uzbekworldclub-bot')
from dotenv import load_dotenv
load_dotenv(override=True, dotenv_path='/opt/uzbekworldclub-bot/.env')
import db

pool = db._get_pool()
if pool is None:
    print("ERROR: no DB pool")
    sys.exit(1)

with pool.connection() as conn, conn.cursor() as cur:
    cur.execute("""
        CREATE TABLE IF NOT EXISTS posted_news (
            url       TEXT PRIMARY KEY,
            title     TEXT,
            posted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    conn.commit()
    cur.execute("SELECT COUNT(*) as n FROM posted_news")
    row = cur.fetchone()
    print("posted_news table ready, rows:", row)
