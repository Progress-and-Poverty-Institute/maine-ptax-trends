"""Time Trends report (Proposal 1): MVR panel, external series, and derived measures.

Geographies: Maine statewide plus its 16 counties. Years: 2012-2025.

MVR measures (municipal rows summed to county/state; unorganized territories excluded, see INCLUDE_UT):
    commitment      Line 13, net property tax commitment
    taxable_value   Line 11, total taxable valuation
    market_value    sum over munis of Line 11 / certified ratio
    parcels         Line 42, land parcels
    mill_rate       commitment / taxable_value                (nominal, decimal)
    certified_ratio taxable_value / market_value
    etr             commitment / market_value                 (effective tax rate)
    avg_bill        commitment / parcels                      (parcel-mean bill)

External series are read from input/trends/ (see scripts/trends_pull.py).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
INPUT = REPO / "input"
TRENDS_IN = INPUT / "trends"
TRENDS_OUT = REPO / "output" / "trends"

YEARS = list(range(2012, 2026))
LATEST_MVR_YEAR = 2025

# Maine homestead exemption (of just value) by MVR year, 36 M.R.S. 683.
HOMESTEAD_EXEMPTION = {
    2012: 10_000, 2013: 10_000, 2014: 10_000, 2015: 10_000,
    2016: 15_000, 2017: 20_000, 2018: 20_000, 2019: 20_000,
    2020: 25_000, 2021: 25_000, 2022: 25_000, 2023: 25_000,
    2024: 25_000, 2025: 25_000,
}

# MVR CSV column -> panel column (2022+ "Line N" naming, unchanged in 2025).
MVR_CSV_COLS = {
    "Certified Ratio": "certified_ratio",
    "Line 11": "total_taxableval",
    "Line 12": "mill_rate",
    "Line 13": "commitment",
    "Line 42": "land_parcels",
    "Line 14e": "hstead_count",
    "Line 14f": "hstead_eval",
}
CORE = ["Year", "County_ofMuni", "Place", *MVR_CSV_COLS.values()]

# Tax Rate Calculation Form (TRCF), reported in the MVR from 2022 only.
# 7+8+9+10 = 11 (appropriations); 11 - 12 - 13 = 15 (net to be raised by property tax).
# 15 = commitment (MVR Line 13 = TRCF 19) + homestead (21) and BETE (22) reimbursements - overlay (23).
TRCF_COLS = {
    "TRCF: Line 7": "trcf_county",          # county tax
    "TRCF: Line 8": "trcf_municipal",       # municipal appropriation
    "TRCF: Line 9": "trcf_tif",             # TIF financing plan amount
    "TRCF: Line 10": "trcf_education",      # local education appropriation
    "TRCF: Line 11": "trcf_appropriations", # total appropriations
    "TRCF: Line 12": "trcf_revshare",       # state municipal revenue sharing
    "TRCF: Line 13": "trcf_other_rev",      # other revenues
    "TRCF: Line 15": "trcf_net",            # net to be raised by local property tax
    "TRCF: Line 21": "trcf_hstead_reimb",   # homestead exemption reimbursement
    "TRCF: Line 22": "trcf_bete_reimb",     # BETE reimbursement
}
TRCF_FIRST_YEAR = 2022
# the 2012-24 master renamed three TRCF lines
MASTER_TRCF_NAMES = {"Appropriations": "TRCF: Line 11", "Expected RevShare": "TRCF: Line 12",
                     "Other Revs (incl Reimbursements)": "TRCF: Line 13"}

MVR_FILES = {  # years not yet in input/master_mvr_2012_24.csv
    2025: INPUT / "2025 MVR Summary.csv",
}


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype(str).str.replace(",", "").str.strip(), errors="coerce")


def load_mvr_csv(path: Path, year: int) -> pd.DataFrame:
    """One year of the MRS MVR summary CSV -> municipal rows in master_mvr layout."""
    d = pd.read_csv(path, encoding="cp1252")
    d = d[~d["Municipality"].astype(str).str.strip().str.upper().eq("TOTAL")]
    out = pd.DataFrame({
        "Year": year,
        "County_ofMuni": d["County"].str.strip().str.upper(),
        "Place": d["Municipality"].str.strip(),
    })
    for src, dst in {**MVR_CSV_COLS, **TRCF_COLS}.items():
        out[dst] = _num(d[src])
    return out.reset_index(drop=True)


def mvr_muni() -> pd.DataFrame:
    """Municipal MVR rows 2012-2025: the cleaned 2012-24 master plus newer CSVs."""
    m = pd.read_csv(INPUT / "master_mvr_2012_24.csv", low_memory=False)
    m = m.loc[m["Aggregation"].eq("Muni")].rename(columns=MASTER_TRCF_NAMES).rename(columns=TRCF_COLS)
    m = m[CORE + list(TRCF_COLS.values())].copy()
    for c in TRCF_COLS.values():
        m[c] = _num(m[c])
    new = [load_mvr_csv(p, y) for y, p in MVR_FILES.items()]
    m = pd.concat([m, *new], ignore_index=True)
    # 2012-21 label counties "X COUNTY", 2022+ just "X"
    m["County_ofMuni"] = (m["County_ofMuni"].str.strip().str.upper()
                          .str.replace(r"\s+COUNTY$", "", regex=True))
    m = fix_trcf(m)
    return m.sort_values(["Year", "County_ofMuni", "Place"])


# Keying errors in individual TRCF lines: (place, year) -> {column: multiplier}. Found by
# trcf_check(); each is repaired here and appropriations / net to be raised recomputed.
TRCF_FIXES = {
    # education entered as 36,700,245 (other years ~$370-470k; commitment $507k): decimal point lost
    ("COLUMBIA FALLS", 2022): {"trcf_education": 0.01},
}


# Reporting-convention breaks, corrected by moving a dollar amount out of two lines at once:
# (place, year) -> (amount, [lines to reduce by it]). Net to be raised (Line 15) is unchanged.
TRCF_NETTING = {
    # Sanford reported its GROSS school budget in 2022 ($59.3M education, with state school aid
    # counted in other revenues, $56.6M) and the NET local appropriation from 2023 ($16.4M; other
    # revenues $14.9M). Net out the state aid from both lines. The aid is estimated as the drop in
    # other revenues between 2022 and 2023 ($41.7M), i.e. other revenues are held at their 2023
    # level. Left uncorrected it cuts statewide education growth 2022-23 from about 5% to under 3%.
    ("SANFORD", 2022): (56_625_273 - 14_890_946, ["trcf_education", "trcf_other_rev"]),
}
APPROPRIATION_LINES = ["trcf_county", "trcf_municipal", "trcf_tif", "trcf_education"]
REVENUE_LINES = ["trcf_revshare", "trcf_other_rev"]


def fix_trcf(m: pd.DataFrame) -> pd.DataFrame:
    """Apply TRCF_FIXES (keying errors) and TRCF_NETTING (reporting-convention breaks),
    keeping Line 11 = 7+8+9+10 and Line 15 = 11-12-13 true after each change."""
    m = m.copy()
    for (place, year), fixes in TRCF_FIXES.items():
        row = m["Place"].str.upper().eq(place) & m["Year"].eq(year)
        for col, mult in fixes.items():
            delta = m.loc[row, col] * (mult - 1)
            m.loc[row, col] += delta
            m.loc[row, "trcf_appropriations"] += delta      # Line 11 = 7 + 8 + 9 + 10
            m.loc[row, "trcf_net"] += delta                 # Line 15 = 11 - 12 - 13
    for (place, year), (amount, cols) in TRCF_NETTING.items():
        row = m["Place"].str.upper().eq(place) & m["Year"].eq(year)
        for col in cols:
            m.loc[row, col] -= amount
            if col in APPROPRIATION_LINES:
                m.loc[row, "trcf_appropriations"] -= amount
                m.loc[row, "trcf_net"] -= amount
            elif col in REVENUE_LINES:
                m.loc[row, "trcf_net"] += amount
    return m


def trcf_check(m: pd.DataFrame | None = None, tol: float = 0.5, min_gap: float = 1e6) -> pd.DataFrame:
    """Town-years where net to be raised (TRCF 15) is far from commitment + homestead and BETE
    reimbursements (they should differ only by the overlay). Remaining known case: Dedham 2025
    (TRCF internally consistent but appropriations fall ~25% while commitment rises 21%; left as
    reported, query for MRS)."""
    m = (mvr_muni() if m is None else m).copy()
    m = m[(m["Year"] >= TRCF_FIRST_YEAR) & ~is_ut(m["Place"])]
    expect = m["commitment"] + m["trcf_hstead_reimb"].fillna(0) + m["trcf_bete_reimb"].fillna(0)
    ratio = m["trcf_net"] / expect
    bad = ((m["trcf_net"] - expect).abs() > min_gap) & ((ratio > 1 + tol) | (ratio < 1 / (1 + tol)))
    return m.loc[bad, ["Year", "Place", "commitment", "trcf_net"]].assign(expected=expect[bad], ratio=ratio[bad])


def clean_parcels(muni: pd.DataFrame, hi: float = 2.5, lo: float = 0.4) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Repair data-entry errors and gaps in Line 42 (land parcels).

    1. A count of 0 is treated as not reported.
    2. A reported count above `hi` x or below `lo` x the median of the town's
       other reported years is treated as a keying error (e.g. Caribou 43,000
       in 2020 against a usual ~4,300).
    3. Each missing or flagged town-year is filled with the mean of the nearest
       good years before and after (or whichever one exists).
    Towns with no good year at all stay missing; mvr_panel() then leaves them
    out of the average-bill numerator and denominator alike.
    Returns (cleaned rows, log of every change).
    """
    m = muni.copy()
    m["land_parcels_raw"] = m["land_parcels"]
    log = []
    for place, g in m.groupby("Place"):
        s = g.set_index("Year")["land_parcels"]
        if s.index.duplicated().any():
            continue
        rep = s.where(s > 0)
        med = pd.Series({y: (o.median() if len(o := rep.drop(y).dropna()) else np.nan)
                         for y in s.index})
        bad = rep.isna() | (rep > hi * med) | (rep < lo * med)
        good = rep[~bad].dropna()
        for y in s.index[bad]:
            nb = pd.concat([good[good.index < y].tail(1), good[good.index > y].head(1)])
            fix = round(nb.mean()) if len(nb) else np.nan
            reason = "zero/missing" if pd.isna(rep[y]) else "outlier"
            if pd.isna(fix) and reason == "zero/missing":
                fix_val = np.nan
            else:
                fix_val = fix
            log.append({"Place": place, "Year": y, "reason": reason, "raw": s[y],
                        "new": fix_val, "town_median_other_years": med[y]})
            m.loc[(m["Place"] == place) & (m["Year"] == y), "land_parcels"] = fix_val
    return m, pd.DataFrame(log)


UT_PATTERN = r"(?:\s+UT$|UNORGANIZED)"
INCLUDE_UT = False   # county unorganized-territory rows exist in the data only from 2017;
                     # excluding them in every year keeps the 2012-2025 series consistent.


def is_ut(place: pd.Series) -> pd.Series:
    return place.astype(str).str.upper().str.strip().str.contains(UT_PATTERN, regex=True)


def mvr_panel(muni: pd.DataFrame | None = None, include_ut: bool = INCLUDE_UT) -> pd.DataFrame:
    """Aggregate municipal rows to county and statewide, one row per (Year, County).
    include_ut=False drops unorganized-territory rows in every year (see INCLUDE_UT)."""
    m = (clean_parcels(mvr_muni())[0] if muni is None else muni).copy()
    if not include_ut:
        m = m[~is_ut(m["Place"])]
    cr = m["certified_ratio"].where(m["certified_ratio"] > 0)
    m["market_value"] = m["total_taxableval"] / cr
    m["commitment_w_parcels"] = m["commitment"].where(m["land_parcels"] > 0)
    agg = {"commitment": "sum", "commitment_w_parcels": "sum", "total_taxableval": "sum", "market_value": "sum",
           "land_parcels": "sum", "hstead_count": "sum", "Place": "count",
           "certified_ratio": lambda s: s.isna().sum(),
           # TRCF exists from 2022 only: all-missing years stay missing rather than summing to 0
           **{c: (lambda s: s.sum(min_count=1)) for c in TRCF_COLS.values()}}
    county = m.groupby(["Year", "County_ofMuni"]).agg(agg).reset_index()
    county["County"] = county.pop("County_ofMuni").str.title()
    state = m.groupby("Year").agg(agg).reset_index().assign(County="Maine")
    p = pd.concat([state, county], ignore_index=True).rename(columns={
        "total_taxableval": "taxable_value", "land_parcels": "parcels",
        "Place": "n_munis", "certified_ratio": "n_missing_ratio"})
    p["mill_rate"] = p["commitment"] / p["taxable_value"]
    p["certified_ratio"] = p["taxable_value"] / p["market_value"]
    p["etr"] = p["commitment"] / p["market_value"]
    p["avg_bill"] = p["commitment_w_parcels"] / p["parcels"]
    return p[["Year", "County", "n_munis", "n_missing_ratio", "commitment", "taxable_value",
              "market_value", "parcels", "hstead_count", "mill_rate", "certified_ratio",
              "etr", "avg_bill", *TRCF_COLS.values()]].sort_values(["County", "Year"]).reset_index(drop=True)


# ----------------------------------------------------------------- external series
def load_cpi() -> pd.DataFrame:
    """Northeast CPI-U all items (CUUR0100SA0), annual average. 2025 = 11 months."""
    return pd.read_csv(TRENDS_IN / "cpi_ne_annual.csv")[["Year", "cpi", "months"]]


def load_bea() -> pd.DataFrame:
    """BEA implicit price deflator, state & local government purchases (national, 2017=100)."""
    return pd.read_csv(TRENDS_IN / "bea_sl_deflator_annual.csv")[["Year", "bea_sl_deflator"]]


def load_acs1() -> pd.DataFrame:
    """ACS 1-year median home value and owner-occupied median income (Maine + 6 counties)."""
    a = pd.read_csv(TRENDS_IN / "acs1_maine.csv")
    return a.drop(columns="geo")


def _annual_mean(df: pd.DataFrame, date_col: str, val_col: str, out: str) -> pd.DataFrame:
    d = df.copy()
    d["Year"] = pd.to_datetime(d[date_col]).dt.year
    g = d.groupby(["County", "Year"])[val_col].agg(["mean", "count"]).reset_index()
    return g.rename(columns={"mean": out, "count": f"{out}_months"})


def load_zillow() -> pd.DataFrame:
    """Zillow ZHVI, calendar-year mean of monthly values."""
    z = pd.read_csv(TRENDS_IN / "zillow_zhvi_maine_monthly.csv")
    return _annual_mean(z, "date", "zhvi", "zhvi")


def load_redfin() -> pd.DataFrame:
    """Redfin median sale price (All Residential, NSA), calendar-year mean of monthly medians."""
    r = pd.read_csv(TRENDS_IN / "redfin_maine_monthly.csv")
    return _annual_mean(r, "PERIOD_BEGIN", "MEDIAN_SALE_PRICE", "redfin_med_price")


def load_fhfa() -> pd.DataFrame:
    """FHFA annual all-transactions HPI (developmental), Maine + counties, base 2000=100."""
    cols = ["a", "b", "fips", "Year", "fhfa_chg_pct", "hpi", "hpi_1990", "fhfa_hpi_2000"]
    s = pd.read_excel(TRENDS_IN / "fhfa_hpi_at_state.xlsx", skiprows=6, names=cols, dtype={"fips": str})
    s = s[s["b"].eq("ME")].assign(County="Maine")
    c = pd.read_excel(TRENDS_IN / "fhfa_hpi_at_county.xlsx", skiprows=6, names=cols, dtype={"fips": str})
    c = c[c["a"].eq("ME")].assign(County=lambda d: d["b"].str.strip())
    out = pd.concat([s, c], ignore_index=True)[["County", "Year", "fhfa_chg_pct", "fhfa_hpi_2000"]]
    for v in ("fhfa_chg_pct", "fhfa_hpi_2000"):
        out[v] = pd.to_numeric(out[v], errors="coerce")
    return out


def build_panel(start: int = 2000, include_ut: bool = INCLUDE_UT) -> pd.DataFrame:
    """One row per (County, Year): MVR measures plus every external series and CPI."""
    frames = [mvr_panel(include_ut=include_ut), load_acs1(), load_zillow(), load_redfin(), load_fhfa()]
    keys = ["County", "Year"]
    p = frames[0]
    for f in frames[1:]:
        p = p.merge(f, on=keys, how="outer")
    p = p.merge(load_cpi().rename(columns={"months": "cpi_months"}), on="Year", how="left")
    p = p.merge(load_bea(), on="Year", how="left")
    p["homestead_exemption"] = p["Year"].map(HOMESTEAD_EXEMPTION)
    return p[p["Year"].between(start, LATEST_MVR_YEAR)].sort_values(keys).reset_index(drop=True)


# ----------------------------------------------------------------- derived measures
REAL_BASE_YEAR = 2025
REDFIN_START = 2016   # Redfin's Maine coverage expands sharply in 2016 (statewide sales
                      # in the tracker go 6,400 -> 17,259); earlier years are not comparable.
DOLLAR_COLS = ["commitment", "avg_bill", "homestead_bill", "med_owner_income",
               "zhvi", "redfin_med_price", "med_home_value"]


def add_derived(p: pd.DataFrame, base_year: int = REAL_BASE_YEAR) -> pd.DataFrame:
    """Median homestead bill, tax share of income, and real (base-year $) versions.

    homestead_bill   = (ACS median home value - homestead exemption) x ETR
                       (= (V - HE) x certified ratio x mill rate, at county/state level)
    tax_share_income = homestead_bill / ACS owner-occupied median household income
    *_real           = nominal x CPI[base_year] / CPI[year]   (Northeast CPI-U)
    """
    p = p.copy()
    p.loc[p["Year"] < REDFIN_START, "redfin_med_price"] = np.nan
    p["homestead_bill"] = (p["med_home_value"] - p["homestead_exemption"]).clip(lower=0) * p["etr"]
    p["tax_share_income"] = p["homestead_bill"] / p["med_owner_income"]
    cpi_base = p.loc[p["Year"] == base_year, "cpi"].dropna().iloc[0]
    p["deflator"] = cpi_base / p["cpi"]
    for c in DOLLAR_COLS:
        p[f"{c}_real"] = p[c] * p["deflator"]
    return p


def panel(include_ut: bool = INCLUDE_UT) -> pd.DataFrame:
    """The analysis panel: build_panel() + add_derived()."""
    return add_derived(build_panel(include_ut=include_ut))
