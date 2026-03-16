"""
Export every database table to a CSV file in ./csv_export/
Usage: python export_csv.py
"""

import os
import csv
import psycopg2
import psycopg2.extras
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

TABLES = [
    "customers",
    "subscriptions",
    "orders",
    "order_items",
    "transactions",
    "chat_interactions",
    "feedback",
]

OUT_DIR = Path("csv_export")
OUT_DIR.mkdir(exist_ok=True)

conn = psycopg2.connect(
    host=os.getenv("DB_HOST", "localhost"),
    port=os.getenv("DB_PORT", "5432"),
    dbname=os.getenv("DB_NAME", "customer_support"),
    user=os.getenv("DB_USER", "postgres"),
    password=os.getenv("DB_PASSWORD", "postgres"),
)

with conn:
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    for table in TABLES:
        cur.execute(f"SELECT * FROM {table} ORDER BY created_at")
        rows = cur.fetchall()
        out_path = OUT_DIR / f"{table}.csv"
        if not rows:
            print(f"  {table}: empty — skipped")
            continue
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        print(f"  {table}: {len(rows)} rows -> {out_path}")

conn.close()
print("Done.")
