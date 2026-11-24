# Data sources

Everything in `input/` is committed so the analysis reproduces without downloads or credentials.
The external series in `input/trends/` are a dated snapshot; `input/trends/SNAPSHOT.csv` records
when each was pulled. See the README for when and how the snapshot is updated.

## Maine Revenue Services: Municipal Valuation Return (MVR)

| File | Contents |
|---|---|
| `input/master_mvr_2012_24.csv` | Municipal rows of the MVR, 2012–2024, trimmed to the columns this code reads. Compiled from MVR data provided by Maine Revenue Services. |
| `input/2025 MVR Summary.csv` | The 2025 MVR statistical summary, shared by Maine Revenue Services in October 2026, trimmed to the columns this code reads. The loader reads columns by name, so MRS's full summary file for a later year can be added as it comes. |

The 2025 figures rest on the 2027 State Valuation, which is **preliminary until certified in
February 2027**, so 2025 values may change. County and statewide figures are summed from the
municipal rows; unorganized territories are excluded in every year because they appear in the data
only from 2017. Known data-entry errors are repaired in `lib/trends.py` (`TRCF_FIXES`,
`clean_parcels()`), and every repair is logged to `output/trends/parcel_cleaning_log.csv`.

## External series (`input/trends/`, refreshed by `scripts/trends_pull.py`)

| File | Source | Notes |
|---|---|---|
| `acs1_maine.csv` | U.S. Census Bureau, American Community Survey 1-year: B25077 (median value, owner-occupied) and B25119_002 (median household income, owner-occupied), with margins of error | Maine plus the six counties of 65,000+ people (Androscoggin, Aroostook, Cumberland, Kennebec, Penobscot, York). No 2020 release. Requires a Census API key to re-pull. |
| `cpi_ne_annual.csv`, `cpi_ne_monthly.csv` | BLS Consumer Price Index, Northeast, all items (CUUR0100SA0), via FRED | 2025 averages 11 months: BLS published no October 2025 CPI. |
| `bea_sl_deflator_annual.csv` | BEA implicit price deflator, state and local government consumption expenditures and gross investment (A829RD3A086NBEA), via FRED | National, annual. |
| `fhfa_hpi_at_state.xlsx`, `fhfa_hpi_at_county.xlsx` | Federal Housing Finance Agency, annual all-transactions House Price Index | Repeat-sales index. |
| `zillow_zhvi_maine_monthly.csv` | Zillow Home Value Index (all homes, middle tier, smoothed, seasonally adjusted), Maine and counties | Zillow data, used under Zillow's terms; please credit Zillow when reusing. |
| `redfin_maine_monthly.csv` | Redfin Data Center market tracker, median sale price (all residential, not seasonally adjusted), Maine and counties | Redfin data, used under Redfin's terms; please credit Redfin when reusing. Used from 2016 only, when Redfin's Maine coverage expands sharply. |

## When each source updates

Release timings as checked in November 2026.

| Source | When new data appears | Notes |
|---|---|---|
| MVR (Maine Revenue Services) | Towns file each year's return by 1 November, or 30 days after commitment if later ([2026 MVR instructions](https://www.maine.gov/revenue/sites/maine.gov.revenue/files/inline-files/2026_mvr.instructions_final.pdf)). MRS's [statistical summary](https://www.maine.gov/revenue/taxes/property-tax/municipal-services/valuation-return-statistical-summary) for that year follows the next year: the 2025 summary arrived in October 2026 | A year's figures stay preliminary until the [State Valuation](https://www.maine.gov/revenue/taxes/property-tax/state-valuation) they rest on is certified, before 1 February two years later (February 2027 for 2025) |
| ACS 1-year estimates (Census Bureau) | Once a year, usually mid-September, for the previous calendar year: the 2024 estimates came out on [11 September 2025](https://www.census.gov/newsroom/press-releases/2025/acs-1-year-estimates-embargo.html) | The 2025 estimates were delayed and came out at the end of October 2026 |
| Northeast CPI (BLS) | Monthly, about mid-month for the previous month. The annual average arrives with December's figure in mid-January ([e.g. 15 January 2025](https://www.bls.gov/regions/mid-atlantic/news-release/2025/consumerpriceindex_northeast_20250115.htm)) | The 2025 average covers 11 months (no October 2025 index) |
| State and local government price index (BEA, via FRED) | A year's figure first appears early the following year. BEA revises the past five years each autumn in its annual update ([30 September in 2026](https://bea.gov/index.php/news/blog/2026-08-17/annual-update-gdp-industry-and-state-stats-publicly-available-starting-sept-30)) | National only |
| FHFA annual house price index (state and county) | Once a year; the files in this snapshot say "Last updated: March 31, 2026" and run to 2025 | Developmental index; past values can be revised |
| Zillow Home Value Index | Monthly, on the 16th ([Zillow release calendar](https://www.zillow.com/research/calendar/)) | Zillow re-smooths past values |
| Redfin median sale price | Monthly, around the 8th to 13th of the following month ([Redfin methodology](https://www.redfin.com/news/data-center/methodology/)) | Redfin revises the latest month for about four weeks |

**When to refresh:** once a year, in October or November. By then the previous year's MVR summary
and ACS 1-year estimates are both out, and every other series already covers that year.

## Municipal reference files

| File | Contents |
|---|---|
| `input/municipal_classification.csv` | The municipal typology adopted in the Phase 2 report: size, service-center status and economic type for each of Maine's 494 municipalities and unorganized territories, with 2020 population. Built from public sources; map geometry removed. |
| `input/municipal_key.csv` | One row per place, with a stable `muni_id`, canonical name, county, status and every known spelling. Includes nine former municipalities that deorganized into their county's unorganized territory during 2012–2025, so historical MVR rows still resolve. |
