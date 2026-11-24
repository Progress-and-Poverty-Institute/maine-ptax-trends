"""Maps each Maine municipality to one identifier, however a source spells its name.

Sources spell the same place differently: "Presque Is." / "Presque Isle", "St John Plt" /
"Saint John Plantation", "Aroostook - Unorganized" / "AROOSTOOK UT". This module maps any
of them to a single `muni_id` using input/municipal_key.csv.

Two steps:
    1. normalize()  removes the systematic variation (case, punctuation, Saint/St,
                    Isle/Is., Plantation/Plt, "County - Unorganized" / "UT").
    2. the key      maps each normalized spelling, and any listed alias, to muni_id.

    from lib import munikey
    df["muni_id"] = munikey.resolve(df["Place"])       # raises if any name is unknown

resolve() raises an error on any name it does not know. To fix it, add the name to the
`aliases` column of input/municipal_key.csv (pipe-separated) and re-run tests/test_munikey.py.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import pandas as pd

KEY_PATH = Path(__file__).resolve().parent.parent / "input" / "municipal_key.csv"


def normalize(name) -> str:
    s = re.sub(r"\s+", " ", str(name).upper().strip())
    s = re.sub(r"^(\w+) - UNORGANIZED$", r"\1 UT", s)        # "WALDO - UNORGANIZED" -> "WALDO UT"
    s = re.sub(r"\bPLANTATION\b", "PLT", s)
    s = re.sub(r"\bPLT\.", "PLT", s)
    s = re.sub(r"\bST\.?\s", "SAINT ", s)                    # "ST JOHN", "ST. JOHN" -> "SAINT JOHN"
    s = re.sub(r"\bIS\.?$", "ISLE", s)                       # "PRESQUE IS." -> "PRESQUE ISLE"
    s = re.sub(r"[.'’]", "", s).replace("-", " ")
    return re.sub(r"\s+", " ", s).strip()


@lru_cache(maxsize=1)
def key() -> pd.DataFrame:
    return pd.read_csv(KEY_PATH, dtype=str)


@lru_cache(maxsize=1)
def _lookup() -> dict[str, str]:
    k = key()
    out: dict[str, str] = {}
    for _, r in k.iterrows():
        names = [r["canonical_name"]] + [a for a in str(r.get("aliases", "") or "").split("|") if a and a != "nan"]
        for n in names:
            nk = normalize(n)
            if out.get(nk, r["muni_id"]) != r["muni_id"]:
                raise ValueError(f"municipal_key.csv: '{n}' maps to both {out[nk]} and {r['muni_id']}")
            out[nk] = r["muni_id"]
    return out


def resolve(names: pd.Series, strict: bool = True) -> pd.Series:
    """muni_id for each name. strict=True raises on any name the key does not know."""
    ids = names.map(lambda n: _lookup().get(normalize(n)))
    if strict and ids.isna().any():
        missing = sorted(names[ids.isna()].astype(str).unique())
        raise KeyError(f"{len(missing)} name(s) not in municipal_key.csv: {missing}")
    return ids
