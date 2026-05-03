#!/usr/bin/env python3
"""Reusable SQLite builder for normalized local dictionary CSV artifacts."""

from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path

from nufi_dataset_builder.nufi_bana_classification import collect_bana_keys, first_matching_bana_key


TABLE_SPECS = {
    "dictionary_import_runs": (
        "dictionary_import_runs.csv",
        """
        CREATE TABLE dictionary_import_runs (
            id INTEGER PRIMARY KEY,
            source_name TEXT NOT NULL,
            source_path TEXT,
            source_sheet TEXT NOT NULL,
            notes TEXT,
            row_count INTEGER NOT NULL
        )
        """,
        ["id", "source_name", "source_path", "source_sheet", "notes", "row_count"],
    ),
    "dictionary_raw_rows": (
        "dictionary_raw_rows.csv",
        """
        CREATE TABLE dictionary_raw_rows (
            id INTEGER PRIMARY KEY,
            import_run_id INTEGER NOT NULL,
            source_row_number INTEGER NOT NULL,
            legacy_id INTEGER,
            keyword TEXT NOT NULL,
            keyword_search TEXT NOT NULL,
            from_to TEXT,
            word_type TEXT,
            meta_data TEXT,
            meaning_raw TEXT NOT NULL,
            audio_file TEXT,
            legacy_column1 TEXT,
            legacy_column3 TEXT,
            legacy_column5 TEXT,
            legacy_column7 TEXT,
            legacy_column9 TEXT
        )
        """,
        [
            "id",
            "import_run_id",
            "source_row_number",
            "legacy_id",
            "keyword",
            "keyword_search",
            "from_to",
            "word_type",
            "meta_data",
            "meaning_raw",
            "audio_file",
            "legacy_column1",
            "legacy_column3",
            "legacy_column5",
            "legacy_column7",
            "legacy_column9",
        ],
    ),
    "dictionary_entries": (
        "dictionary_entries.csv",
        """
        CREATE TABLE dictionary_entries (
            id INTEGER PRIMARY KEY,
            raw_row_id INTEGER,
            canonical_lemma TEXT NOT NULL,
            canonical_lemma_search TEXT NOT NULL,
            display_lemma TEXT NOT NULL,
            entry_kind TEXT NOT NULL,
            from_to TEXT,
            word_type TEXT,
            part_of_speech TEXT,
            metadata TEXT,
            audio_file TEXT,
            orthography_category TEXT
        )
        """,
        [
            "id",
            "raw_row_id",
            "canonical_lemma",
            "canonical_lemma_search",
            "display_lemma",
            "entry_kind",
            "from_to",
            "word_type",
            "part_of_speech",
            "metadata",
            "audio_file",
        ],
    ),
    "dictionary_entry_variants": (
        "dictionary_entry_variants.csv",
        """
        CREATE TABLE dictionary_entry_variants (
            id INTEGER PRIMARY KEY,
            entry_id INTEGER NOT NULL,
            variant_text TEXT NOT NULL,
            variant_search TEXT NOT NULL,
            variant_type TEXT NOT NULL
        )
        """,
        ["id", "entry_id", "variant_text", "variant_search", "variant_type"],
    ),
    "dictionary_senses": (
        "dictionary_senses.csv",
        """
        CREATE TABLE dictionary_senses (
            id INTEGER PRIMARY KEY,
            entry_id INTEGER NOT NULL,
            sense_order INTEGER NOT NULL,
            definition_text TEXT NOT NULL,
            raw_segment TEXT,
            notes TEXT
        )
        """,
        ["id", "entry_id", "sense_order", "definition_text", "raw_segment", "notes"],
    ),
    "dictionary_examples": (
        "dictionary_examples.csv",
        """
        CREATE TABLE dictionary_examples (
            id INTEGER PRIMARY KEY,
            sense_id INTEGER NOT NULL,
            example_order INTEGER NOT NULL,
            nufi_text TEXT NOT NULL,
            french_text TEXT,
            raw_example TEXT
        )
        """,
        ["id", "sense_id", "example_order", "nufi_text", "french_text", "raw_example"],
    ),
    "dictionary_entry_links": (
        "dictionary_entry_links.csv",
        """
        CREATE TABLE dictionary_entry_links (
            id INTEGER PRIMARY KEY,
            from_entry_id INTEGER NOT NULL,
            to_entry_id INTEGER,
            relation_type TEXT NOT NULL,
            target_lemma TEXT,
            target_lemma_search TEXT,
            source_text TEXT
        )
        """,
        [
            "id",
            "from_entry_id",
            "to_entry_id",
            "relation_type",
            "target_lemma",
            "target_lemma_search",
            "source_text",
        ],
    ),
}

FTS_TABLE_SQL = """
CREATE VIRTUAL TABLE dictionary_search_fts USING fts5(
    entry_id UNINDEXED,
    variant_search,
    canonical_search,
    definition_text
)
"""

FTS_POPULATE_SQL = """
INSERT INTO dictionary_search_fts (entry_id, variant_search, canonical_search, definition_text)
SELECT
    e.id,
    COALESCE((
      SELECT group_concat(v.variant_search, ' ')
      FROM dictionary_entry_variants v
      WHERE v.entry_id = e.id
    ), ''),
    e.canonical_lemma_search,
    COALESCE((
      SELECT group_concat(s.definition_text, ' ')
      FROM dictionary_senses s
      WHERE s.entry_id = e.id
    ), '')
FROM dictionary_entries e
"""


def populate_orthography_categories(cursor: sqlite3.Cursor) -> int:
    """Set orthography_category ('bana' | 'non_bana') from headword or display_lemma."""
    keys = collect_bana_keys()
    cursor.execute(
        """
        SELECT e.id,
               COALESCE(
                 (SELECT v.variant_text FROM dictionary_entry_variants v
                  WHERE v.entry_id = e.id AND v.variant_type = 'headword' LIMIT 1),
                 e.display_lemma
               ) AS lemma
        FROM dictionary_entries e
        """
    )
    rows = cursor.fetchall()
    updated = 0
    for entry_id, lemma in rows:
        cat = "bana" if first_matching_bana_key(str(lemma), keys) is not None else "non_bana"
        cursor.execute(
            "UPDATE dictionary_entries SET orthography_category = ? WHERE id = ?",
            (cat, entry_id),
        )
        updated += 1
    return updated


INDEX_STATEMENTS = [
    "CREATE INDEX idx_entries_canonical_search ON dictionary_entries(canonical_lemma_search)",
    "CREATE INDEX idx_entries_canonical_lemma ON dictionary_entries(canonical_lemma)",
    "CREATE INDEX idx_entries_canonical_lemma_nocase ON dictionary_entries(canonical_lemma COLLATE NOCASE)",
    "CREATE INDEX idx_variants_search ON dictionary_entry_variants(variant_search)",
    "CREATE INDEX idx_variants_text ON dictionary_entry_variants(variant_text)",
    "CREATE INDEX idx_variants_text_nocase ON dictionary_entry_variants(variant_text COLLATE NOCASE)",
    "CREATE INDEX idx_senses_entry_order ON dictionary_senses(entry_id, sense_order)",
    "CREATE INDEX idx_senses_definition_text ON dictionary_senses(definition_text)",
    "CREATE INDEX idx_examples_sense_order ON dictionary_examples(sense_id, example_order)",
    "CREATE INDEX idx_links_from_relation ON dictionary_entry_links(from_entry_id, relation_type)",
    "CREATE INDEX idx_links_target_search ON dictionary_entry_links(target_lemma_search)",
]


def load_csv(cursor: sqlite3.Cursor, csv_path: Path, table_name: str, field_order: list[str]) -> int:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        placeholders = ", ".join(["?"] * len(field_order))
        sql = f"INSERT INTO {table_name} ({', '.join(field_order)}) VALUES ({placeholders})"
        rows = []
        for row in reader:
            rows.append([row.get(field, "") for field in field_order])
        cursor.executemany(sql, rows)
        return len(rows)


def build_local_dictionary_db(csv_dir: Path, db_path: Path) -> dict[str, object]:
    csv_dir = csv_dir.resolve()
    db_path = db_path.resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(db_path)
    try:
        cursor = connection.cursor()
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA synchronous = NORMAL")

        for table_name in TABLE_SPECS:
            cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
        cursor.execute("DROP TABLE IF EXISTS dictionary_search_fts")

        row_counts: dict[str, int] = {}
        for table_name, (csv_name, ddl, field_order) in TABLE_SPECS.items():
            cursor.execute(ddl)
            row_counts[table_name] = load_csv(cursor, csv_dir / csv_name, table_name, field_order)

        for index_sql in INDEX_STATEMENTS:
            cursor.execute(index_sql)

        cursor.execute(FTS_TABLE_SQL)
        cursor.execute(FTS_POPULATE_SQL)

        orthography_updated = populate_orthography_categories(cursor)

        connection.commit()

        # Switch back to DELETE journal mode so the deployed file never looks for
        # a WAL file on the server. WAL was only used for build-time performance.
        cursor.execute("PRAGMA journal_mode = DELETE")
        connection.commit()
    finally:
        connection.close()

    return {
        "db_path": str(db_path),
        "orthography_updated": orthography_updated,
        "row_counts": row_counts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build local SQLite dictionary DB")
    parser.add_argument(
        "--csv-dir",
        default="reports/nufi-normalized-import",
        help="Directory containing normalized CSV artifacts",
    )
    parser.add_argument(
        "--db-path",
        default="data/local-dictionary.sqlite",
        help="Output SQLite database path",
    )
    args = parser.parse_args()

    result = build_local_dictionary_db(Path(args.csv_dir), Path(args.db_path))

    print(f"Built local dictionary DB at {result['db_path']}")
    print(f"orthography_category rows updated: {result['orthography_updated']}")
    for table_name, count in result["row_counts"].items():
        print(f"{table_name}: {count}")


if __name__ == "__main__":
    main()