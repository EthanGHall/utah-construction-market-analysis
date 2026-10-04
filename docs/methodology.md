# Methodology

## Decision and scope

This case study screens Utah counties for a hypothetical residential construction supplier's market research. The deliverable is a shortlist for investigation. Selecting an actual branch location would also require customer interviews, competitor coverage, delivery costs, product demand, and operating economics.

The analysis covers 2021–2025. The 2020 observations provide the prior year for 2021 growth calculations and context in trend charts. They are excluded from five-year analysis totals and recent three-year averages.

## Source and observation level

The source is the U.S. Census Bureau's [Building Permits Survey](https://www.census.gov/construction/bps/about.html), using the final annual county and state files downloaded on October 1, 2026. The download manifest records each original URL, retrieval time, relative path, and SHA-256 fingerprint. Rebuilding uses the preserved snapshot without downloading revised files.

| Table | One row represents | Rows |
| --- | --- | ---: |
| `data/county_annual.csv` | One Utah county in one calendar year | 174 |
| `data/county_by_structure.csv` | One county, year, and structure category | 696 |
| `data/counties.csv` | One county and its identifiers | 29 |
| `data/utah_state_controls.csv` | One year and structure category for Utah | 24 |

County identifiers are five-character strings composed of state FIPS and county FIPS. Analytical joins use identifiers and years. Names are display labels. Joining county totals directly to all four structure rows without controlling the observation level would multiply the county totals.

## Measures and calculations

| Measure | Calculation | Interpretation |
| --- | --- | --- |
| Authorized units | Sum of units in all four structure categories | Residential activity indicated by permits |
| Recent annual average | Sum of 2023, 2024, and 2025 units divided by three | Recent scale with less dependence on one year |
| Annual unit change | Current year units minus prior year units | Absolute increase or decrease |
| Annual percentage change | Annual unit change divided by prior year units | Relative change; unavailable when prior units are zero |
| Utah share | County units divided by all Utah county units in the same year | Share of statewide permitted housing units |
| Multifamily share | Units in 2-, 3–4-, and 5+ unit buildings divided by total units | Housing mix relevant to customer segmentation |
| Imputed unit share | Estimated units less reported units, divided by estimated units | Portion of the published estimate supplied through imputation |
| Permit valuation | Sum of estimated valuation across structure types | Nominal value recorded for the permitted structures |

Ratios are computed from matching numerators and denominators. Statewide shares use statewide sums, rather than averages of county percentages. A zero denominator is recorded as unavailable. A missing source value causes validation to fail rather than becoming zero.

## Screening approach

The primary screen ranks 2025 authorized housing units. The three-year average, housing mix, year-over-year changes, and imputed share provide context and challenge the initial choices. The sensitivity analysis compares rankings under alternative volume measures, including single-family units. No composite score, causal model, or revenue forecast is used.

This approach fits a general supplier screening exercise. A supplier specializing in single-family homebuilders could reasonably select a different shortlist from a supplier focused on multifamily developments. Changes under those alternatives are reported rather than concealed behind a single score.

## Source handling and validation

Original downloads remain unchanged under `raw/` and `sources/`. `scripts/prepare_data.py` extracts state FIPS `49`, converts numeric fields explicitly, creates the county and structure tables, and reconciles county sums with separately published state controls.

The county files publish valuation in dollars; state files publish valuation in thousands of dollars. State amounts are multiplied by 1,000 before comparison. Buildings and units must match exactly. Each state/category valuation can differ by up to $500 because the state amount is rounded to thousands. This tolerance is applied to individual category comparisons, not used to excuse count differences.

The analysis pipeline adds independent source comparisons, key and coverage checks, and SQL-versus-Python comparisons. Read the [validation report](validation.md) for the executed results and scope of each check.

## Interpretation limits

1. **Authorizations:** A permit is an authorization. It does not establish when a project started or whether it was completed. Housing units and buildings are separate measures, and neither is a count of permit documents. See the [Census definitions](https://www.census.gov/construction/bps/definitions.html).
2. **Coverage change:** Beginning in 2023, Census moved from a fixed 2014 permit-office universe to an annually updated universe. Changes across 2022–2023 can reflect coverage as well as activity. Long-term trends are descriptive and carry that qualification. See the [2023 methodology FAQ](https://www.census.gov/construction/pdf/bps_2023_faqs.pdf).
3. **Imputation:** Estimated totals already include reported activity and Census imputations. The reported and estimated blocks must not be added together. Imputed share is not a confidence interval or an office response rate.
4. **Valuation:** Dollar values are nominal, without inflation adjustment. They are permit valuations, not supplier sales, profit, or a verified measure of construction spending. Changes may reflect prices and housing mix as well as volume.
5. **Decision coverage:** Annual county data does not identify individual customers, current competitors, travel time, monthly seasonality, commercial projects, or local profitability. The shortlist supports further research.

