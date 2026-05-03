# -*- coding: utf-8 -*-
"""
Classify Nufi lemmas as Bana vs non-Bana using the same Bana dictionary keys as
`nufi_bana_standard_maps.py` (excludes `dict_ton_bas`).

Shared by `dump_bana_headword_audit.py` and `local_dictionary_db.py`.
"""

from __future__ import annotations

import unicodedata

from nufi_dataset_builder.nufi_bana_standard_maps import (
    dict_bana_to_standard,
    dict_bana_to_standard_ab_am,
    dict_bana_to_standard_one_chr,
    dict_bana_to_standard_three_chr,
    dict_bana_to_standard_two_chr,
    vowel_bana_to_komako,
)


def collect_bana_keys() -> list[str]:
    keys: set[str] = set()
    for d in (
        dict_bana_to_standard,
        dict_bana_to_standard_one_chr,
        dict_bana_to_standard_two_chr,
        dict_bana_to_standard_three_chr,
        dict_bana_to_standard_ab_am,
        vowel_bana_to_komako,
    ):
        keys.update(d.keys())
    return sorted(keys, key=len, reverse=True)


def first_matching_bana_key(word: str, sorted_keys: list[str]) -> str | None:
    nfc = unicodedata.normalize("NFC", word.strip())
    for key in sorted_keys:
        if not key:
            continue
        k = unicodedata.normalize("NFC", key)
        if k in nfc:
            return key
    return None


def orthography_category_for_lemma(word: str, sorted_keys: list[str] | None = None) -> str:
    keys = sorted_keys if sorted_keys is not None else collect_bana_keys()
    return "bana" if first_matching_bana_key(word, keys) is not None else "non_bana"


__all__ = [
    "collect_bana_keys",
    "first_matching_bana_key",
    "orthography_category_for_lemma",
]
