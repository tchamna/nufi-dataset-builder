#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Classify lexical Nufi headwords as Bana vs non-Bana using the same Bana dictionary
keys as `src/lib/nufiBanaForbiddenSubstrings.ts` / `nufi_bana_standard_maps.py`
(excludes `dict_ton_bas`).

Writes:
  - reports/bana_headword_audit.csv   — all rows with category + optional match key
  - reports/bana_headwords.csv        — Bana only
  - reports/non_bana_headwords.csv    — non-Bana only

Usage:
  python dictionary-builder/dump_bana_headword_audit.py
  python dictionary-builder/dump_bana_headword_audit.py --db path/to/local-dictionary.sqlite
"""

from __future__ import annotations

import argparse
import csv
import os
import sqlite3
from pathlib import Path

from nufi_dataset_builder.nufi_bana_classification import collect_bana_keys, first_matching_bana_key


def fetch_lexical_headwords(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    cur = conn.execute(
        """
        SELECT e.id, hw.variant_text AS word
        FROM dictionary_entries e
        INNER JOIN dictionary_entry_variants hw
          ON hw.entry_id = e.id AND hw.variant_type = 'headword'
        WHERE e.entry_kind = 'lexical'
          AND NOT EXISTS (
            SELECT 1 FROM dictionary_entry_links l
            WHERE l.from_entry_id = e.id AND l.relation_type = 'alias_of'
          )
        ORDER BY e.canonical_lemma_search
        """
    )
    return [(str(r[0]), str(r[1])) for r in cur.fetchall()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Dump Bana vs non-Bana headword CSV audit.")
    parser.add_argument(
        "--db",
        default=os.path.join(os.getcwd(), "data", "local-dictionary.sqlite"),
        help="Path to local dictionary SQLite",
    )
    parser.add_argument(
        "--out-dir",
        default=os.path.join(os.getcwd(), "reports"),
        help="Output directory for CSV files",
    )
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if not db_path.is_file():
        raise SystemExit(f"Database not found: {db_path}")

    keys = collect_bana_keys()
    rows_out: list[dict[str, str]] = []

    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
        headwords = fetch_lexical_headwords(conn)

    for entry_id, word in headwords:
        match = first_matching_bana_key(word, keys)
        if match is None:
            category = "non_bana"
            match_key = ""
        else:
            category = "bana"
            match_key = match
        rows_out.append(
            {
                "entry_id": entry_id,
                "headword": word,
                "category": category,
                "matching_bana_key": match_key,
            }
        )

    combined = out_dir / "bana_headword_audit.csv"
    bana_only = out_dir / "bana_headwords.csv"
    non_only = out_dir / "non_bana_headwords.csv"

    fieldnames = ["entry_id", "headword", "category", "matching_bana_key"]

    for path in (combined,):
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(rows_out)

    with bana_only.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows_out:
            if r["category"] == "bana":
                w.writerow(r)

    with non_only.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows_out:
            if r["category"] == "non_bana":
                w.writerow(r)

    bana_count = sum(1 for r in rows_out if r["category"] == "bana")
    print(f"Wrote {combined} ({len(rows_out)} rows, {bana_count} bana, {len(rows_out) - bana_count} non_bana)")
    print(f"Wrote {bana_only}")
    print(f"Wrote {non_only}")


if __name__ == "__main__":
    main()
