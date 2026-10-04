"""Prepare independent raw-file controls for the optional Excel builder.

Run from any directory: python scripts/prepare_workbook_inputs.py
The final workbook is authored by build_workbook.mjs, not this script.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TYPES = ["1-unit", "2-unit", "3-4-unit", "5-plus-unit"]


def records(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def main():
    roster = records(ROOT / "data/counties.csv")
    controls, state = [], []
    for year in range(2020, 2026):
        relative = f"raw/county/co{year}a.txt"
        for line_number, text in enumerate((ROOT / relative).read_text().splitlines(), 1):
            fields = next(csv.reader([text]))
            if len(fields) < 30 or fields[1].strip() != "49":
                continue
            if int(fields[0][:4]) != year:
                raise ValueError(f"Year mismatch in {relative}:{line_number}")
            numbers = [int(value.strip()) for value in fields[6:30]]
            controls.append({
                "year": year, "county_fips5": fields[1].strip() + fields[2].strip().zfill(3),
                "county_name": fields[5].strip(),
                "units": [numbers[i] for i in (1, 4, 7, 10)],
                "valuation_usd": sum(numbers[i] for i in (2, 5, 8, 11)),
                "reported_units": sum(numbers[i] for i in (13, 16, 19, 22)),
                "source_id": f"BPS-CO-{year}", "source_file": relative,
                "source_line": line_number,
            })
        relative = f"raw/state/st{year}a.txt"
        matched = 0
        for line_number, text in enumerate((ROOT / relative).read_text().splitlines(), 1):
            fields = next(csv.reader([text]))
            if len(fields) < 29 or fields[1].strip() != "49":
                continue
            if int(fields[0][:4]) != year:
                raise ValueError(f"Year mismatch in {relative}:{line_number}")
            matched += 1
            numbers = [int(value.strip()) for value in fields[5:29]]
            for type_index, structure_type in enumerate(TYPES):
                for basis_index, basis in enumerate(("estimated", "reported")):
                    for measure_index, measure in enumerate(("buildings", "units", "valuation_usd")):
                        source_value = numbers[basis_index * 12 + type_index * 3 + measure_index]
                        state.append({
                            "year": year, "structure_type": structure_type, "basis": basis,
                            "measure": measure,
                            "state_value": source_value * (1000 if measure_index == 2 else 1),
                            "tolerance": 500 if measure_index == 2 else 0,
                            "source_id": f"BPS-ST-{year}", "source_line": line_number,
                            "source_file": relative,
                        })
        if matched != 1:
            raise ValueError(f"Expected one Utah state row in {relative}, found {matched}")
    expected = {(year, row["county_fips5"]) for year in range(2020, 2026) for row in roster}
    observed = [(row["year"], row["county_fips5"]) for row in controls]
    if len(observed) != 174 or set(observed) != expected:
        raise ValueError("Raw county records do not contain exactly the expected county-years")
    out = ROOT / "work/workbook_inputs.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"roster": roster, "raw_counties": controls, "state_controls": state}, indent=2) + "\n")
    print("Prepared 174 independent county controls and 144 state comparisons.")


if __name__ == "__main__":
    main()
