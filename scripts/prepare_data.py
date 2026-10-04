"""Rebuild this package's CSVs and checks from the preserved Census source files.

Python 3.10+, standard library only. Run from any directory:
    python path/to/utah-construction-data/scripts/prepare_data.py
This performs no downloads and never alters original source files.
"""
from pathlib import Path
from collections import defaultdict
import csv
import hashlib
import json

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / 'data'
DATA.mkdir(exist_ok=True)
YEARS = range(2020, 2026)
TYPES = [('101', '1-unit', 'single_family'), ('103', '2-unit', 'multifamily'),
         ('104', '3-4-unit', 'multifamily'), ('105', '5-plus-unit', 'multifamily')]
manifest = json.loads((BASE / 'sources/download_manifest.json').read_text(encoding='utf-8'))
checks = []

def check(name, passed, detail):
    checks.append(dict(check=name, status='PASS' if passed else 'FAIL', detail=detail))

def write_csv(name, rows):
    assert rows, name
    with (DATA / name).open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

def selected_rows(path, state_index):
    # enumerate physical source lines to retain a direct row-level audit trail.
    with path.open(newline='', encoding='utf-8-sig') as f:
        for line_number, row in enumerate(csv.reader(f), start=1):
            if len(row) > state_index and row[state_index].strip() == '49':
                yield line_number, [cell.strip() for cell in row]

def numbers(cells):
    # Blank/suppressed values must cause an explicit error, never silently become 0.
    return [int(value) for value in cells]

long_rows = []
county_rows = []
state_rows = []
reconciliation = []

for year in YEARS:
    county_file = f'raw/county/co{year}a.txt'
    selected = list(selected_rows(BASE / county_file, 1))
    check(f'{year}: 29 distinct Utah counties', len(selected) == 29 and len({r[2] for _, r in selected}) == 29,
          f'{len(selected)} rows; {len({r[2] for _, r in selected})} distinct county codes')
    for line, row in selected:
        assert len(row) == 30, (year, line, len(row))
        assert row[0] == str(year) and row[1] == '49' and row[3:5] == ['4', '8'], (year, line)
        assert len(row[2]) == 3 and row[2].isdigit(), (year, line)
        est, reported = numbers(row[6:18]), numbers(row[18:30])
        shared = dict(year=year, state_fips=row[1], county_fips=row[2], county_fips5=row[1]+row[2], county_name=row[5])
        period = 'baseline' if year == 2020 else 'analysis'
        coverage = '2014 fixed universe' if year <= 2022 else 'annually updated universe'
        provenance = dict(source_id=f'BPS-CO-{year}', source_file=county_file, source_line=line)
        for j, (code, label, family) in enumerate(TYPES):
            b, u, v = est[j*3:j*3+3]
            rb, ru, rv = reported[j*3:j*3+3]
            long_rows.append(dict(**shared, structure_code=code, structure_type=label, housing_group=family,
                estimated_buildings=b, estimated_units=u, estimated_valuation_usd=v,
                reported_buildings=rb, reported_units=ru, reported_valuation_usd=rv,
                period_role=period, coverage_basis=coverage, **provenance))
        total_units, reported_units = sum(est[1::3]), sum(reported[1::3])
        county_rows.append(dict(**shared,
            single_family_units=est[1], two_unit_units=est[4], three_four_unit_units=est[7], five_plus_unit_units=est[10],
            total_buildings=sum(est[0::3]), total_units=total_units, multifamily_units=sum(est[4::3]),
            total_valuation_usd=sum(est[2::3]), reported_buildings=sum(reported[0::3]), reported_units=reported_units,
            reported_valuation_usd=sum(reported[2::3]), imputed_units=total_units-reported_units,
            imputed_unit_share=(total_units-reported_units)/total_units if total_units else '',
            period_role=period, coverage_basis=coverage, **provenance))

    state_file = f'raw/state/st{year}a.txt'
    state_selected = list(selected_rows(BASE / state_file, 1))
    assert len(state_selected) == 1, (year, 'state row count')
    line, row = state_selected[0]
    assert len(row) == 29 and row[0] == f'{year}99' and row[2:4] == ['4', '8'], (year, row[:5])
    est, reported = numbers(row[5:17]), numbers(row[17:29])
    for j, (code, label, _) in enumerate(TYPES):
        b, u, vk = est[j*3:j*3+3]
        rb, ru, rvk = reported[j*3:j*3+3]
        state_rows.append(dict(year=year, state_fips='49', state_name=row[4], structure_code=code, structure_type=label,
            estimated_buildings=b, estimated_units=u, estimated_valuation_thousand_usd=vk,
            estimated_valuation_usd=vk*1000, reported_buildings=rb, reported_units=ru,
            reported_valuation_thousand_usd=rvk, reported_valuation_usd=rvk*1000,
            source_id=f'BPS-ST-{year}', source_file=state_file, source_line=line))
        matching = [r for r in long_rows if r['year'] == year and r['structure_code'] == code]
        for basis, values in [('estimated', (b,u,vk*1000)), ('reported', (rb,ru,rvk*1000))]:
            for measure, control in zip(['buildings','units','valuation_usd'], values):
                total = sum(r[f'{basis}_{measure}'] for r in matching)
                tolerance = 500 if measure == 'valuation_usd' else 0
                diff = total - control
                reconciliation.append(dict(year=year, structure_code=code, structure_type=label, basis=basis,
                    measure=measure, county_sum=total, state_value=control, county_minus_state=diff,
                    allowed_rounding_difference=tolerance, status='PASS' if abs(diff) <= tolerance else 'FAIL'))

long_rows.sort(key=lambda r: (r['year'], r['county_fips5'], r['structure_code']))
county_rows.sort(key=lambda r: (r['year'], r['county_fips5']))
counties = [{key: r[key] for key in ['state_fips','county_fips','county_fips5','county_name']} for r in county_rows if r['year'] == 2025]
write_csv('county_annual.csv', county_rows)
write_csv('county_by_structure.csv', long_rows)
write_csv('counties.csv', counties)
write_csv('utah_state_controls.csv', state_rows)
write_csv('reconciliation.csv', reconciliation)

check('County-year primary key and count', len(county_rows) == 174 and len({(r['year'],r['county_fips5']) for r in county_rows}) == 174, 'Expected 29 counties x 6 years = 174 rows')
check('Structure primary key and count', len(long_rows) == 696 and len({(r['year'],r['county_fips5'],r['structure_code']) for r in long_rows}) == 696, 'Expected 29 counties x 6 years x 4 types = 696 rows')
check('Five-year analysis row count', sum(r['period_role']=='analysis' for r in county_rows) == 145, '145 analysis rows, with 29 additional 2020 baseline rows')
lookup = {r['county_fips5']:r['county_name'] for r in counties}
check('County identifiers and names stable', all(lookup[r['county_fips5']]==r['county_name'] for r in county_rows), 'All six years match the county lookup')
fields = [f'{basis}_{measure}' for basis in ['estimated','reported'] for measure in ['buildings','units','valuation_usd']]
check('No missing or negative source measures', all(isinstance(r[k],int) and r[k]>=0 for r in long_rows for k in fields), 'Blank or nonnumeric source values cause parsing to stop; zero is retained as zero')
check('Reported measures do not exceed estimates', all(r['reported_'+m] <= r['estimated_'+m] for r in long_rows for m in ['buildings','units','valuation_usd']), 'Estimates include reported values and imputation')
for code, label, _ in TYPES:
    failures=[]
    for r in long_rows:
        if r['structure_code'] != code:
            continue
        for basis in ['estimated','reported']:
            b,u = r[basis+'_buildings'],r[basis+'_units']
            valid = u==b if code=='101' else u==2*b if code=='103' else 3*b<=u<=4*b if code=='104' else u>=5*b
            if not valid:
                failures.append(f"{r['year']} {r['county_name']} {basis}: {b} buildings, {u} units")
    check(f'{label}: units consistent with buildings', not failures, '; '.join(failures) if failures else 'Both estimated and reported fields satisfy structure type bounds')
check('County-to-state reconciliation', all(r['status']=='PASS' for r in reconciliation), f'{len(reconciliation)} comparisons; counts exact, dollar valuations within $500 per rounded state category')
check('Source IDs resolve to manifest', all(r['source_id'] in {m['source_id'] for m in manifest} for r in long_rows+state_rows), 'Each data record links to an original downloaded source')
check('Original download checksums unchanged', all(hashlib.sha256((BASE/m['relative_path']).read_bytes()).hexdigest()==m['sha256'] for m in manifest), f'{len(manifest)} downloaded sources verified with SHA-256')
write_csv('validation_results.csv', checks)

dictionary=[]
def define(dataset, field, datatype, unit, definition, derivation):
    dictionary.append(dict(dataset=dataset, field=field, data_type=datatype, unit=unit, definition=definition, source_or_derivation=derivation))

common={
 'year':('integer','calendar year','Annual period; 2020 is only the growth baseline.','County field 1; state field 1 uses YYYY99.'),
 'state_fips':('text','code','Two-character state identifier; Utah is 49.','County/state field 2.'),
 'county_fips':('text','code','Three-character county identifier; preserve leading zeros.','County field 3.'),
 'county_fips5':('text','code','Five-character unique county identifier.','state_fips + county_fips; primary-key component.'),
 'county_name':('text','name','Census county name, with leading/trailing spaces removed.','County field 6.'),
 'structure_code':('text','code','101 = 1 unit; 103 = 2 units; 104 = 3-4 units; 105 = 5+ units.','C-404 item codes assigned from source column groups.'),
 'structure_type':('text','category','Number of housing units per residential building.','Mapped from structure_code.'),
 'housing_group':('text','category','single_family = code 101; multifamily = codes 103/104/105.','Mapped from structure_code; single family includes qualifying attached homes.'),
 'period_role':('text','category','baseline for 2020; analysis for 2021-2025.','Assigned from year; exclude baseline from five-year averages/rankings.'),
 'coverage_basis':('text','method','Survey permit-office universe used for the annual estimate.','2014 fixed universe through 2022; annually updated from 2023. See DOC-2023-FAQ.'),
 'source_id':('text','key','Join to sources/download_manifest.csv to find URL and retrieval metadata.','Annual county BPS-CO-YYYY or state BPS-ST-YYYY.'),
 'source_file':('text','relative path','Location of unchanged original file inside this package.','raw/county/coYYYYa.txt or raw/state/stYYYYa.txt.'),
 'source_line':('integer','line number','One-based physical source line including header rows.','Recorded while parsing original text file.'),
}
for dataset, rows in [('county_annual',county_rows),('county_by_structure',long_rows),('counties',counties),('utah_state_controls',state_rows)]:
    for field in rows[0]:
        if field in common:
            define(dataset,field,*common[field]); continue
        if field == 'state_name':
            define(dataset,field,'text','name','State name.','State field 5.'); continue
        if dataset == 'county_by_structure':
            basis,measure = field.split('_',1)
            begin = 7 if basis=='estimated' else 19
            offset = {'buildings':0,'units':1,'valuation_usd':2}[measure]
            source_fields = ', '.join(str(begin+offset+3*j) for j in range(4))
            descriptions={'buildings':'Residential buildings authorized; not individual permit-document counts.',
                          'units':'Housing units authorized within residential buildings.',
                          'valuation_usd':'Permit valuation in whole nominal U.S. dollars; not sales, profit, or inflation-adjusted cost.'}
            definition=descriptions[measure]+(' Includes reported data and Census imputation.' if basis=='estimated' else ' Reported-only data; excludes Census imputation.')
            define(dataset,field,'integer','USD' if measure=='valuation_usd' else 'count',definition,f'County fields {source_fields}, respectively for codes 101/103/104/105.'); continue
        if dataset == 'county_annual':
            mapping={
              'single_family_units':('count','Units in 1-unit buildings, including qualifying attached homes.','county_by_structure estimated_units for 101.'),
              'two_unit_units':('count','Units in 2-unit buildings.','county_by_structure estimated_units for 103.'),
              'three_four_unit_units':('count','Units in 3-4-unit buildings.','county_by_structure estimated_units for 104.'),
              'five_plus_unit_units':('count','Units in buildings containing at least 5 units.','county_by_structure estimated_units for 105.'),
              'total_buildings':('count','Total estimated residential buildings authorized.','Sum estimated_buildings across all four structure types.'),
              'total_units':('count','Total estimated housing units authorized; includes imputation.','Sum estimated_units across all four structure types.'),
              'multifamily_units':('count','Estimated units in structures containing two or more units.','two_unit_units + three_four_unit_units + five_plus_unit_units.'),
              'total_valuation_usd':('USD','Total estimated nominal permit valuation.','Sum estimated_valuation_usd across all four structure types.'),
              'reported_buildings':('count','Reported-only residential buildings authorized.','Sum reported_buildings across all four structure types.'),
              'reported_units':('count','Reported-only housing units authorized.','Sum reported_units across all four structure types.'),
              'reported_valuation_usd':('USD','Reported-only nominal permit valuation.','Sum reported_valuation_usd across all four structure types.'),
              'imputed_units':('count','Units added through Census imputation.','total_units - reported_units.'),
              'imputed_unit_share':('proportion 0-1','Share of estimated units contributed by imputation; not an office response rate or confidence score.','imputed_units / total_units; blank if total_units is zero.'),
            }
            unit,definition,derivation=mapping[field]
            define(dataset,field,'decimal / nullable' if field=='imputed_unit_share' else 'integer',unit,definition,derivation); continue
        if dataset == 'utah_state_controls':
            basis,measure = field.split('_',1)
            start = 6 if basis=='estimated' else 18
            if measure == 'valuation_usd':
                define(dataset,field,'integer','USD',f'{basis.title()} state valuation converted from rounded thousands; a reconciliation control.',f'{basis}_valuation_thousand_usd * 1000.'); continue
            offset = {'buildings':0,'units':1,'valuation_thousand_usd':2}[measure]
            source_fields=', '.join(str(start+offset+3*j) for j in range(4))
            define(dataset,field,'integer','thousand USD' if measure=='valuation_thousand_usd' else 'count',
                   f'{basis.title()} state {measure.replace("_", " ")}; separate state-file control.',f'State fields {source_fields}, respectively for codes 101/103/104/105.'); continue
        raise ValueError((dataset,field))
write_csv('data_dictionary.csv',dictionary)

summary=dict(county_rows=len(county_rows), structure_rows=len(long_rows), counties=len(counties),
             source_files=len(manifest), checks_passed=sum(c['status']=='PASS' for c in checks),
             checks_total=len(checks), reconciliation_comparisons=len(reconciliation),
             annual_totals=[dict(year=y, units=sum(r['total_units'] for r in county_rows if r['year']==y),
                                 valuation_usd=sum(r['total_valuation_usd'] for r in county_rows if r['year']==y)) for y in YEARS])
(DATA / 'validation_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps(summary,indent=2))
if any(c['status']=='FAIL' for c in checks):
    print(json.dumps([c for c in checks if c['status']=='FAIL'],indent=2))
    raise SystemExit(1)
