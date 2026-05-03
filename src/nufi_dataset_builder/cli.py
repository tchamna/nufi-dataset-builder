"""Command-line interface for nufi-dataset-builder."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from nufi_dataset_builder.local_dictionary_db import build_local_dictionary_db
from nufi_dataset_builder.nufi_dictionary_builder import build_dictionary_csv_artifacts
from nufi_dataset_builder.rebuild import (
    DEFAULT_CSV_DIR,
    DEFAULT_DB_PATH,
    DEFAULT_SHEET,
    run_rebuild,
    safe_console_text,
)


def _cmd_rebuild(args: argparse.Namespace) -> int:
    try:
        wb, csv_dir, db_path = run_rebuild(
            xlsx_path=args.xlsx_path,
            sheet=args.sheet,
            csv_dir=args.csv_dir,
            db_path=args.db_path,
            app_port=args.app_port,
            allow_running_app=args.allow_running_app,
        )
        print(safe_console_text(f"Rebuilt local dictionary from {wb}"))
        print(safe_console_text(f"CSV artifacts: {csv_dir}"))
        print(safe_console_text(f"SQLite DB: {db_path}"))
        return 0
    except (FileNotFoundError, RuntimeError) as e:
        print(safe_console_text(str(e)), file=sys.stderr)
        return 1


def _cmd_from_csv(args: argparse.Namespace) -> int:
    result = build_local_dictionary_db(Path(args.csv_dir).resolve(), Path(args.db_path).resolve())
    print(f"Built local dictionary DB at {result['db_path']}")
    print(f"orthography_category rows updated: {result['orthography_updated']}")
    for table_name, count in result["row_counts"].items():
        print(f"{table_name}: {count}")
    return 0


def _cmd_import_xlsx(args: argparse.Namespace) -> int:
    summary = build_dictionary_csv_artifacts(
        Path(args.xlsx).expanduser().resolve(),
        Path(args.out_dir).resolve(),
        sheet_name=args.sheet,
        source_name=args.source_name,
        generated_by="nufi-dataset-builder import-xlsx",
    )
    sys.stdout.buffer.write((json.dumps(summary, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="nufi-dataset",
        description="Nufi dictionary: Excel → normalized CSV → SQLite",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_rebuild = sub.add_parser("rebuild", help="Workbook → CSV → SQLite (full pipeline)")
    p_rebuild.add_argument("--xlsx-path", default=None, help="Path to dictionary workbook (.xlsx)")
    p_rebuild.add_argument("--sheet", default=DEFAULT_SHEET, help="Worksheet name")
    p_rebuild.add_argument("--csv-dir", default=DEFAULT_CSV_DIR, help="Output directory for CSV bundle")
    p_rebuild.add_argument("--db-path", default=DEFAULT_DB_PATH, help="Output SQLite database path")
    p_rebuild.add_argument("--app-port", type=int, default=None, help="Only check this port for a running app")
    p_rebuild.add_argument(
        "--allow-running-app",
        action="store_true",
        help="Skip check for Next.js (or other app) on ports 3000/3001",
    )
    p_rebuild.set_defaults(func=_cmd_rebuild)

    p_csv = sub.add_parser("from-csv", help="CSV bundle → SQLite only")
    p_csv.add_argument("--csv-dir", default=DEFAULT_CSV_DIR, help="Directory containing normalized CSV artifacts")
    p_csv.add_argument("--db-path", default=DEFAULT_DB_PATH, help="Output SQLite database path")
    p_csv.set_defaults(func=_cmd_from_csv)

    p_xlsx = sub.add_parser("import-xlsx", help="Workbook → CSV only")
    p_xlsx.add_argument("--xlsx", required=True, help="Path to the source workbook")
    p_xlsx.add_argument("--sheet", default=DEFAULT_SHEET, help="Worksheet name")
    p_xlsx.add_argument("--out-dir", default=DEFAULT_CSV_DIR, help="Directory for CSV artifacts")
    p_xlsx.add_argument(
        "--source-name",
        default="Dictionnaire_Nufi_Francais_Nufi_updated_2026.xlsx",
        help="Logical source name stored in the import run summary",
    )
    p_xlsx.set_defaults(func=_cmd_import_xlsx)

    args = parser.parse_args()
    code = args.func(args)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
