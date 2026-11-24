"""Growth in the property tax commitment by type of municipality (Proposal 1).

Written in response to a Task Force member's question about whether the commitment grows faster
in some kinds of municipality, such as smaller towns. Uses the three-part typology adopted in
the Phase 2 report (input/municipal_classification.csv):

    size     Tiny Town ... City, by 2020 population
    service  service-center status (Primary, Secondary, Specialized, Small, SC-adjacent, Non-SC)
    economy  dominant economic type (bedroom, tourism, fishing, ...)

Method
    * Municipal MVR rows are matched to the typology through lib.munikey, never by raw name.
    * A fixed set of towns: only municipalities with a positive commitment in every year
      2012-2025, so a group's growth is never moved by towns entering or leaving the data
      (nine towns deorganized during the period; unorganized territories are excluded, as in
      the county and state series).
    * Group growth is the growth of the group's summed commitment (a dollar-weighted rate).
      Because small towns' commitments swing from year to year, the median of the town-level
      growth rates is reported alongside it, and growth is only ever measured over several years.
    * Real growth deflates by the Northeast CPI-U, as elsewhere in the report.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import munikey, trends as T

DIMS = {"size": "MuniType_Size", "service": "MuniType_Service", "economy": "MuniType_Economy"}
ORDER = {
    "size": ["Tiny Town", "Small Town", "Medium Town", "Large Town", "Small City", "City"],
    "service": ["Primary", "Secondary", "Specialized", "Small", "SC-adjacent", "Non-SC"],
}
PERIODS = [(2012, 2019), (2019, 2025), (2021, 2025), (2012, 2025)]
FIRST, LAST = 2012, T.LATEST_MVR_YEAR


def classification() -> pd.DataFrame:
    return pd.read_csv(T.INPUT / "municipal_classification.csv", dtype={"GEOCODENUM": str})


def muni_typed(balanced: bool = True) -> pd.DataFrame:
    """Municipal rows 2012-2025 with muni_id and the three types attached."""
    m = T.mvr_muni()
    m = m[~T.is_ut(m["Place"])].copy()
    m["muni_id"] = munikey.resolve(m["Place"])
    c = classification().rename(columns={"GEOCODENUM": "muni_id"})
    m = m.merge(c[["muni_id", "pop2020", *DIMS.values()]], on="muni_id", how="inner")
    m = m[m["Year"].between(FIRST, LAST)]
    if balanced:
        ok = (m[m["commitment"] > 0].groupby("muni_id")["Year"].nunique() == LAST - FIRST + 1)
        m = m[m["muni_id"].isin(ok[ok].index)]
    return m


def _cpi() -> pd.Series:
    return T.load_cpi().set_index("Year")["cpi"]


def _cagr(a: float, b: float, n: int) -> float:
    return (b / a) ** (1 / n) - 1 if a > 0 and b > 0 else np.nan


def by_type(dim: str, m: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per category: towns, people, commitment, and growth over each period."""
    m = muni_typed() if m is None else m
    col, cpi = DIMS[dim], _cpi()
    wide = m.pivot_table(index="muni_id", columns="Year", values="commitment", aggfunc="sum")
    cat = m.drop_duplicates("muni_id").set_index("muni_id")[[col, "pop2020"]]
    rows = []
    for name, ids in cat.groupby(col).groups.items():
        w, tot = wide.loc[ids], wide.loc[ids].sum()
        r = {"dimension": dim, "category": name, "towns": len(ids),
             "pop2020": int(cat.loc[ids, "pop2020"].sum()),
             f"commitment_{FIRST}": tot[FIRST], f"commitment_{LAST}": tot[LAST],
             f"per_capita_{LAST}": tot[LAST] / cat.loc[ids, "pop2020"].sum()}
        for a, b in PERIODS:
            n = b - a
            r[f"cagr_{a}_{b}"] = _cagr(tot[a], tot[b], n)
            r[f"cagr_real_{a}_{b}"] = _cagr(tot[a] / cpi[a], tot[b] / cpi[b], n)
            r[f"median_town_cagr_{a}_{b}"] = np.nanmedian([_cagr(x, y, n) for x, y in zip(w[a], w[b])])
        rows.append(r)
    out = pd.DataFrame(rows)
    order = [c for c in ORDER.get(dim, []) if c in set(out["category"])]
    rest = out[~out["category"].isin(order)].sort_values("towns", ascending=False)["category"].tolist()
    return out.set_index("category").loc[order + rest].reset_index()


def index_series(dim: str, m: pd.DataFrame | None = None, base: int = FIRST) -> pd.DataFrame:
    """Summed commitment per category and year, indexed to `base` = 100."""
    m = muni_typed() if m is None else m
    s = m.groupby([DIMS[dim], "Year"])["commitment"].sum().unstack(0)
    return 100 * s / s.loc[base]


def summary() -> pd.DataFrame:
    m = muni_typed()
    allrow = by_type("size", m.assign(MuniType_Size="All municipalities")).assign(dimension="all")
    return pd.concat([allrow, *[by_type(d, m) for d in DIMS]], ignore_index=True)


# ------------------------------------------------------------------ TRCF: municipal appropriations, 2022-2025
TRCF_FIRST = T.TRCF_FIRST_YEAR      # the Tax Rate Calculation Form is in the MVR from 2022 only
TRCF_PARTS = {"trcf_municipal": "Municipal", "trcf_education": "Local education",
              "trcf_county": "County tax", "commitment": "Property tax commitment"}


def trcf_typed(value: str = "trcf_municipal") -> pd.DataFrame:
    """Municipal rows 2022-2025 with the typology attached, restricted to a fixed set of
    towns reporting a positive `value` in every TRCF year."""
    m = muni_typed(balanced=False)
    m = m[m["Year"].between(TRCF_FIRST, LAST)]
    ok = m[m[value] > 0].groupby("muni_id")["Year"].nunique() == LAST - TRCF_FIRST + 1
    return m[m["muni_id"].isin(ok[ok].index)]


def trcf_by_type(dim: str, value: str = "trcf_municipal", m: pd.DataFrame | None = None) -> pd.DataFrame:
    """Growth 2022-2025 in one TRCF line (default Line 8, the municipal appropriation) by
    category, with the other appropriation lines and the commitment over the same towns."""
    m = trcf_typed(value) if m is None else m
    col, cpi, n = DIMS[dim], _cpi(), LAST - TRCF_FIRST
    cat = m.drop_duplicates("muni_id").set_index("muni_id")[[col, "pop2020"]]
    wide = {v: m.pivot_table(index="muni_id", columns="Year", values=v, aggfunc="sum") for v in TRCF_PARTS}
    rows = []
    for name, ids in cat.groupby(col).groups.items():
        pop = cat.loc[ids, "pop2020"].sum()
        tot = wide[value].loc[ids].sum()
        r = {"dimension": dim, "category": name, "towns": len(ids), "pop2020": int(pop),
             f"{value}_{TRCF_FIRST}": tot[TRCF_FIRST], f"{value}_{LAST}": tot[LAST],
             f"{value}_per_capita_{LAST}": tot[LAST] / pop,
             f"{value}_share_of_appropriations_{LAST}":
                 tot[LAST] / sum(wide[v].loc[ids].sum()[LAST] for v in ("trcf_municipal", "trcf_education", "trcf_county")),
             f"cagr_{value}": _cagr(tot[TRCF_FIRST], tot[LAST], n),
             f"cagr_real_{value}": _cagr(tot[TRCF_FIRST] / cpi[TRCF_FIRST], tot[LAST] / cpi[LAST], n),
             f"median_town_cagr_{value}": np.nanmedian([_cagr(a, b, n) for a, b in
                                                        zip(wide[value].loc[ids][TRCF_FIRST], wide[value].loc[ids][LAST])])}
        for v in TRCF_PARTS:
            if v != value:
                t = wide[v].loc[ids].sum()
                r[f"cagr_{v}"] = _cagr(t[TRCF_FIRST], t[LAST], n)
        rows.append(r)
    out = pd.DataFrame(rows)
    order = [c for c in ORDER.get(dim, []) if c in set(out["category"])]
    rest = out[~out["category"].isin(order)].sort_values("towns", ascending=False)["category"].tolist()
    return out.set_index("category").loc[order + rest].reset_index()


def trcf_summary(value: str = "trcf_municipal") -> pd.DataFrame:
    m = trcf_typed(value)
    allrow = trcf_by_type("size", value, m.assign(MuniType_Size="All municipalities")).assign(dimension="all")
    return pd.concat([allrow, *[trcf_by_type(d, value, m) for d in DIMS]], ignore_index=True)
