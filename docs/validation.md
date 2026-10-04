# Validation report

The saved Census snapshot passes **19 preparation checks and 15 analysis checks**. These are automated checks of the data and implementation. They do not imply that permit records are free of reporting error or that authorized projects were completed.

## Results

| Check | Expected | Executed result | Evidence |
| --- | --- | --- | --- |
| County-year uniqueness and coverage | 29 counties × 6 years, one record per combination | 174 unique county-year records; no duplicate or missing combinations | `reports/analysis_validation.csv` |
| Structure coverage | Four categories for every county-year | 696 distinct county-year-category records | `reports/analysis_validation.csv` |
| Analysis period | Five analysis years plus one baseline | 145 analysis records and 29 baseline records | `data/validation_results.csv` |
| Required source measures | Numeric, nonnegative values; explicit handling of missing data | Preparation checks pass; blanks or nonnumeric source measures stop the parser | `scripts/prepare_data.py` |
| Source integrity | Downloaded files unchanged | All 21 source and documentation hashes match the original manifest | `sources/download_manifest.csv` |
| Structure values versus raw downloads | Exact match for every prepared measure | 4,176 numeric comparisons pass | `reports/raw_to_prepared_audit.csv` |
| County annual measures versus raw downloads | Exact independently calculated values | 2,262 numeric comparisons pass | `reports/raw_to_prepared_audit.csv` |
| State controls versus raw downloads | Correct values and thousand-dollar conversion | 192 numeric comparisons pass | `reports/analysis_validation.csv` |
| Row-level provenance | Correct identifiers, labels, source file, and physical line | 5,268 field comparisons pass | `reports/analysis_validation.csv` |
| County totals versus independent state controls | Exact counts; valuation within documented rounding tolerance | All 144 comparisons pass | `reports/independent_state_reconciliation.csv` |
| SQL versus independent Python calculations | Same analytical results | 4,347 numeric comparisons pass | `reports/analysis_validation.csv` |
| Zero growth denominator | Preserve absolute change; percentage unavailable | Tested zero-to-12 fixture returns +12 units and NULL percentage | `reports/analysis_validation.csv` |
| Duplicate input protection | Reject repeated county-year keys | SQLite primary-key constraint rejects the duplicate fixture | `reports/analysis_validation.csv` |
| Annual market shares | County shares sum to 100% in each year | All six years pass | `reports/analysis_validation.csv` |

Comparisons overlap in purpose and are not independent statistical observations. Their counts describe the scope of the audit, rather than a confidence level.

## Trace a record

The [source comparison table](../reports/source_spot_checks.csv) presents 144 selected numeric comparisons with raw value, prepared value, relative source path, physical line number, and one-based field position. It is an inspectable sample of the full automated raw-source comparison.

For example, the 2020 Beaver County record is at physical line 2675 of `raw/county/co2020a.txt`. The first structure block contains 38 buildings, 38 units, and $11,007,562 valuation for 1-unit buildings. The 3–4-unit block contains one building, four units, and $806,985 valuation. Total authorized units are 42 and total permit valuation is $11,814,547.

These figures illustrate why buildings and housing units must remain separate, and why the source's reported-only block must not be added to the estimate block.

## Reconciliation tolerance

The state files publish valuation rounded to thousands of dollars. Each converted state/category valuation is therefore allowed to differ from its county sum by up to $500. Counts have a tolerance of zero. The [reconciliation file](../reports/independent_state_reconciliation.csv) records each difference and allowed tolerance explicitly.

## Re-run the checks

From the repository root, using Python 3.10 or newer:

```bash
python scripts/analyze.py --skip-charts
```

This command uses the Python standard library, rebuilds prepared data, runs the SQL, and performs the source and analytical checks. It exits with an error on a failed check. Omit `--skip-charts` after installing `requirements.txt` to regenerate the figures as well.

`reports/validation_summary.json` records the latest run's identifier, UTC timestamps, and status: `RUNNING`, `FAIL`, or `PASS`. A run marks itself `RUNNING` before checking sources or preparing data. Analytical reports and requested figures are built in a temporary directory and published only after validation and chart generation succeed; `PASS` is written last. A source, preparation, SQL, or chart failure records `FAIL` and its error in the validation files while retaining the previous analytical reports and figures. Prepared files under `data/` are rebuilt by the preparation step and are not covered by this report-publication safeguard. Use `scripts/analyze.py` as the entry point for a validated rebuild.

The failure-and-recovery regression checks run in disposable repository copies:

```bash
python -m unittest discover -s tests -v
```

The final Excel workbook includes its own visible validation evidence. Source audits and pipeline results are retained separately, so a displayed workbook status can be traced to actual calculations and source records.

## Saved Excel workbook

The [workbook verification results](../reports/workbook_validation.json) record its SHA-256 and confirm that all 11,682 reference value cells were preserved, 609 county comparison metrics match the independent analysis, and all 12 visible validation checks pass. The saved file contains no formula errors. Input-change, blank-input, and duplicate-key tests passed in the artifact calculation engine; native Microsoft Excel recalculation was not exercised.

To inspect the saved workbook independently of the builder, install the optional verification dependency and run:

```bash
python -m pip install openpyxl
python scripts/verify_workbook.py
```

To rebuild the workbook in an environment that provides Codex's `@oai/artifact-tool` package, first run the analysis workflow, then:

```bash
python scripts/prepare_workbook_inputs.py
node scripts/build_workbook.mjs
python scripts/verify_workbook.py
```

The builder imports the preserved reference workbook, restores live formulas for derived annual measures, and creates the presentation and validation sheets. The three derived columns retain their original numeric results. The original learner workbook is preserved outside this repository.

