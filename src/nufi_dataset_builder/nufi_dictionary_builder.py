#!/usr/bin/env python3
"""Reusable builder for normalized dictionary artifacts from the source XLSX workbook."""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import openpyxl


SHEET_NAME_DEFAULT = "MainDictionary"

BREAK_TAG_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
SENSE_SPLIT_RE = re.compile(
    r"(?:^|(?:<tag_(?:bullet|def)>\s*)?(?:<br\s*/?>\s*)*)(?P<order>\d+)[–-]\s*(?P<body>.*?)(?=(?:(?:<tag_(?:bullet|def)>\s*)?(?:<br\s*/?>\s*)*\d+[–-])|$)",
    re.DOTALL,
)
EXAMPLE_RE = re.compile(
    r"\bex\.\s*(?P<nufi>.*?)\s*:\s*(?P<french>.*?)(?=(?:\s*\bex\.)|(?:(?:\s*<tag_(?:bullet|def)>)?(?:\s*<br\s*/?>\s*)*\d+[–-])|(?:\n\s*\d+[–-])|$)",
    re.DOTALL | re.IGNORECASE,
)
REFERENCE_RE = re.compile(r"\b(?P<kind>cf|syn|anto)\.\s*(?P<target>[^;.,]+)", re.IGNORECASE)
LONG_FRENCH_EXAMPLE_TRIM_THRESHOLD = 100
LONG_FRENCH_EXAMPLE_MAX_LENGTH = 200
LONG_FRENCH_EXAMPLE_DISCARD_THRESHOLD = 1000
INLINE_EXAMPLE_MARKER_PATTERNS = (
    r"\s*;\s*syn\.\s*",
    r"\s*;\s*cf\.\s*",
    r"\s*;\s*anto\.\s*",
    r"\s*;\s*litt\.\s*,?\s*",
    r"\s*N\.B\.\s*",
    r"\s*quasi-hom\.\s*",
)
SPILL_MARKER_PATTERNS = (
    r"\s+ODL:\s*",
    r"\n\s*(?:consultez|voir|cf\.|n\.b\.|moralit[ée]|proverbe|contexte culturel|source|lien)\b",
    r"\n\s*\d+[.)-]\s",
)
SECOND_LINE_SPILL_RE = re.compile(
    r"^(?:liste|tableau|titre|source|lien|moralit[ée]|par|recueilli)\b",
    re.IGNORECASE,
)


@dataclass
class RawRow:
    source_row_number: int
    legacy_id: int | None
    keyword: str
    keyword_search: str
    from_to: str | None
    word_type: str | None
    meta_data: str | None
    meaning_raw: str
    audio_file: str | None
    legacy_column1: str | None
    legacy_column3: str | None
    legacy_column5: str | None
    legacy_column7: str | None
    legacy_column9: str | None


FIELD_HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "keyword": ("Keyword",),
    "from_to": ("From_to", "From To"),
    "word_type": ("Word_Type", "Word Type"),
    "meaning_raw": ("Meaning",),
    "meta_data": ("Meta_data", "Metadata", "Pronunciation"),
    "audio_file": ("Audio_files", "Audio_file"),
    "legacy_id": ("ID",),
}


def normalize_text(value: object) -> str:
    if value is None:
        return ""
    return unicodedata.normalize("NFC", str(value)).strip()


def normalize_header_name(value: object) -> str:
    text = normalize_text(value).lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def resolve_header_indexes(header_row: tuple[object, ...]) -> dict[str, int | None]:
    header_lookup: dict[str, int] = {}
    for index, cell in enumerate(header_row):
        normalized = normalize_header_name(cell)
        if normalized and normalized not in header_lookup:
            header_lookup[normalized] = index

    indexes: dict[str, int | None] = {}
    for field, aliases in FIELD_HEADER_ALIASES.items():
        indexes[field] = next(
            (
                header_lookup.get(normalize_header_name(alias))
                for alias in aliases
                if normalize_header_name(alias) in header_lookup
            ),
            None,
        )

    missing_required = [
        field for field in ("keyword", "meaning_raw") if indexes[field] is None
    ]
    if missing_required:
        raise ValueError(
            "Workbook sheet is missing required columns: "
            + ", ".join(missing_required)
            + f". Header row: {[normalize_text(cell) for cell in header_row]}"
        )

    return indexes


def row_value(row: tuple[object, ...], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return normalize_text(row[index])


def search_key(text: str) -> str:
    normalized = unicodedata.normalize("NFD", normalize_text(text).replace("’", "'"))
    stripped = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    stripped = stripped.lower()
    stripped = re.sub(r"\s+", " ", stripped)
    stripped = re.sub(r"^[^\wɑɔəɛʉŋ']+|[^\wɑɔəɛʉŋ']+$", "", stripped, flags=re.IGNORECASE)
    stripped = stripped.lstrip("'")
    return unicodedata.normalize("NFC", stripped)


def clean_markup(text: str) -> str:
    text = BREAK_TAG_RE.sub("\n", text)
    text = text.replace("<tag_bullet>", " ")
    text = TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*", "\n", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def split_senses(meaning_raw: str) -> list[tuple[int, str]]:
    matches = list(SENSE_SPLIT_RE.finditer(meaning_raw))
    if not matches:
        return [(1, meaning_raw)]

    senses: list[tuple[int, str]] = []
    for match in matches:
        order = int(match.group("order"))
        body = match.group("body").strip()
        if body:
            senses.append((order, body))
    return senses or [(1, meaning_raw)]


def strip_examples(segment_text: str) -> str:
    stripped = EXAMPLE_RE.sub("", segment_text)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    return stripped


def trim_example_nufi_text(text: str) -> str:
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if not lines:
        return ""
    return lines[0]


def trim_example_french_text(text: str) -> str:
    text = text.strip()

    question_syn_match = re.search(r"\?\s*syn\.\s*", text, re.IGNORECASE)
    if question_syn_match:
        text = text[: question_syn_match.start() + 1].rstrip()

    for pattern in INLINE_EXAMPLE_MARKER_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            text = text[: match.start()].rstrip()
            break

    for pattern in SPILL_MARKER_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            text = text[: match.start()].rstrip()
            break

    text = re.sub(r"\s+([;.!?])", r"\1", text)

    if len(text) > LONG_FRENCH_EXAMPLE_TRIM_THRESHOLD:
        punctuation_match = re.search(r"^(.+?[;.!?])(?:\s|$)", text)
        if punctuation_match:
            text = punctuation_match.group(1)

    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if len(lines) <= 1:
        return text

    first_line = lines[0]
    second_line = lines[1]
    if re.search(r"[.!?;:]$", first_line) and (
        re.match(r"^\d+[.)-]\s", second_line)
        or re.match(r"^[^:\n]{1,80}\s*:\s*(?:\S.*)?$", second_line)
        or SECOND_LINE_SPILL_RE.match(second_line)
        or (len(second_line.split()) >= 3 and second_line[:1].isupper())
    ):
        return first_line

    return text


def looks_like_french_start(text: str) -> bool:
    normalized = text.strip().lower()
    if not normalized:
        return False
    return bool(
        re.match(
            r"^(?:l'|d'|c'|j'|qu'|le\b|la\b|les\b|un\b|une\b|des\b|du\b|de\b|ce\b|cet\b|cette\b|ces\b|il\b|elle\b|on\b|qui\b|que\b|où\b|pour\b|avec\b|sans\b|dans\b|sur\b)",
            normalized,
        )
    )


def rebalance_example_split(nufi_text: str, french_text: str) -> tuple[str, str]:
    separator = " : "
    if separator not in french_text:
        return nufi_text, french_text

    for match in re.finditer(r"\s:\s", french_text):
        prefix = french_text[: match.start()].strip()
        suffix = french_text[match.end() :].strip()
        if not prefix or not suffix:
            continue

        if "\n" in prefix or re.search(r"[.!?;]", prefix):
            continue

        prefix_looks_nufi = bool(re.search(r"[ɑʉəɛɔŋǐěǎǒ]", prefix)) or prefix.count(",") >= 2
        if prefix_looks_nufi and looks_like_french_start(suffix):
            return f"{nufi_text}{separator}{prefix}", suffix

    return nufi_text, french_text


def should_discard_example(nufi_text: str, french_text: str) -> bool:
    nufi_word_count = len([word for word in nufi_text.split() if word.strip()])
    if nufi_word_count > 8 and re.search(r"[.!?]", nufi_text):
        return True
    if nufi_word_count == 1:
        return len(french_text) > LONG_FRENCH_EXAMPLE_DISCARD_THRESHOLD
    return len(french_text) > LONG_FRENCH_EXAMPLE_MAX_LENGTH


def extract_examples(raw_segment: str) -> list[dict[str, str]]:
    normalized_segment = clean_markup(raw_segment)
    examples: list[dict[str, str]] = []
    for order, match in enumerate(EXAMPLE_RE.finditer(normalized_segment), start=1):
        nufi_text = trim_example_nufi_text(normalize_text(match.group("nufi")).rstrip(" ;"))
        french_text = normalize_text(match.group("french")).rstrip(" ;")
        nufi_text, french_text = rebalance_example_split(nufi_text, french_text)
        french_text = trim_example_french_text(french_text).rstrip(" ;")
        if nufi_text and french_text and not should_discard_example(nufi_text, french_text):
            raw_example = f"ex. {nufi_text} : {french_text}"
            examples.append(
                {
                    "example_order": str(order),
                    "nufi_text": nufi_text,
                    "french_text": french_text,
                    "raw_example": raw_example,
                }
            )
    return examples


def extract_references(raw_segment: str) -> list[tuple[str, str]]:
    cleaned = clean_markup(raw_segment)
    references: list[tuple[str, str]] = []
    for match in REFERENCE_RE.finditer(cleaned):
        kind = match.group("kind").lower()
        target = normalize_text(match.group("target")).rstrip(" ;")
        if not target:
            continue
        relation = {
            "cf": "cf",
            "syn": "synonym",
            "anto": "antonym",
        }[kind]
        references.append((relation, target))
    return references


def maybe_alias_target(keyword: str, meaning_raw: str, known_keywords: set[str]) -> str | None:
    if "<tag_bullet>" in meaning_raw or "ex." in meaning_raw.lower():
        return None

    candidate = clean_markup(meaning_raw)
    candidate = re.sub(r"^[.;:,-]+|[.;:,-]+$", "", candidate).strip()
    if not candidate or candidate == keyword:
        return None

    if candidate in known_keywords:
        return candidate

    return None


def load_rows(xlsx_path: Path, sheet_name: str) -> list[RawRow]:
    workbook = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    sheet = workbook[sheet_name]

    rows = sheet.iter_rows(values_only=True)
    header_row = next(rows)
    header_indexes = resolve_header_indexes(header_row)

    loaded_rows: list[RawRow] = []
    for source_row_number, row in enumerate(rows, start=2):
        keyword = row_value(row, header_indexes["keyword"])
        meaning_raw = row_value(row, header_indexes["meaning_raw"])

        if not keyword or not meaning_raw:
            continue

        from_to = row_value(row, header_indexes["from_to"]) or None
        word_type = row_value(row, header_indexes["word_type"]) or None
        meta_data = row_value(row, header_indexes["meta_data"]) or None
        audio_file = row_value(row, header_indexes["audio_file"]) or None
        legacy_id_raw = row_value(row, header_indexes["legacy_id"])

        loaded_rows.append(
            RawRow(
                source_row_number=source_row_number,
                legacy_id=int(legacy_id_raw) if legacy_id_raw else None,
                keyword=keyword,
                keyword_search=search_key(keyword),
                from_to=from_to,
                word_type=word_type,
                meta_data=meta_data,
                meaning_raw=meaning_raw,
                audio_file=audio_file,
                legacy_column1=normalize_text(row[0] if len(row) > 0 else "") or None,
                legacy_column3=normalize_text(row[2] if len(row) > 2 else "") or None,
                legacy_column5=normalize_text(row[4] if len(row) > 4 else "") or None,
                legacy_column7=normalize_text(row[6] if len(row) > 6 else "") or None,
                legacy_column9=normalize_text(row[8] if len(row) > 8 else "") or None,
            )
        )

    return loaded_rows


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def build_dictionary_csv_artifacts(
    xlsx_path: Path,
    out_dir: Path,
    *,
    sheet_name: str = SHEET_NAME_DEFAULT,
    source_name: str = "Dictionnaire_Nufi_Francais_Nufi_updated_2026.xlsx",
    generated_by: str = "nufi-dataset-builder import-xlsx",
) -> dict[str, object]:
    out_dir.mkdir(parents=True, exist_ok=True)

    raw_rows = load_rows(xlsx_path, sheet_name)
    keyword_to_entry_id: dict[str, int] = {}
    known_keywords = {row.keyword for row in raw_rows}

    import_run_id = 1
    import_run = {
        "id": import_run_id,
        "source_name": source_name,
        "source_path": str(xlsx_path),
        "source_sheet": sheet_name,
        "notes": json.dumps(
            {
                "generated_by": generated_by,
                "strategy": "raw_rows + normalized_entries",
            },
            ensure_ascii=False,
        ),
        "row_count": len(raw_rows),
    }

    raw_rows_csv: list[dict[str, object]] = []
    entries_csv: list[dict[str, object]] = []
    variants_csv: list[dict[str, object]] = []
    senses_csv: list[dict[str, object]] = []
    examples_csv: list[dict[str, object]] = []
    links_csv: list[dict[str, object]] = []
    next_variant_id = 1
    next_sense_id = 1
    next_example_id = 1
    next_link_id = 1

    for row in raw_rows:
        raw_row_id = len(raw_rows_csv) + 1
        raw_rows_csv.append(
            {
                "id": raw_row_id,
                "import_run_id": import_run_id,
                "source_row_number": row.source_row_number,
                "legacy_id": row.legacy_id or "",
                "keyword": row.keyword,
                "keyword_search": row.keyword_search,
                "from_to": row.from_to or "",
                "word_type": row.word_type or "",
                "meta_data": row.meta_data or "",
                "meaning_raw": row.meaning_raw,
                "audio_file": row.audio_file or "",
                "legacy_column1": row.legacy_column1 or "",
                "legacy_column3": row.legacy_column3 or "",
                "legacy_column5": row.legacy_column5 or "",
                "legacy_column7": row.legacy_column7 or "",
                "legacy_column9": row.legacy_column9 or "",
            }
        )

        alias_target = maybe_alias_target(row.keyword, row.meaning_raw, known_keywords)
        entry_kind = "reverse_lookup" if alias_target else "lexical"
        entry_id = len(entries_csv) + 1
        keyword_to_entry_id[row.keyword] = entry_id

        entries_csv.append(
            {
                "id": entry_id,
                "raw_row_id": raw_row_id,
                "canonical_lemma": row.keyword,
                "canonical_lemma_search": row.keyword_search,
                "display_lemma": row.keyword,
                "entry_kind": entry_kind,
                "from_to": row.from_to or "",
                "word_type": row.word_type or "",
                "part_of_speech": row.meta_data or "",
                "metadata": row.meta_data or "",
                "audio_file": row.audio_file or "",
            }
        )

        variants_csv.append(
            {
                "id": next_variant_id,
                "entry_id": entry_id,
                "variant_text": row.keyword,
                "variant_search": row.keyword_search,
                "variant_type": "headword",
            }
        )
        next_variant_id += 1

        normalized_variant = search_key(row.keyword)
        if normalized_variant and normalized_variant != row.keyword:
            variants_csv.append(
                {
                    "id": next_variant_id,
                    "entry_id": entry_id,
                    "variant_text": normalized_variant,
                    "variant_search": normalized_variant,
                    "variant_type": "normalized_search",
                }
            )
            next_variant_id += 1

        assigned_sense_orders: set[int] = set()
        next_sense_order = 1

        for parsed_sense_order, raw_segment in split_senses(row.meaning_raw):
            sense_order = parsed_sense_order
            if sense_order in assigned_sense_orders:
                while next_sense_order in assigned_sense_orders:
                    next_sense_order += 1
                sense_order = next_sense_order

            assigned_sense_orders.add(sense_order)
            next_sense_order = max(next_sense_order, sense_order + 1)

            cleaned_segment = clean_markup(raw_segment)
            definition_text = strip_examples(cleaned_segment)
            definition_text = re.sub(r"\s+", " ", definition_text).strip()

            if not definition_text:
                definition_text = cleaned_segment

            sense_id = next_sense_id
            next_sense_id += 1
            senses_csv.append(
                {
                    "id": sense_id,
                    "entry_id": entry_id,
                    "sense_order": sense_order,
                    "definition_text": definition_text,
                    "raw_segment": raw_segment,
                    "notes": "",
                }
            )

            for example in extract_examples(raw_segment):
                examples_csv.append(
                    {
                        "id": next_example_id,
                        "sense_id": sense_id,
                        "example_order": example["example_order"],
                        "nufi_text": example["nufi_text"],
                        "french_text": example["french_text"],
                        "raw_example": example["raw_example"],
                    }
                )
                next_example_id += 1

            for relation_type, target in extract_references(raw_segment):
                links_csv.append(
                    {
                        "id": next_link_id,
                        "from_entry_id": entry_id,
                        "to_entry_id": "",
                        "relation_type": relation_type,
                        "target_lemma": target,
                        "target_lemma_search": search_key(target),
                        "source_text": target,
                    }
                )
                next_link_id += 1

        if alias_target:
            links_csv.append(
                {
                    "id": next_link_id,
                    "from_entry_id": entry_id,
                    "to_entry_id": "",
                    "relation_type": "alias_of",
                    "target_lemma": alias_target,
                    "target_lemma_search": search_key(alias_target),
                    "source_text": alias_target,
                }
            )
            next_link_id += 1

    for link in links_csv:
        target_lemma = str(link["target_lemma"])
        if target_lemma in keyword_to_entry_id:
            link["to_entry_id"] = keyword_to_entry_id[target_lemma]

    write_csv(out_dir / "dictionary_import_runs.csv", list(import_run.keys()), [import_run])
    write_csv(
        out_dir / "dictionary_raw_rows.csv",
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
        raw_rows_csv,
    )
    write_csv(
        out_dir / "dictionary_entries.csv",
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
        entries_csv,
    )
    write_csv(
        out_dir / "dictionary_entry_variants.csv",
        ["id", "entry_id", "variant_text", "variant_search", "variant_type"],
        variants_csv,
    )
    write_csv(
        out_dir / "dictionary_senses.csv",
        ["id", "entry_id", "sense_order", "definition_text", "raw_segment", "notes"],
        senses_csv,
    )
    write_csv(
        out_dir / "dictionary_examples.csv",
        ["id", "sense_id", "example_order", "nufi_text", "french_text", "raw_example"],
        examples_csv,
    )
    write_csv(
        out_dir / "dictionary_entry_links.csv",
        [
            "id",
            "from_entry_id",
            "to_entry_id",
            "relation_type",
            "target_lemma",
            "target_lemma_search",
            "source_text",
        ],
        links_csv,
    )

    summary = {
        "source_workbook": str(xlsx_path),
        "source_sheet": sheet_name,
        "raw_rows": len(raw_rows_csv),
        "entries": len(entries_csv),
        "entry_variants": len(variants_csv),
        "senses": len(senses_csv),
        "examples": len(examples_csv),
        "links": len(links_csv),
        "reverse_lookup_entries": sum(1 for entry in entries_csv if entry["entry_kind"] == "reverse_lookup"),
        "rows_with_audio": sum(1 for row in raw_rows_csv if row["audio_file"]),
        "resolved_links": sum(1 for link in links_csv if link["to_entry_id"]),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Normalize MainDictionary workbook data")
    parser.add_argument("--xlsx", required=True, help="Path to the source workbook")
    parser.add_argument("--sheet", default=SHEET_NAME_DEFAULT, help="Worksheet name")
    parser.add_argument(
        "--out-dir",
        default="reports/nufi-normalized-import",
        help="Directory where CSV artifacts will be written",
    )
    parser.add_argument(
        "--source-name",
        default="Dictionnaire_Nufi_Francais_Nufi_updated_2026.xlsx",
        help="Logical source name stored in the import run summary",
    )
    args = parser.parse_args(argv)

    summary = build_dictionary_csv_artifacts(
        Path(args.xlsx).expanduser().resolve(),
        Path(args.out_dir).resolve(),
        sheet_name=args.sheet,
        source_name=args.source_name,
    )
    sys.stdout.buffer.write((json.dumps(summary, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


if __name__ == "__main__":
    main()