#!/usr/bin/env python3
"""
Add dictionary_entries.orthography_category and populate it for an existing DB.

Safe to run once; skips if the column already exists.

Usage:
  python dictionary-builder/migrate_add_orthography_category.py
  python dictionary-builder/migrate_add_orthography_category.py --db path/to/local-dictionary.sqlite
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from nufi_dataset_builder.local_dictionary_db import populate_orthography_categories


def column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def main() -> None:
    parser = argparse.ArgumentParser(description="Add orthography_category column to dictionary DB")
    parser.add_argument(
        "--db",
        default="data/local-dictionary.sqlite",
        help="Path to SQLite dictionary database",
    )
    args = parser.parse_args()
    db_path = Path(args.db).resolve()
    if not db_path.is_file():
        raise SystemExit(f"Database not found: {db_path}")

    with sqlite3.connect(db_path) as conn:
        if column_exists(conn, "dictionary_entries", "orthography_category"):
            print("Column orthography_category already exists; repopulating values.")
        else:
            conn.execute("ALTER TABLE dictionary_entries ADD COLUMN orthography_category TEXT")
            print("Added column orthography_category.")

        cur = conn.cursor()
        n = populate_orthography_categories(cur)
        conn.commit()
        print(f"Updated orthography_category for {n} entries.")


if __name__ == "__main__":
    main()
