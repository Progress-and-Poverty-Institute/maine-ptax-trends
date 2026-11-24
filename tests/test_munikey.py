"""Every municipal name this repo reads must resolve to exactly one muni_id.

Run:  python -m pytest tests/
A failure names the unknown spelling: add it to the `aliases` column of
input/municipal_key.csv rather than changing the data.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import munikey, trends as T  # noqa: E402


def test_every_mvr_name_2012_2025_resolves():
    m = T.mvr_muni()
    ids = munikey.resolve(m["Place"])          # raises KeyError listing any unknown name
    assert ids.notna().all()


def test_one_row_per_town_year():
    m = T.mvr_muni().assign(muni_id=lambda d: munikey.resolve(d["Place"]))
    dup = m[m.duplicated(["muni_id", "Year"], keep=False)]
    assert dup.empty, dup[["Year", "Place", "muni_id"]]


def test_classification_resolves_to_its_own_id():
    c = pd.read_csv(T.INPUT / "municipal_classification.csv", dtype={"GEOCODENUM": str})
    assert (munikey.resolve(c["MUNI"]) == c["GEOCODENUM"]).all()


def test_key_ids_are_unique():
    k = munikey.key()
    assert k["muni_id"].is_unique


def test_known_spelling_variants():
    cases = {"Presque Is.": "PRESQUE ISLE", "St. John Plantation": "SAINT JOHN PLT",
             "St John Plt": "SAINT JOHN PLT", "Aroostook - Unorganized": "AROOSTOOK UT"}
    for raw, want in cases.items():
        assert munikey.normalize(raw) == want
    assert munikey.resolve(pd.Series(["Presque Is.", "PRESQUE ISLE"])).nunique() == 1
