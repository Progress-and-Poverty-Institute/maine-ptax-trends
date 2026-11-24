# Maine Property Tax Trends, 2012–2025

Code and data behind [*Trends Over Time in County & Statewide Property Tax Burdens*](https://legislature.maine.gov/doc/12793)
(final report, 3 November 2026), prepared by the Progress and Poverty Institute and the Center for
Land Economics for Maine's Real Estate Property Tax Relief Task Force (Phase 3, Proposal 1).

The report looks at how property taxes in Maine have changed since 2012, both in dollars and
compared to incomes and property values. Results cover Maine statewide and its 16 counties.

## Quick start

Requires Python 3.10 or later.

```bash
pip install -r requirements.txt
python scripts/trends_build.py      # rebuilds output/trends/ from the committed data
python -m pytest tests/             # runs the checks (names, town types, data repairs)
```

These commands reproduce the report's figures. The data in `input/` is committed, so the
build runs offline and needs no credentials.

## Producing the charts

`trends_build.py` takes about 45 seconds and writes 159 PNG charts to `output/trends/charts/`:

- `state/`: the eight statewide charts
- `county/`: the same eight charts for each county, plus grids that compare counties side by side
- `types/`: growth by type of municipality

To change how a chart looks, edit its function in `lib/trends_charts.py` and run the build again,
or use the notebook below.

## Stepping through the analysis

To see each table and chart as it is made, open the notebook from the repository folder:

```bash
jupyter lab 40-time-trends.ipynb
```

Run the cells in order. The notebook builds the panel, shows the data checks, then draws the
state, county and town-type charts one at a time, saving each to `output/trends/charts/` as the
build does. Change `geo` in the "One county" section to see any county. Edits to
`lib/trends_charts.py` take effect when you re-run a chart's cell, with no restart.

## Refreshing the data (optional)

To pull newer data from the original sources:

1. **Get a free Census API key** at https://api.census.gov/data/key_signup.html.
2. **Copy `.env.example` to `.env`** and paste your key after `CENSUS_API_KEY=`.
   `.env` is ignored by git, so your key stays on your machine.
3. **Pull, then rebuild:**
   ```bash
   python scripts/trends_pull.py            # every source
   python scripts/trends_pull.py acs cpi    # or just some: acs cpi bea zillow redfin fhfa
   python scripts/trends_build.py
   ```

Only the ACS pull needs the key. The other sources are public downloads.

## About the committed data snapshot

`input/trends/` holds each external series as it stood when we last pulled it. We commit these
files because several sources revise past years (FHFA and BEA restate them, Zillow re-smooths its
series), and the committed copy lets anyone reproduce the published report exactly.

- `input/trends/SNAPSHOT.csv` records the date each source was last pulled.
  `trends_pull.py` updates it automatically.
- We update the snapshot only when we re-pull a source and commit the result, for
  example to add a newly released year. Each such commit says which sources changed
  and why. If you re-pull yourself, expect small differences from the report where a source has
  revised its history.

**Main sources, and when each releases new data:**

- **Municipal Valuation Return** (Maine Revenue Services): towns file each year's return by
  1 November, and MRS's statistical summary follows the next year. Figures stay preliminary until
  the State Valuation they rest on is certified, two Februaries later.
- **ACS 1-year estimates** (Census Bureau): once a year, usually mid-September, for the previous year.
- **Northeast CPI** (BLS): monthly; the annual average arrives with December's figure in mid-January.
- **State and local government price index** (BEA): annual, revised every autumn.
- **FHFA house price index**: annual state and county files, updated around the end of March.
- **Zillow** and **Redfin**: monthly, Zillow on the 16th and Redfin around the 8th to 13th.

**When to refresh:** once a year, in October or November. By then the previous year's MVR summary
and ACS 1-year estimates are both out, and every other series already covers that year.

See [`docs/data-sources.md`](docs/data-sources.md) for every source, its terms, its caveats and its
release calendar.

## Repository layout

`lib/` holds the functions for loading, cleaning, calculating and charting. `scripts/` holds the
commands you run, which call those functions in order and write the results. `tests/` checks that
the functions still give the expected results; run them with `python -m pytest tests/`.

| Path | What it is |
|---|---|
| `lib/trends.py` | Loads the MVR 2012–2025, repairs data-entry errors, aggregates to county and state, merges the external series, derives tax bills and burdens |
| `lib/trends_charts.py` | One function per chart |
| `lib/trends_types.py` | Growth in the property tax commitment by type of municipality (size, service-center status, economic type), and growth in municipal appropriations by type, 2022–2025 |
| `lib/munikey.py` | Resolves any spelling of a Maine municipality to one ID |
| `scripts/trends_pull.py` | Downloads the external series into `input/trends/` |
| `scripts/trends_build.py` | Writes `output/trends/`: `panel.csv`, `summary_by_geo.csv`, `summary_by_muni_type.csv`, `summary_municipal_appropriations_by_type.csv`, the parcel-repair log and every chart |
| `40-time-trends.ipynb` | Interactive notebook for exploring and restyling the charts |
| `input/` | Committed data (see `docs/data-sources.md`) |
| `tests/` | Checks on the municipal name key, the municipal-type grouping and the data repairs (e.g. Sanford's 2022 education figures) |

`output/` is not committed; `trends_build.py` regenerates it.

## Municipal names

Sources spell the same town differently ("Presque Is." / "Presque Isle", "St. John Plt" /
"Saint John Plantation", "Aroostook - Unorganized" / "AROOSTOOK UT"). `lib/munikey.py` and
`input/municipal_key.csv` map every spelling to a single `muni_id`. The tests check that every
municipal row in the MVR from 2012 to 2025 resolves to exactly one ID. If the test fails, it will
print the unrecognised spelling. Add the spelling to the `aliases` column of the key.

## Licence

The code is released under the [MIT License](LICENSE). The data in `input/` is not covered by
that licence: each source keeps its own terms, set out in [`docs/data-sources.md`](docs/data-sources.md).

## Credits

Prepared by Stephen Hoskins (Progress and Poverty Institute) and Greg Miller (Center for Land
Economics). Municipal Valuation Return data courtesy of Maine Revenue Services.
