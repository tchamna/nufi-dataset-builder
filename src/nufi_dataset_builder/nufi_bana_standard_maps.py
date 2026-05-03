# -*- coding: utf-8 -*-
"""
Nufi orthography dictionaries: Bana → standard forms, tone stripping, etc.

Used for normalization / transliteration pipelines; import the dicts you need.

Word-of-the-day also excludes headwords containing any *key* from the Bana maps
(excluding dict_ton_bas); see `src/lib/nufiBanaForbiddenSubstrings.ts` — keep in sync.

Schwa + apostrophe (ə' …) rule (Komako)
---------------------------------------
For sequences **C + schwa (with tone) + apostrophe**, Bana uses **ə**; standard Komako
uses **e** with the same tone, and sometimes inserts **w** after the consonant.

• **Glide (insert w):**  Cə' → **Cw** + è'/é'/ē'/ě'/ê'
  Consonants: **k, c, g, y** (and **nj** as a cluster). So e.g. kə́'→kwé', gə̄'→gwē',
  yə̀'→ywè', njə́'→njwé'. Sequences like **nkə'** match the **kə'** substring → **nkw…'**.

• **No glide:**  Cə' → **C** + è'/é'/…
  Consonants / clusters: **l, n, p, s, t, h, nd, mb** (e.g. nə́'→né', ndə̀'→ndè', mbə̄'→mbē').

• **Fallback** (only if no longer Cə' pattern matched): bare **ə̀'…ə̂'** → **è'…ê'**
  (`vowel_bana_to_komako`). Prefer explicit Cə' rules first so **ngə'** etc. are not
  mangled by the bare rule alone.
"""

from __future__ import annotations

dict_bana_to_standard = {
    "nàh": "làh",
    "ndə̀b": "ndòm",
    "mɛ̀ɛ̀": "màà",
}

# One-character ɛ tone → a tone (Latin epsilon ɛ U+025B, not Greek ε)
dict_bana_to_standard_one_chr = {
    "ɛ̀": "à",
    "ɛ́": "á",
    "ɛ̄": "ā",
    "ɛ̌": "ǎ",
    "ɛ̂": "â",
}

dict_bana_to_standard_two_chr = {
    "ə̀b": "òm",
    "ə́b": "óm",
    "ə̄b": "ōm",
    "ə̌b": "ǒm",
    "ə̂b": "ôm",
    "ə̀h": "ɑ̀h",
    "ə́h": "ɑ́h",
    "ə̄h": "ɑ̄h",
    "ə̌h": "ɑ̌h",
    "ə̂h": "ɑ̂h",
}

_SCHWA_APOSTROPHE_TONES = (
    ("ə̀'", "è'"),
    ("ə́'", "é'"),
    ("ə̄'", "ē'"),
    ("ə̌'", "ě'"),
    ("ə̂'", "ê'"),
)


def _capitalize_prefix(prefix: str) -> str:
    if not prefix:
        return prefix
    return prefix[0].upper() + prefix[1:]


def _build_schwa_apostrophe_map(prefixes: tuple[str, ...], insert_w: bool) -> dict[str, str]:
    """Map C + toned ə + apostrophe → C[w] + toned e + apostrophe (lower and capital C)."""
    out: dict[str, str] = {}
    for p in prefixes:
        for schwa, e_toned in _SCHWA_APOSTROPHE_TONES:
            w = "w" if insert_w else ""
            key_lo = f"{p}{schwa}"
            out[key_lo] = f"{p}{w}{e_toned}"
            cap = _capitalize_prefix(p)
            out[f"{cap}{schwa}"] = f"{cap}{w}{e_toned}"
    return out


# Glide: k, c, g, y; cluster nj (nkə' handled via kə' substring).
_SCHWA_GLIDE_PREFIXES = ("k", "c", "g", "y", "nj")
# No glide: liquids/nasals/obstruents + clusters nd, mb.
_SCHWA_NO_GLIDE_PREFIXES = ("l", "n", "p", "s", "t", "h", "nd", "mb")

dict_bana_to_standard_three_chr = {
    "cīcō'ò": "cʉ̄cō'ò",
    "mbə̀pə̄'": "pə̀pə̄'",
    "nàh": "làh",
    "Nàh": "Làh",
    "kòlə̀'": "kwèlè'",
    "èlɑ̀": "ènɑ",
    "élɑ́": "énɑ́",
    "ēlɑ̄": "ēnɑ̄",
    "Bàt": "Pàt",
    "bàt": "pàt",
    **_build_schwa_apostrophe_map(_SCHWA_GLIDE_PREFIXES, True),
    **_build_schwa_apostrophe_map(_SCHWA_NO_GLIDE_PREFIXES, False),
}

dict_bana_to_standard_ab_am = {
    "àb": "àm",
    "áb": "ám",
    "āb": "ām",
    "ǎb": "ǎm",
    "âb": "âm",
}

vowel_bana_to_komako = {
    "ə̀'": "è'",
    "ə́'": "é'",
    "ə̄'": "ē'",
    "ə̌'": "ě'",
    "ə̂'": "ê'",
}

# Low tone → base vowel / sonorant (duplicate "ù" key removed)
dict_ton_bas = {
    "à": "a",
    "À": "A",
    "ɑ̀": "ɑ",
    "è": "e",
    "È": "E",
    "ɛ̀": "ɛ̀",
    "Ɛ̀": "Ɛ",
    "ə̀": "ə",
    "Ə̀": "Ə",
    "ì": "i",
    "Ì": "I",
    "ò": "o",
    "Ò": "O",
    "ɔ̀": "ɔ",
    "Ɔ̀": "Ɔ",
    "ù": "u",
    "Ù": "U",
    "ʉ̀": "ʉ",
    "ǹ": "n",
    "m̀": "m",
    "ŋ̀": "ŋ",
    "M̀": "M",
    "Ŋ̀": "Ŋ",
    # NFC composes N/n + grave → U+01F8/U+01F9 (Ǹ/ǹ); strip ton bas after normalize
    "ǹ": "n",
    "Ǹ": "N",
}

__all__ = [
    "dict_bana_to_standard",
    "dict_bana_to_standard_one_chr",
    "dict_bana_to_standard_two_chr",
    "dict_bana_to_standard_three_chr",
    "dict_bana_to_standard_ab_am",
    "vowel_bana_to_komako",
    "dict_ton_bas",
]
