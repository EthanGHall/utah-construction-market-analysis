"""Rebuild the offline Utah BPS portfolio analysis from preserved source files.

Usage: python scripts/analyze.py [--skip-charts]
Python 3.10+; only chart generation needs matplotlib (see requirements.txt).
SQL is executed from sql/*.sql and independently checked against Python results.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from contextlib import closing
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import uuid

BASE = Path(__file__).resolve().parents[1]
REPORTS = BASE / "reports"
YEARS = tuple(range(2020, 2026))
TYPES = ("101", "103", "104", "105")
TEXT_FIELDS = {
    "state_fips", "county_fips", "county_fips5", "county_name", "period_role",
    "coverage_basis", "source_id", "source_file", "state_name", "structure_code",
    "structure_type", "housing_group",
}
RANK_FIELDS = {
    "rank_units_2025": "units_2025",
    "rank_avg_units_2023_2025": "avg_units_2023_2025",
    "rank_avg_units_2021_2025": "avg_units_2021_2025",
    "rank_single_family_2025": "single_family_units_2025",
    "rank_multifamily_2025": "multifamily_units_2025",
    "rank_reported_units_2025": "reported_units_2025",
    "rank_absolute_growth_2024_2025": "absolute_change_2024_2025",
    "rank_pct_growth_2024_2025": "pct_change_2024_2025",
}
CHECKS: list[dict] = []


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check(name, passed, detail, comparisons=None):
    item = {"check": name, "status": "PASS" if passed else "FAIL", "detail": detail,
            "comparisons": comparisons}
    CHECKS.append(item)
    require(passed, f"{name}: {detail}")


def read_csv(path, typed=True):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not typed:
        return rows
    for row in rows:
        for key, value in row.items():
            if key not in TEXT_FIELDS:
                row[key] = None if value == "" else float(value) if key == "imputed_unit_share" else int(value)
    return rows


def write_csv(name, rows, reports=REPORTS):
    require(bool(rows), f"No rows for {name}")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="",
                                         dir=reports, delete=False) as handle:
            temporary = Path(handle.name)
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        temporary.replace(reports / name)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def write_json(name, data, reports=REPORTS):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=reports,
                                         delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(json.dumps(data, indent=2, allow_nan=False) + "\n")
        temporary.replace(reports / name)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def same(a, b):
    if a is None or b is None:
        return a is b
    if isinstance(a, float) or isinstance(b, float):
        return math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)
    return a == b


def hashes(manifest):
    return {m["relative_path"]: hashlib.sha256((BASE / m["relative_path"]).read_bytes()).hexdigest()
            for m in manifest}


def independent_raw_checks(annual, structures, controls, reports=REPORTS):
    """Reparse raw physical lines independently and compare every prepared measure.

    County source positions below are zero-based: 6-17 estimated; 18-29 reported.
    State positions are 5-16 and 17-28; their valuations are rounded thousands.
    This function does not import or call prepare_data.py's parsing functions.
    """
    annual_index = {(r["year"], r["county_fips5"]): r for r in annual}
    structure_index = {(r["year"], r["county_fips5"], r["structure_code"]): r for r in structures}
    state_index = {(r["year"], r["structure_code"]): r for r in controls}
    structure_count = annual_count = control_count = provenance_count = 0
    source_audit, spots, independent_reconciliation = [], [], []
    raw_sums = defaultdict(int)
    for year in YEARS:
        path = f"raw/county/co{year}a.txt"
        lines = (BASE / path).read_text(encoding="utf-8-sig").splitlines()
        for line_number, line in enumerate(lines, 1):
            cells = [c.strip() for c in next(csv.reader([line]))]
            if len(cells) < 2 or cells[1] != "49":
                continue
            require(len(cells) == 30 and int(cells[0]) == year, f"Invalid county raw row {path}:{line_number}")
            fips = cells[1] + cells[2]
            row = annual_index[(year, fips)]
            expected_meta = {"source_file": path, "source_line": line_number,
                             "source_id": f"BPS-CO-{year}", "county_name": cells[5],
                             "state_fips": cells[1], "county_fips": cells[2]}
            for key, value in expected_meta.items():
                require(row[key] == value, f"Annual provenance mismatch {year} {fips} {key}")
                provenance_count += 1
            expected = {
                "single_family_units": int(cells[7]), "two_unit_units": int(cells[10]),
                "three_four_unit_units": int(cells[13]), "five_plus_unit_units": int(cells[16]),
                "total_buildings": sum(int(cells[i]) for i in (6, 9, 12, 15)),
                "total_units": sum(int(cells[i]) for i in (7, 10, 13, 16)),
                "multifamily_units": sum(int(cells[i]) for i in (10, 13, 16)),
                "total_valuation_usd": sum(int(cells[i]) for i in (8, 11, 14, 17)),
                "reported_buildings": sum(int(cells[i]) for i in (18, 21, 24, 27)),
                "reported_units": sum(int(cells[i]) for i in (19, 22, 25, 28)),
                "reported_valuation_usd": sum(int(cells[i]) for i in (20, 23, 26, 29)),
            }
            expected["imputed_units"] = expected["total_units"] - expected["reported_units"]
            expected["imputed_unit_share"] = ratio(expected["imputed_units"], expected["total_units"])
            for key, value in expected.items():
                require(same(row[key], value), f"Raw-to-annual mismatch {year} {fips} {key}")
                annual_count += 1
            for position, code in enumerate(TYPES):
                item = structure_index[(year, fips, code)]
                for key, value in expected_meta.items():
                    require(item[key] == value, f"Structure provenance mismatch {year} {fips} {code} {key}")
                    provenance_count += 1
                for basis, start in (("estimated", 6), ("reported", 18)):
                    for offset, measure in enumerate(("buildings", "units", "valuation_usd")):
                        index = start + position * 3 + offset
                        value, field = int(cells[index]), f"{basis}_{measure}"
                        require(item[field] == value, f"Raw-to-structure mismatch {year} {fips} {code} {field}")
                        structure_count += 1
                        raw_sums[(year, code, field)] += value
                        if year in (2020, 2025) and fips in ("49001", "49049", "49057"):
                            spots.append({"year": year, "county_fips5": fips, "county_name": cells[5],
                                          "structure_code": code, "measure": field, "raw_value": value,
                                          "prepared_value": item[field], "source_file": path,
                                          "source_line": line_number, "source_field_one_based": index + 1,
                                          "status": "PASS"})
            source_audit.append({"year": year, "county_fips5": fips, "county_name": cells[5],
                                 "source_file": path, "source_line": line_number,
                                 "structure_measure_comparisons": 24,
                                 "annual_measure_comparisons": len(expected), "status": "PASS"})
        state_path = f"raw/state/st{year}a.txt"
        state_lines = (BASE / state_path).read_text(encoding="utf-8-sig").splitlines()
        selected = []
        for line_number, line in enumerate(state_lines, 1):
            cells = [c.strip() for c in next(csv.reader([line]))]
            if len(cells) > 1 and cells[1] == "49":
                selected.append((line_number, cells))
        require(len(selected) == 1, f"State row count for {year}")
        line_number, cells = selected[0]
        require(len(cells) == 29 and cells[0] == f"{year}99", f"Invalid state raw row {year}")
        for position, code in enumerate(TYPES):
            item = state_index[(year, code)]
            require(item["source_file"] == state_path and item["source_line"] == line_number,
                    f"State provenance mismatch {year} {code}")
            provenance_count += 2
            for basis, start in (("estimated", 5), ("reported", 17)):
                for offset, measure in enumerate(("buildings", "units", "valuation_thousand_usd")):
                    raw_value = int(cells[start + position * 3 + offset])
                    require(item[f"{basis}_{measure}"] == raw_value, f"State raw value mismatch {year} {code} {basis} {measure}")
                    control_count += 1
                    measure_for_counties = "valuation_usd" if offset == 2 else measure
                    value = raw_value * 1000 if offset == 2 else raw_value
                    if offset == 2:
                        require(item[f"{basis}_valuation_usd"] == value, "State USD conversion mismatch")
                        control_count += 1
                    county_sum = raw_sums[(year, code, f"{basis}_{measure_for_counties}")]
                    tolerance = 500 if offset == 2 else 0
                    require(abs(county_sum - value) <= tolerance, f"Independent state reconciliation {year} {code} {basis} {measure}")
                    independent_reconciliation.append({"year": year, "structure_code": code,
                        "basis": basis, "measure": measure_for_counties, "raw_county_sum": county_sum,
                        "raw_state_value": value, "difference": county_sum - value,
                        "rounding_tolerance": tolerance, "status": "PASS"})
    check("All county structure source measures match", structure_count == 4176,
          "174 raw county rows x 4 structure categories x 6 measures; all values exact", structure_count)
    check("All derived county annual measures match", annual_count == 2262,
          "174 rows x 13 measures independently recomputed from raw lines", annual_count)
    check("All state control measures match", control_count == 192,
          "24 state-category rows x 8 measures including USD conversions", control_count)
    check("Row-level provenance matches raw physical lines", True,
          "County names, codes and source references, plus state source references", provenance_count)
    check("Independent raw county-to-state reconciliation", len(independent_reconciliation) == 144,
          "Counts exact; nominal dollars within $500 per rounded state category", len(independent_reconciliation))
    write_csv("raw_to_prepared_audit.csv", source_audit, reports)
    write_csv("source_spot_checks.csv", spots, reports)
    write_csv("independent_state_reconciliation.csv", independent_reconciliation, reports)
    return {"structure_measures_compared": structure_count, "annual_measures_compared": annual_count,
            "state_control_measures_compared": control_count, "provenance_fields_compared": provenance_count,
            "raw_county_rows_checked": len(source_audit), "source_spot_check_measures": len(spots),
            "independent_state_comparisons": len(independent_reconciliation)}


def build_database(rows):
    database = BASE / "work" / "market_analysis.sqlite"
    database.parent.mkdir(exist_ok=True)
    # Rebuild a generated database only. Never modify the preserved raw files.
    if database.exists():
        database.unlink()
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    connection.executescript((BASE / "sql/00_schema.sql").read_text(encoding="utf-8"))
    fields = list(rows[0])
    connection.executemany(
        f"INSERT INTO county_annual ({','.join(fields)}) VALUES ({','.join('?' for _ in fields)})",
        [tuple(r[k] for k in fields) for r in rows],
    )
    for path in sorted((BASE / "sql").glob("*.sql")):
        if path.name != "00_schema.sql":
            connection.executescript(path.read_text(encoding="utf-8"))
    connection.commit()
    return connection


def query(connection, sql):
    return [dict(r) for r in connection.execute(sql)]


def independent_sql_checks(source, annual_metrics, county_metrics, states, sensitivity):
    """Verify SQL results with direct Python arithmetic and comparison-based ranks."""
    lookup = {(r["year"], r["county_fips5"]): r for r in source}
    totals = {y: sum(r["total_units"] for r in source if r["year"] == y) for y in YEARS}
    count = 0
    for result in annual_metrics:
        y, f = result["year"], result["county_fips5"]
        row = lookup[y, f]
        prior = lookup[y - 1, f]["total_units"] if y > 2020 else None
        expected = {k: row[k] for k in (
            "total_units", "total_buildings", "single_family_units", "multifamily_units",
            "total_valuation_usd", "reported_units", "imputed_units", "imputed_unit_share")}
        expected.update(prior_year_units=prior,
            yoy_units_change=row["total_units"] - prior if prior is not None else None,
            yoy_pct_change=ratio(row["total_units"] - prior, prior) if prior is not None else None,
            state_unit_share=ratio(row["total_units"], totals[y]),
            single_family_share=ratio(row["single_family_units"], row["total_units"]),
            multifamily_share=ratio(row["multifamily_units"], row["total_units"]),
            yoy_crosses_2023_coverage_change=int(y == 2023))
        for key, value in expected.items():
            require(same(result[key], value), f"SQL annual mismatch {y} {f} {key}")
            count += 1
    for result in county_metrics:
        f = result["county_fips5"]
        units = {y: lookup[y, f]["total_units"] for y in YEARS}
        latest = lookup[2025, f]
        expected = {f"units_{y}": units[y] for y in YEARS}
        expected.update(avg_units_2023_2025=sum(units[y] for y in (2023, 2024, 2025)) / 3,
                        avg_units_2021_2025=sum(units[y] for y in range(2021, 2026)) / 5,
                        min_units_2021_2025=min(units[y] for y in range(2021, 2026)),
                        max_units_2021_2025=max(units[y] for y in range(2021, 2026)))
        for baseline in (2020, 2023, 2024):
            expected[f"absolute_change_{baseline}_2025"] = units[2025] - units[baseline]
            expected[f"pct_change_{baseline}_2025"] = ratio(units[2025] - units[baseline], units[baseline])
        expected.update(state_share_2025=ratio(units[2025], totals[2025]),
            single_family_units_2025=latest["single_family_units"],
            multifamily_units_2025=latest["multifamily_units"],
            single_family_share_2025=ratio(latest["single_family_units"], units[2025]),
            multifamily_share_2025=ratio(latest["multifamily_units"], units[2025]),
            imputed_units_2025=units[2025] - latest["reported_units"],
            imputed_share_2025=ratio(units[2025] - latest["reported_units"], units[2025]),
            reported_units_2025=latest["reported_units"], valuation_usd_2025=latest["total_valuation_usd"])
        for key, value in expected.items():
            require(same(result[key], value), f"SQL county mismatch {f} {key}")
            count += 1
        for rank_field, metric in RANK_FIELDS.items():
            value = result[metric]
            expected_rank = 1 + sum(r[metric] is not None and (value is None or r[metric] > value)
                                    for r in county_metrics)
            require(result[rank_field] == expected_rank, f"SQL ranking mismatch {f} {rank_field}")
            count += 1
    for result in states:
        y = result["year"]
        group = [r for r in source if r["year"] == y]
        expected = {k: sum(r[k] for r in group) for k in (
            "total_units", "total_buildings", "single_family_units", "multifamily_units", "reported_units", "imputed_units")}
        expected["valuation_usd"] = sum(r["total_valuation_usd"] for r in group)
        prior = totals.get(y - 1)
        expected.update(prior_year_units=prior,
            yoy_units_change=totals[y] - prior if prior is not None else None,
            yoy_pct_change=ratio(totals[y] - prior, prior) if prior is not None else None,
            single_family_share=ratio(expected["single_family_units"], totals[y]),
            multifamily_share=ratio(expected["multifamily_units"], totals[y]),
            imputed_share=ratio(expected["imputed_units"], totals[y]),
            yoy_crosses_2023_coverage_change=int(y == 2023))
        for key, value in expected.items():
            require(same(result[key], value), f"SQL statewide mismatch {y} {key}")
            count += 1
    scenario_map = {
        "latest_total_units": ("units_2025", "rank_units_2025"),
        "recent_average_units": ("avg_units_2023_2025", "rank_avg_units_2023_2025"),
        "five_year_average_units": ("avg_units_2021_2025", "rank_avg_units_2021_2025"),
        "single_family_units": ("single_family_units_2025", "rank_single_family_2025"),
        "multifamily_units": ("multifamily_units_2025", "rank_multifamily_2025"),
        "reported_only_units": ("reported_units_2025", "rank_reported_units_2025"),
        "absolute_growth_2024_2025": ("absolute_change_2024_2025", "rank_absolute_growth_2024_2025"),
        "percent_growth_2024_2025": ("pct_change_2024_2025", "rank_pct_growth_2024_2025"),
    }
    county_index = {r["county_fips5"]: r for r in county_metrics}
    for row in sensitivity:
        metric, rank_field = scenario_map[row["scenario"]]
        county = county_index[row["county_fips5"]]
        require(same(row["metric_value"], county[metric]) and row["metric_rank"] == county[rank_field]
                and row["top_three_in_scenario"] == int(county[rank_field] <= 3), "Sensitivity mismatch")
        count += 3
    check("SQL measures and ranks match independent Python", True,
          "All annual, county, statewide and sensitivity numeric results; relative/absolute tolerance 1e-12", count)
    # Test actual SQL behavior for zero baselines and duplicate keys in isolation.
    fixture = sqlite3.connect(":memory:")
    fixture.executescript((BASE / "sql/00_schema.sql").read_text(encoding="utf-8"))
    fields = list(source[0])
    a, b = dict(source[0]), dict(source[0])
    for row, year, unit_count in ((a, 2020, 0), (b, 2021, 12)):
        row.update(year=year, single_family_units=unit_count, two_unit_units=0,
            three_four_unit_units=0, five_plus_unit_units=0, total_buildings=unit_count,
            total_units=unit_count, multifamily_units=0, reported_units=unit_count,
            imputed_units=0, imputed_unit_share=0.0 if unit_count else None,
            period_role="baseline" if year == 2020 else "analysis")
    statement = f"INSERT INTO county_annual ({','.join(fields)}) VALUES ({','.join('?' for _ in fields)})"
    fixture.executemany(statement, [tuple(r[k] for k in fields) for r in (a, b)])
    fixture.executescript((BASE / "sql/01_annual_metrics.sql").read_text(encoding="utf-8"))
    zero_case = fixture.execute("SELECT prior_year_units,yoy_units_change,yoy_pct_change FROM annual_metrics WHERE year=2021").fetchone()
    check("Zero growth baseline yields NULL percentage", zero_case == (0, 12, None),
          "Actual SQL fixture: zero to twelve units retains +12 and returns NULL percent", 1)
    duplicate_rejected = False
    try:
        fixture.execute(statement, tuple(a[k] for k in fields))
    except sqlite3.IntegrityError:
        duplicate_rejected = True
    check("Database rejects duplicate county-year input", duplicate_rejected,
          "Actual primary-key constraint tested using a disposable in-memory database", 1)
    fixture.close()
    return count


def summary_data(metrics, states, sensitivity, raw_quality, source_count):
    shortlist = [dict(r) for r in metrics[:3]]
    rationales = {
        "49049": ("Largest 2025 unit market and strongest single-family unit volume in this dataset.",
                  "2025 volume remains below 2020; investigate builders, competition and service costs before committing."),
        "49035": ("Second-largest 2025 unit market; highest multifamily unit volume supports a multifamily-focused sales investigation.",
                  "Multifamily-heavy activity can be concentrated in large projects; permits do not measure realized purchases."),
        "49053": ("Third-largest 2025 unit market; single-family-heavy mix offers a different customer focus.",
                  "2025 units fell from 2024; this is a scale-based candidate rather than a growth leader."),
    }
    for row in shortlist:
        row["rationale"], row["caution"] = rationales.get(row["county_fips5"],
            ("Top-three 2025 estimated housing-unit market under the stated screen.",
             "Investigate customer demand, competition and operating costs before committing."))
    scenario_names = sorted({r["scenario"] for r in sensitivity})
    scenario_summary = []
    for name in scenario_names:
        leaders = [r for r in sensitivity if r["scenario"] == name and r["top_three_in_scenario"]]
        scenario_summary.append({"scenario": name, "top_three": leaders,
                                 "same_counties_as_primary_shortlist": {r["county_fips5"] for r in leaders} == {r["county_fips5"] for r in shortlist}})
    latest, baseline = states[-1], states[0]
    return {
        "schema_version": "1.0",
        "analysis_date": "2026-10-04",
        "scope": {"analysis_years": [2021, 2022, 2023, 2024, 2025], "baseline_year": 2020,
                  "counties": 29, "county_year_rows": 174, "structure_rows": 696,
                  "snapshot_retrieval_date": "2026-10-01", "source": "U.S. Census Bureau Building Permits Survey",
                  "scenario": "Hypothetical residential construction supplier screening county sales markets for further investigation",
                  "selection_rule": "Top three counties by 2025 estimated authorized housing units; compare alternative objectives separately",
                  "percent_storage": "All percentages are fractions: 0.10 means 10%"},
        "statewide": states,
        "headlines": {"units_2025": latest["total_units"], "yoy_units_change": latest["yoy_units_change"],
                      "yoy_pct_change": latest["yoy_pct_change"],
                      "pct_change_2020_2025": ratio(latest["total_units"] - baseline["total_units"], baseline["total_units"]),
                      "shortlist_units_2025": sum(r["units_2025"] for r in shortlist),
                      "shortlist_state_share_2025": sum(r["units_2025"] for r in shortlist) / latest["total_units"],
                      "imputed_share_2025": latest["imputed_share"]},
        "shortlist": shortlist,
        "sensitivity": scenario_summary,
        "quality": {**raw_quality, "downloaded_source_files": source_count,
                    "original_preparation_checks_passed": 19, "original_preparation_checks_total": 19,
                    "analysis_checks_passed": sum(r["status"] == "PASS" for r in CHECKS),
                    "analysis_checks_total": len(CHECKS),
                    "performed_by": "Automated Python and SQL validation"},
        "limitations": [
            "Permits authorize construction; they are not completed homes, supplier sales, revenue or profit.",
            "The survey changed from a fixed 2014 permit-office universe to annual updates starting in 2023. Changes crossing that break combine market and coverage effects; even later comparisons are not a constant-office panel.",
            "County totals include Census imputation. Imputed-unit share is not a response rate, confidence interval or error estimate.",
            "Permit valuations are nominal dollars and reflect housing mix and estimated costs; they are not inflation-adjusted market growth.",
            "The hypothetical supplier's products, customers, locations, competition and costs are unspecified. The shortlist screens sales markets and does not justify a branch opening or estimate ROI.",
            "Only six annual observations are available. Growth is descriptive and small baselines can create large percentage changes; no causal model or forecast is fitted.",
        ],
        "figures": ["reports/figures/market_size.png", "reports/figures/shortlist_trends.png", "reports/figures/housing_mix.png"],
    }


def plot_charts(metrics, summary, reports=REPORTS):
    try:
        import matplotlib
    except ImportError as exc:
        raise SystemExit("Charts require matplotlib. Install requirements.txt, or use --skip-charts for SQL and validation only.") from exc
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter, MultipleLocator, PercentFormatter
    out = reports / "figures"
    out.mkdir(exist_ok=True)
    navy, teal, orange = "#183B56", "#007F86", "#C26B26"
    gray, ink = "#B8C7D0", "#243746"
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11,
        "axes.edgecolor": "#CED6DE", "axes.labelcolor": ink, "text.color": ink,
        "xtick.color": ink, "ytick.color": ink, "axes.spines.top": False,
        "axes.spines.right": False, "axes.spines.left": False, "axes.spines.bottom": False,
        "figure.facecolor": "#FFFFFF", "axes.facecolor": "#FFFFFF", "savefig.facecolor": "#FFFFFF"})
    colors = {r["county_fips5"]: c for r, c in zip(summary["shortlist"], (navy, teal, orange))}
    def finish(fig, ax, title, subtitle, footer, filename, left=0.18, top=0.83, title_y=0.945):
        fig.text(left, title_y, title, fontsize=20, fontweight="bold", ha="left")
        fig.text(left, title_y - 0.049, subtitle, fontsize=11, color="#5A6C7A", ha="left")
        fig.text(left, 0.045, footer, fontsize=9, color="#5A6C7A", ha="left", linespacing=1.5)
        ax.set_axisbelow(True)
        fig.subplots_adjust(left=left, right=0.96, top=top, bottom=0.19)
        fig.savefig(out / filename, dpi=180)
        plt.close(fig)
    top = metrics[:10]
    fig, ax = plt.subplots(figsize=(11.5, 7.5))
    positions = list(range(len(top)))
    bars = ax.barh(positions, [r["units_2025"] for r in top], height=0.63,
                   color=[colors.get(r["county_fips5"], gray) for r in top])
    ax.set_yticks(positions, [r["county_name"].replace(" County", "") for r in top])
    ax.invert_yaxis()
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, p: f"{x:,.0f}"))
    ax.xaxis.set_major_locator(MultipleLocator(2000))
    ax.set_xlim(0, max(r["units_2025"] for r in top) * 1.19)
    ax.grid(axis="x", color="#E9EEF2")
    ax.tick_params(axis="both", length=0)
    ax.set_xlabel("Housing units authorized in 2025", labelpad=12)
    for bar, r in zip(bars, top):
        ax.text(bar.get_width() + 100, bar.get_y() + bar.get_height() / 2,
                f"{r['units_2025']:,}", va="center", fontsize=11, fontweight="bold")
    finish(fig, ax, f"Three counties account for {summary['headlines']['shortlist_state_share_2025']:.1%} of Utah units",
           "Top 10 counties by estimated housing units authorized, 2025",
           "Source: U.S. Census Bureau, Building Permits Survey. Snapshot: October 1, 2026.\nEstimated totals include imputation. Permits are authorizations, not completed construction or sales.",
           "market_size.png")
    fig, ax = plt.subplots(figsize=(11.5, 7.5))
    for r in summary["shortlist"]:
        values = [r[f"units_{y}"] for y in YEARS]
        ax.plot(YEARS, values, color=colors[r["county_fips5"]], linewidth=2.8, marker="o", markersize=6,
                label=r["county_name"].replace(" County", ""))
    ax.axvspan(2019.75, 2020.22, color="#F2F4F6", zorder=0)
    ax.axvline(2022.5, linestyle=(0, (4, 4)), color="#8E9AA5", linewidth=1.2)
    ax.text(2022.57, 0.97, "2023 coverage change", transform=ax.get_xaxis_transform(), fontsize=9, va="top", color="#5A6C7A")
    ax.set_xticks(YEARS, ["2020\nBaseline", "2021", "2022", "2023", "2024", "2025"])
    ax.set_xlim(2019.8, 2025.18)
    ax.set_ylim(0, max(r[f"units_{y}"] for r in summary["shortlist"] for y in YEARS) * 1.18)
    ax.set_ylabel("Housing units authorized", labelpad=12)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, p: f"{x:,.0f}"))
    ax.grid(axis="y", color="#E9EEF2")
    ax.tick_params(axis="both", length=0, pad=9)
    ax.legend(loc="lower left", frameon=False, ncol=3, bbox_to_anchor=(0, 1.02))
    finish(fig, ax, "Scale and growth tell different stories",
           "Annual estimated units for the three largest 2025 county markets",
           "Source: U.S. Census Bureau, Building Permits Survey. 2021–2025 analysis; 2020 baseline.\nFrom 2023 the permit-office universe updates annually. Cross-break changes are not purely market growth.",
           "shortlist_trends.png", left=0.12, top=0.76, title_y=0.915)
    fig, ax = plt.subplots(figsize=(11.5, 6.5))
    selected = summary["shortlist"]
    positions = list(range(3))
    sf = [r["single_family_share_2025"] for r in selected]
    mf = [r["multifamily_share_2025"] for r in selected]
    ax.barh(positions, sf, color=navy, height=0.54, label="Single-family units")
    ax.barh(positions, mf, left=sf, color=teal, height=0.54, label="Multifamily units (2+)")
    ax.set_yticks(positions, [r["county_name"].replace(" County", "") for r in selected])
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.xaxis.set_major_formatter(PercentFormatter(1))
    ax.set_xlabel("Share of estimated housing units authorized in 2025", labelpad=12)
    ax.tick_params(axis="both", length=0, pad=9)
    for index, r in enumerate(selected):
        ax.text(sf[index] / 2, index, f"{sf[index]:.1%}\n{r['single_family_units_2025']:,} units",
                ha="center", va="center", color="white", fontsize=11, fontweight="bold")
        ax.text(sf[index] + mf[index] / 2, index, f"{mf[index]:.1%}\n{r['multifamily_units_2025']:,} units",
                ha="center", va="center", color="white", fontsize=10, fontweight="bold")
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.02), ncol=2, frameon=False)
    finish(fig, ax, "Housing mix changes the sales conversation",
           "Salt Lake is multifamily-heavy; Washington is predominantly single-family",
           "Source: U.S. Census Bureau, Building Permits Survey. Unit shares, not building shares.\nSingle-family includes qualifying attached homes. Housing mix alone does not identify supplier spending.",
           "housing_mix.png", top=0.76)


def run_analysis(args, reports):
    """Build and validate a run in a private directory before publication."""
    manifest = json.loads((BASE / "sources/download_manifest.json").read_text(encoding="utf-8"))
    before = hashes(manifest)
    check("Preserved sources match download checksums", all(before[m["relative_path"]] == m["sha256"] for m in manifest),
          f"All {len(manifest)} downloaded raw and documentation files checked against the original manifest", len(manifest))
    subprocess.run([sys.executable, str(BASE / "scripts/prepare_data.py")], cwd=BASE, check=True, capture_output=True, text=True)
    preparation = json.loads((BASE / "data/validation_summary.json").read_text(encoding="utf-8"))
    check("Original preparation checks pass", preparation["checks_passed"] == preparation["checks_total"],
          f"{preparation['checks_passed']}/{preparation['checks_total']} original checks; details in data/validation_results.csv", preparation["checks_total"])
    annual = read_csv(BASE / "data/county_annual.csv")
    structures = read_csv(BASE / "data/county_by_structure.csv")
    controls = read_csv(BASE / "data/utah_state_controls.csv")
    keys = {(r["year"], r["county_fips5"]) for r in annual}
    roster = read_csv(BASE / "data/counties.csv")
    counties = {r["county_fips5"] for r in roster}
    raw_roster = set()
    with (BASE / "raw/county/co2025a.txt").open(encoding="utf-8-sig", newline="") as handle:
        for source_row in csv.reader(handle):
            cells = [c.strip() for c in source_row]
            if len(cells) > 1 and cells[1] == "49":
                raw_roster.add((cells[1], cells[2], cells[1] + cells[2], cells[5]))
    roster_values = {(r["state_fips"], r["county_fips"], r["county_fips5"], r["county_name"]) for r in roster}
    check("Complete county-year panel", len(annual) == len(keys) == 174
          and len(roster) == len(counties) == len(raw_roster) == 29 and roster_values == raw_roster
          and keys == {(y, f) for y in YEARS for f in counties},
          "29-county lookup roster matches the 2025 raw source; all six years contain exactly that roster", len(keys))
    structure_keys = {(r["year"], r["county_fips5"], r["structure_code"]) for r in structures}
    check("Complete county-year-structure panel", len(structures) == len(structure_keys) == 696
          and structure_keys == {(y, f, t) for y, f in keys for t in TYPES}, "174 county-year keys x 4 types", len(structure_keys))
    raw_quality = independent_raw_checks(annual, structures, controls, reports)
    with closing(build_database(annual)) as connection:
        metrics = query(connection, "SELECT * FROM county_metrics ORDER BY units_2025 DESC, county_fips5")
        annual_metrics = query(connection, "SELECT * FROM annual_metrics ORDER BY year, county_fips5")
        states = query(connection, "SELECT * FROM statewide_trends ORDER BY year")
        sensitivity = query(connection, "SELECT * FROM ranking_sensitivity ORDER BY scenario, metric_rank, county_fips5")
    write_csv("county_metrics.csv", metrics, reports)
    write_csv("annual_metrics.csv", annual_metrics, reports)
    write_csv("statewide_trends.csv", states, reports)
    write_csv("ranking_sensitivity.csv", sensitivity, reports)
    selected = {r["county_fips5"] for r in metrics[:3]}
    write_csv("shortlist_trends.csv", [r for r in annual_metrics if r["county_fips5"] in selected], reports)
    sql_comparisons = independent_sql_checks(annual, annual_metrics, metrics, states, sensitivity)
    raw_quality["sql_python_numeric_comparisons"] = sql_comparisons
    check("Annual market shares reconcile", all(math.isclose(sum(r["state_unit_share"] for r in annual_metrics if r["year"] == y), 1.0) for y in YEARS), "County unit shares sum to 100% in each year", len(YEARS))
    check("2020 kept outside analysis averages", all(r["period_role"] == ("baseline" if r["year"] == 2020 else "analysis") for r in annual), "145 analysis records plus 29 baseline records; averages independently verified", len(annual))
    check("Source files unchanged after full rebuild", before == hashes(manifest), "Before/after SHA-256 comparison of every preserved source", len(manifest))
    summary = summary_data(metrics, states, sensitivity, raw_quality, len(manifest))
    summary["quality"]["original_preparation_checks_passed"] = preparation["checks_passed"]
    summary["quality"]["original_preparation_checks_total"] = preparation["checks_total"]
    write_json("analysis_summary.json", summary, reports)
    write_csv("analysis_validation.csv", CHECKS, reports)
    if not args.skip_charts:
        plot_charts(metrics, summary, reports)
    return summary, {"status": "PASS", "county_rows": len(annual), "structure_rows": len(structures),
                     "shortlist": [r["county_name"] for r in metrics[:3]],
                     "checks_passed": len(CHECKS), "sql_python_comparisons": sql_comparisons,
                     "charts_generated": not args.skip_charts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-charts", action="store_true", help="Run data, SQL and checks using only the standard library")
    args = parser.parse_args()
    REPORTS.mkdir(exist_ok=True)
    CHECKS.clear()
    run = {"id": uuid.uuid4().hex, "started_at_utc": datetime.now(timezone.utc).isoformat(),
           "charts_requested": not args.skip_charts}
    try:
        # Invalidate the prior success before any source/preparation work starts.
        write_json("validation_summary.json", {"status": "RUNNING", "run": run, "checks": []})
        write_csv("analysis_validation.csv", [{"check": "Analysis run", "status": "RUNNING",
                  "detail": "Validation is in progress; retained reports belong to the previous successful run.",
                  "comparisons": None}])
        work = BASE / "work"
        work.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="analysis-", dir=work) as directory:
            staged = Path(directory)
            summary, result = run_analysis(args, staged)
            # Only validated reports reach the public directory. Workbook reports
            # are separate artifacts and are not part of this publication.
            for path in sorted(staged.rglob("*")):
                if path.is_file():
                    destination = REPORTS / path.relative_to(staged)
                    destination.parent.mkdir(exist_ok=True, parents=True)
                    path.replace(destination)
        run["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        # PASS is the final publication step, including requested chart generation.
        write_json("validation_summary.json", {"status": "PASS", "run": run,
                   "quality": summary["quality"], "checks": CHECKS})
    except (Exception, KeyboardInterrupt, SystemExit) as exc:
        detail = f"{type(exc).__name__}: {exc}"
        if isinstance(exc, subprocess.CalledProcessError):
            detail += "\n" + (exc.stderr or exc.stdout or "").strip()
        if not any(item["status"] == "FAIL" for item in CHECKS):
            CHECKS.append({"check": "Analysis run completed", "status": "FAIL",
                           "detail": detail, "comparisons": None})
        run["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        write_json("validation_summary.json", {"status": "FAIL", "run": run,
                   "error": detail, "checks": CHECKS})
        write_csv("analysis_validation.csv", CHECKS)
        raise
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
