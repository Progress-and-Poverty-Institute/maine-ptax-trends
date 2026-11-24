#!/usr/bin/env python3
"""Pull the external series for the Time Trends report (Proposal 1) into input/trends/.

Each source is pulled by its own function and written to disk, so the analysis
(lib/trends.py, 40-time-trends.ipynb) runs offline from the saved files.

    python scripts/trends_pull.py            # pull everything
    python scripts/trends_pull.py acs cpi    # pull only some sources

Sources
  cpi     Northeast CPI-U, all items (BLS CUUR0100SA0, via FRED), monthly + annual average
  acs     ACS 1-year B25077_001E (median value, owner-occupied) and B25119_002E
          (median household income, owner-occupied), with MOEs, Maine + counties,
          2005-2025. 2020 has no standard 1-year release; a year not yet released
          is skipped with a message. Only counties of 65,000+ are published.
  zillow  ZHVI (all homes, mid tier, smoothed, SA), monthly, Maine + counties
  redfin  Redfin Data Center market tracker, MEDIAN_SALE_PRICE, Maine + counties,
          All Residential, not seasonally adjusted
  fhfa    FHFA annual HPI (all-transactions, repeat sales), state + county files
  bea     BEA implicit price deflator, state and local government consumption
          expenditures and gross investment (national, annual; via FRED)

Reads CENSUS_API_KEY from .env.
"""
from __future__ import annotations

import gzip
import io
import os
import sys
import tempfile
from pathlib import Path

import pandas as pd
import requests

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "input" / "trends"
OUT.mkdir(parents=True, exist_ok=True)

ME_FIPS = "23"
ACS_YEARS = [y for y in range(2005, 2026) if y != 2020]
ACS_VARS = ["B25077_001E", "B25077_001M", "B25119_002E", "B25119_002M"]

CPI_SERIES = "CUUR0100SA0"
BEA_SL_SERIES = "A829RD3A086NBEA"
ZILLOW = "https://files.zillowstatic.com/research/public_csvs/zhvi/{geo}_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv"
REDFIN = "https://redfin-public-data.s3.us-west-2.amazonaws.com/redfin_market_tracker/{geo}_market_tracker.tsv000.gz"
FHFA = "https://www.fhfa.gov/hpi/download/annual/hpi_at_{geo}.xlsx"


def load_env() -> None:
    env = REPO / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _get(url: str, **kw) -> requests.Response:
    r = requests.get(url, timeout=kw.pop("timeout", 120), **kw)
    r.raise_for_status()
    return r


# --------------------------------------------------------------------------- CPI
def pull_cpi() -> None:
    r = _get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={CPI_SERIES}")
    m = pd.read_csv(io.StringIO(r.text))
    m.columns = ["date", "cpi"]
    m["date"] = pd.to_datetime(m["date"])
    m["cpi"] = pd.to_numeric(m["cpi"], errors="coerce")
    m.to_csv(OUT / "cpi_ne_monthly.csv", index=False)
    a = (m.assign(Year=m["date"].dt.year).groupby("Year")["cpi"]
           .agg(cpi="mean", months="count").reset_index())
    # Full calendar years only, except that 2025 has 11 months: BLS collected no
    # October 2025 CPI because of the federal shutdown. Its annual figure is the
    # mean of the 11 published months; the `months` column records this.
    a = a[(a["months"] == 12) | ((a["Year"] == 2025) & (a["months"] == 11))]
    a["series"] = CPI_SERIES
    a.to_csv(OUT / "cpi_ne_annual.csv", index=False)
    print(f"cpi: {len(m)} months, annual {a.Year.min()}-{a.Year.max()}")


# --------------------------------------------------------------------------- BEA
def pull_bea() -> None:
    """Price index for what state and local governments buy (compensation, goods and
    services, construction). National only; no state or regional version exists."""
    r = _get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={BEA_SL_SERIES}")
    a = pd.read_csv(io.StringIO(r.text))
    a.columns = ["date", "bea_sl_deflator"]
    a["Year"] = pd.to_datetime(a["date"]).dt.year
    a["bea_sl_deflator"] = pd.to_numeric(a["bea_sl_deflator"], errors="coerce")
    a = a.dropna()[["Year", "bea_sl_deflator"]].assign(series=BEA_SL_SERIES)
    a.to_csv(OUT / "bea_sl_deflator_annual.csv", index=False)
    print(f"bea: annual {a.Year.min()}-{a.Year.max()}")


# --------------------------------------------------------------------------- ACS
def pull_acs() -> None:
    load_env()
    key = os.environ.get("CENSUS_API_KEY")
    frames = []
    for y in ACS_YEARS:
        base = f"https://api.census.gov/data/{y}/acs/acs1"
        for geo, extra in (("state", {"for": f"state:{ME_FIPS}"}),
                           ("county", {"for": "county:*", "in": f"state:{ME_FIPS}"})):
            params = {"get": "NAME," + ",".join(ACS_VARS), "key": key, **extra}
            r = requests.get(base, params=params, timeout=60)
            if r.status_code != 200 or not r.text.startswith("["):
                print(f"acs: {y} {geo} not available (HTTP {r.status_code}) - skipped")
                continue
            rows = r.json()
            d = pd.DataFrame(rows[1:], columns=rows[0])
            d["Year"], d["geo"] = y, geo
            frames.append(d)
    acs = pd.concat(frames, ignore_index=True)
    for v in ACS_VARS:
        acs[v] = pd.to_numeric(acs[v], errors="coerce")
        acs.loc[acs[v] < 0, v] = pd.NA            # Census annotation codes -> missing
    acs["County"] = (acs["NAME"].str.replace(", Maine", "", regex=False)
                     .str.replace(" County", "", regex=False))
    acs.loc[acs["geo"] == "state", "County"] = "Maine"
    acs = acs.rename(columns={"B25077_001E": "med_home_value", "B25077_001M": "med_home_value_moe",
                              "B25119_002E": "med_owner_income", "B25119_002M": "med_owner_income_moe"})
    keep = ["Year", "geo", "County", "med_home_value", "med_home_value_moe",
            "med_owner_income", "med_owner_income_moe"]
    acs[keep].sort_values(["geo", "County", "Year"]).to_csv(OUT / "acs1_maine.csv", index=False)
    cov = acs[acs.geo == "county"].groupby("Year")["County"].nunique()
    print(f"acs: years {sorted(acs.Year.unique())}\n     counties per year: {cov.to_dict()}")


# ------------------------------------------------------------------------ Zillow
def pull_zillow() -> None:
    out = []
    for geo in ("State", "County"):
        d = pd.read_csv(io.StringIO(_get(ZILLOW.format(geo=geo)).text))
        d = d[d["StateName"].eq("ME") | d["RegionName"].eq("Maine")] if geo == "County" else d[d["RegionName"].eq("Maine")]
        date_cols = [c for c in d.columns if c[:2] in ("19", "20")]
        long = d.melt(id_vars=["RegionName"], value_vars=date_cols, var_name="date", value_name="zhvi")
        long["geo"] = geo.lower()
        out.append(long)
    z = pd.concat(out, ignore_index=True)
    z["County"] = z["RegionName"].str.replace(" County", "", regex=False)
    z[["geo", "County", "date", "zhvi"]].to_csv(OUT / "zillow_zhvi_maine_monthly.csv", index=False)
    print(f"zillow: {z.County.nunique()} geographies, {z.date.min()} to {z.date.max()}")


# ------------------------------------------------------------------------ Redfin
def pull_redfin() -> None:
    out = []
    for geo in ("state", "county"):
        with tempfile.NamedTemporaryFile(suffix=".gz", delete=False) as tmp:
            with requests.get(REDFIN.format(geo=geo), stream=True, timeout=600) as r:
                r.raise_for_status()
                for chunk in r.iter_content(1 << 20):
                    tmp.write(chunk)
            path = tmp.name
        keep = []
        with gzip.open(path, "rt") as fh:
            for ch in pd.read_csv(fh, sep="\t", chunksize=250_000, low_memory=False):
                ch.columns = [c.upper() for c in ch.columns]
                ch = ch[(ch["STATE_CODE"] == "ME") & (ch["PROPERTY_TYPE"] == "All Residential")
                        & (ch["IS_SEASONALLY_ADJUSTED"].astype(str).str.lower() == "false")]
                if len(ch):
                    keep.append(ch)
        os.unlink(path)
        d = pd.concat(keep, ignore_index=True)
        d["geo"] = geo
        out.append(d)
    rf = pd.concat(out, ignore_index=True)
    rf["County"] = (rf["REGION"].str.replace(", ME", "", regex=False)
                    .str.replace(" County", "", regex=False))
    rf.loc[rf.geo == "state", "County"] = "Maine"
    cols = ["geo", "County", "PERIOD_BEGIN", "PERIOD_END", "PERIOD_DURATION",
            "MEDIAN_SALE_PRICE", "HOMES_SOLD"]
    rf[[c for c in cols if c in rf.columns]].to_csv(OUT / "redfin_maine_monthly.csv", index=False)
    print(f"redfin: {rf.County.nunique()} geographies, {rf.PERIOD_BEGIN.min()} to {rf.PERIOD_BEGIN.max()}, "
          f"durations {sorted(rf.PERIOD_DURATION.unique())}")


# -------------------------------------------------------------------------- FHFA
def pull_fhfa() -> None:
    for geo in ("state", "county"):
        (OUT / f"fhfa_hpi_at_{geo}.xlsx").write_bytes(_get(FHFA.format(geo=geo)).content)
    print("fhfa: saved fhfa_hpi_at_state.xlsx, fhfa_hpi_at_county.xlsx")


SOURCES = {"cpi": pull_cpi, "acs": pull_acs, "zillow": pull_zillow,
           "redfin": pull_redfin, "fhfa": pull_fhfa, "bea": pull_bea}

SOURCE_FILES = {"cpi": "cpi_ne_annual.csv, cpi_ne_monthly.csv", "acs": "acs1_maine.csv",
                "zillow": "zillow_zhvi_maine_monthly.csv", "redfin": "redfin_maine_monthly.csv",
                "fhfa": "fhfa_hpi_at_state.xlsx, fhfa_hpi_at_county.xlsx",
                "bea": "bea_sl_deflator_annual.csv"}
SNAPSHOT = OUT / "SNAPSHOT.csv"


def record_pull(name: str) -> None:
    """Stamp input/trends/SNAPSHOT.csv with the date this source was last pulled."""
    from datetime import date
    s = (pd.read_csv(SNAPSHOT, dtype=str) if SNAPSHOT.exists()
         else pd.DataFrame(columns=["source", "files", "pulled_on"]))
    s = pd.concat([s[s["source"] != name],
                   pd.DataFrame([[name, SOURCE_FILES[name], date.today().isoformat()]], columns=s.columns)],
                  ignore_index=True)
    s.sort_values("source").to_csv(SNAPSHOT, index=False)


if __name__ == "__main__":
    for name in (sys.argv[1:] or SOURCES):
        SOURCES[name]()
        record_pull(name)
