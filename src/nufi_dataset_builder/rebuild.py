"""Orchestrate workbook → CSV → SQLite (standalone; paths default to cwd)."""

from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

from nufi_dataset_builder.local_dictionary_db import build_local_dictionary_db
from nufi_dataset_builder.nufi_dictionary_builder import build_dictionary_csv_artifacts

WORKBOOK_BASENAME = "Dictionnaire_Nufi_Francais_Nufi_updated_2026.xlsx"
WORKBOOK_PATTERN = f"*/Livres Nufi/*/{WORKBOOK_BASENAME}"
DEFAULT_SHEET = "MainDictionary"
DEFAULT_CSV_DIR = "reports/nufi-normalized-import"
DEFAULT_DB_PATH = "data/local-dictionary.sqlite"
DEFAULT_APP_PORTS = (3000, 3001)

_SKIP_DIR_PARTS = frozenset(
    {"node_modules", ".git", "__pycache__", ".venv", "venv", ".tox", "dist", "build", "site-packages"}
)


def _workspace_root() -> Path:
    """Project root for resolving relative output paths and workbook search."""
    return Path.cwd().resolve()


def resolve_workbook_path(explicit_path: str | None) -> Path:
    if explicit_path:
        path = Path(explicit_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Dictionary workbook not found: {path}")
        return path

    env_path = (os.getenv("NUFI_DICTIONARY_XLSX") or "").strip()
    if env_path:
        path = Path(env_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"NUFI_DICTIONARY_XLSX not found: {path}")
        return path

    root = _workspace_root()
    data_candidate = root / "data" / WORKBOOK_BASENAME
    if data_candidate.is_file():
        return data_candidate.resolve()

    for path in sorted(root.rglob(WORKBOOK_BASENAME)):
        if any(p in _SKIP_DIR_PARTS for p in path.parts):
            continue
        return path.resolve()

    gdrive = Path("G:/My Drive")
    if gdrive.is_dir():
        matches = sorted(gdrive.glob(WORKBOOK_PATTERN))
        if matches:
            return matches[0].resolve()

    raise FileNotFoundError(
        f"Dictionary workbook ({WORKBOOK_BASENAME}) not found. "
        "Set NUFI_DICTIONARY_XLSX, place the file under ./data/, or pass --xlsx-path."
    )


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def any_local_app_port_in_use(ports: tuple[int, ...]) -> int | None:
    for port in ports:
        if is_port_in_use(port):
            return port
    return None


def safe_console_text(value: object) -> str:
    text = str(value)
    encoding = sys.stdout.encoding or "utf-8"
    return text.encode(encoding, errors="replace").decode(encoding)


def run_rebuild(
    *,
    xlsx_path: str | None,
    sheet: str,
    csv_dir: str,
    db_path: str,
    app_port: int | None,
    allow_running_app: bool,
) -> tuple[Path, Path, Path]:
    """Run full pipeline. Returns (workbook_path, csv_dir, db_path) as resolved Paths."""
    workbook_path = resolve_workbook_path(xlsx_path)
    csv_path = Path(csv_dir).resolve()
    db_file = Path(db_path).resolve()

    ports_to_check = (app_port,) if app_port is not None else DEFAULT_APP_PORTS
    busy_port = None if allow_running_app else any_local_app_port_in_use(ports_to_check)
    if busy_port is not None:
        raise RuntimeError(
            f"Local app detected on port {busy_port}. Stop the app before rebuilding the dictionary "
            "(SQLite may be locked), or use allow_running_app=True."
        )

    build_dictionary_csv_artifacts(
        workbook_path,
        csv_path,
        sheet_name=sheet,
        generated_by="nufi-dataset-builder rebuild",
    )
    build_local_dictionary_db(csv_path, db_file)
    return workbook_path, csv_path, db_file
