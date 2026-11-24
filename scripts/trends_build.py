#!/usr/bin/env python3
"""Build the Time Trends report outputs from the data committed in input/ (offline; no downloads or keys).
Run scripts/trends_pull.py first only if you want to refresh that data.

    python scripts/trends_build.py

Writes to output/trends/:
    panel.csv                    every measure, Maine + 16 counties, 2000-2025
    summary_by_geo.csv           key years and growth rates per geography
    summary_by_muni_type.csv     commitment growth by type of municipality (size, service, economy)
    summary_municipal_appropriations_by_type.csv   2022-2025 growth in TRCF Line 8 by type
    charts/types/*.png           growth by type of municipality
    parcel_cleaning_log.csv      every Line 42 repair
    charts/state/*.png           the eight state charts
    charts/county/*__by_county.png   small multiples
    charts/county/*__<county>.png    the eight charts for each county
"""
import sys
import warnings
from pathlib import Path

warnings.simplefilter("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from lib import trends as T
from lib import trends_charts as C
from lib import trends_types as TT


def summary(p: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for geo, d in p.groupby("County"):
        d = d.set_index("Year")
        r = {"County": geo}
        for c in ["commitment", "commitment_real", "mill_rate", "etr", "avg_bill", "avg_bill_real",
                  "homestead_bill", "tax_share_income", "zhvi", "fhfa_hpi_2000", "med_home_value",
                  "med_owner_income"]:
            for y in (2012, 2019, 2024, 2025):
                r[f"{c}_{y}"] = d[c].get(y, np.nan)
        for c in ["commitment", "commitment_real", "avg_bill", "avg_bill_real"]:
            for a, b in ((2012, 2025), (2012, 2019), (2019, 2025), (2021, 2025)):
                r[f"{c}_cagr_{a}_{b}"] = (d.loc[b, c] / d.loc[a, c]) ** (1 / (b - a)) - 1
        rows.append(r)
    out = pd.DataFrame(rows)
    return pd.concat([out[out.County == "Maine"], out[out.County != "Maine"]], ignore_index=True)


if __name__ == "__main__":
    T.TRENDS_OUT.mkdir(parents=True, exist_ok=True)
    p = T.panel()
    p.to_csv(T.TRENDS_OUT / "panel.csv", index=False)
    summary(p).to_csv(T.TRENDS_OUT / "summary_by_geo.csv", index=False)
    T.clean_parcels(T.mvr_muni())[1].to_csv(T.TRENDS_OUT / "parcel_cleaning_log.csv", index=False)
    n = (len(C.state_charts(p)) + len(C.county_grids(p)) + len(C.county_grids(p, C.ACS1_COUNTIES))
         + len(C.county_singles(p)))
    types = TT.summary()
    types.to_csv(T.TRENDS_OUT / "summary_by_muni_type.csv", index=False)
    n += len([C.commitment_growth_by_type(types, d) for d in TT.DIMS])
    muni = TT.trcf_summary("trcf_municipal")
    muni.to_csv(T.TRENDS_OUT / "summary_municipal_appropriations_by_type.csv", index=False)
    n += len([C.municipal_appropriation_growth_by_type(muni, d) for d in TT.DIMS])
    tm = TT.trcf_typed("trcf_municipal")
    C.municipal_appropriation_change_distribution(tm); C.municipal_appropriation_cagr_by_munitype(tm)
    C.municipal_appropriation_cagr_by_munitype(tm, stat="median"); n += 3
    print(f"panel {p.shape}, {n} charts -> {C.CHART_DIR}")
