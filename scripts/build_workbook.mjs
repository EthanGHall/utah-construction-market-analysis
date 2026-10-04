/**
 * Build the portfolio workbook with the OpenAI artifact-tool runtime.
 *
 * Prerequisites: Node.js and @oai/artifact-tool supplied by Codex.
 * Run prepare_workbook_inputs.py first, then run this script from any directory.
 * Data analysis is independently reproducible with the repository's Python/SQL
 * scripts; the optional spreadsheet rendering dependency is not required for it.
 * The reference workbook is imported so its original data, source register,
 * dictionary, formulas and Excel tables remain available in the final artifact.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';

process.on('uncaughtException', error => {
  console.error(error.message);
  console.error(String(error.stack).split('\n').filter(line => line.includes('build_workbook.mjs')).join('\n'));
  process.exit(1);
});

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const input = JSON.parse(await fs.readFile(path.join(root, 'work/workbook_inputs.json'), 'utf8'));
const wb = await SpreadsheetFile.importXlsx(await FileBlob.load(path.join(root, 'data/reference/Utah_Construction_Data.xlsx')));
const navy = '#18364D', blue = '#315D85', muted = '#617486', pale = '#EEF3F7', ink = '#203445';
const amber = '#9A5B16', red = '#A12828', white = '#FFFFFF';
const integer = '#,##0;[Red](#,##0);–';
const percent = '0.0%;[Red](0.0%);–';
const dollars = '$#,##0;[Red]($#,##0);–';
const annual = wb.worksheets.getItem('County annual');
const structures = wb.worksheets.getItem('By structure');
const summary = wb.worksheets.getItem('Start here');
const comparison = wb.worksheets.add('County comparison');
const coverage = wb.worksheets.add('County coverage');
const sourceChecks = wb.worksheets.add('Source comparison');
const stateChecks = wb.worksheets.add('State reconciliation');
const log = wb.worksheets.add('Validation log');

// The source workbook stores these three derived measures as prepared values.
// Retain the learner working copy's correct SUM/IF calculations so category
// changes update analysis. Independent raw controls below still check inputs.
annual.getRange('H6:I6').formulas = [['=SUM(D6:G6)', '=SUM(E6:G6)']];
annual.getRange('H6:I179').fillDown();
annual.getRange('L6').formulas = [['=IF(H6=0,"",(H6-K6)/H6)']];
annual.getRange('L6:L179').fillDown();

function styleRange(sheet, address) {
  sheet.getRange(address).format.font = { name: 'Arial', size: 10, color: ink };
  sheet.getRange(address).format.rowHeight = 21;
  sheet.getRange(address).format.verticalAlignment = 'center';
  sheet.showGridLines = false;
}
function heading(sheet, title, note, end = 'L', lastRow = 40) {
  styleRange(sheet, `A1:${end}${lastRow}`);
  sheet.getRange('A1').values = [[title]];
  sheet.getRange('A1').format.font = { name: 'Arial', size: 16, color: navy, bold: true };
  sheet.getRange('A1').format.rowHeight = 31;
  sheet.getRange('A2').values = [[note]];
  sheet.getRange('A2').format.font = { name: 'Arial', size: 10, color: muted, italic: true };
  sheet.getRange(`A3:${end}3`).format.borders = { bottom: { style: 'thin', color: '#BCD0DF' } };
}
function headers(sheet, address) {
  sheet.getRange(address).format = {
    fill: navy,
    font: { name: 'Arial', size: 10, color: white, bold: true },
    wrapText: true,
    horizontalAlignment: 'center', verticalAlignment: 'center', rowHeight: 37,
    borders: { insideVertical: { style: 'thin', color: white } },
  };
}
function band(sheet, start, end, firstCol, lastCol) {
  for (let row = start; row <= end; row++) if ((row - start) % 2 === 0) {
    sheet.getRange(`${firstCol}${row}:${lastCol}${row}`).format.fill = pale;
  }
}
function failFormat(range, operator, formula) {
  if (typeof formula === 'boolean') formula = formula ? 'TRUE' : 'FALSE';
  range.conditionalFormats.add('cellIs', { operator, formula, format: { fill: '#FCE7E7', font: { color: red, bold: true } } });
}
function column(sheet, col, width, format) {
  sheet.getRange(`${col}1:${col}200`).format.columnWidth = width;
  if (format) sheet.getRange(`${col}6:${col}200`).setNumberFormat(format);
}
function annualSum(sumCol, row, yearCell) {
  return `SUMIFS('County annual'!$${sumCol}$6:$${sumCol}$179,'County annual'!$C$6:$C$179,$A${row},'County annual'!$A$6:$A$179,${yearCell})`;
}
function sourceAnnual(sumCol, row) {
  return `SUMIFS('County annual'!$${sumCol}$6:$${sumCol}$179,'County annual'!$C$6:$C$179,$C${row},'County annual'!$A$6:$A$179,$A${row})`;
}

// Preserve the source data and supplied correct calculations. Add the learner's
// duplicate-key check as a live calculated column in the existing annual table.
annual.getRange('Q5').values = [['Record count']];
annual.getRange('Q6').formulas = [['=COUNTIFS($A$6:$A$179,A6,$C$6:$C$179,C6)']];
annual.getRange('Q6:Q179').fillDown();
const annualTableName = annual.tables.items[0].name;
annual.tables.items[0].delete();
const annualTable = annual.tables.add('A5:Q179', true, annualTableName);
annualTable.style = 'TableStyleMedium2';
annual.getRange('Q5:Q179').format.columnWidth = 13;
annual.getRange('Q6:Q179').setNumberFormat('0');
failFormat(annual.getRange('Q6:Q179'), 'notEqual', 1);
for (const s of [annual, structures, wb.worksheets.getItem('Sources'), wb.worksheets.getItem('Dictionary')]) {
  s.freezePanes.unfreeze(); s.freezePanes.freezeRows(5);
}
annual.freezePanes.freezeColumns(3);
structures.freezePanes.freezeColumns(3);

// County comparison: all metrics are live formulas over the original data.
const latestRaw = input.raw_counties.filter(r => r.year === 2025)
  .sort((a, b) => b.units.reduce((x, y) => x + y) - a.units.reduce((x, y) => x + y) || a.county_fips5.localeCompare(b.county_fips5));
heading(comparison, 'County comparison', 'Residential units authorized. Initially sorted by 2025 units; use the table filters to explore other measures.', 'W', 42);
comparison.getRange('A5:W5').values = [[
  'County FIPS', 'County', 2020, 2021, 2022, 2023, 2024, 2025,
  '2023–25 avg units', '2025 change units', '2025 change %', '2025 state share',
  '2025 single-family share', '2025 multifamily share', '2025 imputed share',
  '2025 valuation USD', '2025 volume rank', '3-year avg rank', '2021–25 avg units',
  '5-year avg rank', '2025 reported units', 'Reported-only rank', '2023–25 change %',
]];
comparison.getRange('A6:B34').values = latestRaw.map(r => [r.county_fips5, r.county_name]);
const compFormulas = latestRaw.map((_, index) => {
  const r = index + 6;
  return [
    ...['C', 'D', 'E', 'F', 'G', 'H'].map(c => `=${annualSum('H', r, `${c}$5`)}`),
    `=AVERAGE(F${r}:H${r})`, `=H${r}-G${r}`, `=IF(G${r}=0,"n.a.",H${r}/G${r}-1)`,
    `=H${r}/$H$36`, `=IF(H${r}=0,"n.a.",${annualSum('D', r, '$H$5')}/H${r})`,
    `=IF(H${r}=0,"n.a.",1-M${r})`, `=IF(H${r}=0,"n.a.",(H${r}-U${r})/H${r})`,
    `=${annualSum('J', r, '$H$5')}`, `=RANK(H${r},$H$6:$H$34,0)`,
    `=RANK(I${r},$I$6:$I$34,0)`, `=AVERAGE(D${r}:H${r})`, `=RANK(S${r},$S$6:$S$34,0)`,
    `=${annualSum('K', r, '$H$5')}`, `=RANK(U${r},$U$6:$U$34,0)`, `=IF(F${r}=0,"n.a.",H${r}/F${r}-1)`,
  ];
});
comparison.getRange('C6:W34').formulas = compFormulas;
comparison.getRange('A36:B36').values = [['49', 'Utah statewide']];
comparison.getRange('C36:W36').formulas = [[
  ...['C', 'D', 'E', 'F', 'G', 'H'].map(c => `=SUM(${c}6:${c}34)`),
  '=AVERAGE(F36:H36)', '=H36-G36', '=H36/G36-1', '=1',
  '=SUMIFS(\'County annual\'!$D$6:$D$179,\'County annual\'!$A$6:$A$179,H$5)/H36',
  '=1-M36', '=(H36-U36)/H36', '=SUM(P6:P34)', '', '', '=AVERAGE(D36:H36)', '', '=SUM(U6:U34)', '', '=H36/F36-1',
]];
comparison.getRange('A39').values = [['Growth spanning 2022–2023 also reflects Census survey-coverage changes. Prefer 2023–2025 comparisons for the recent view.']];
comparison.getRange('A40').values = [['Imputed share = (estimated units − reported units) / estimated units. Reported-only ranks are a sensitivity check, not a superior estimate.']];
comparison.getRange('A39:A40').format.font = { name: 'Arial', size: 10, italic: true, color: muted };
comparison.tables.add('A5:W34', true, 'CountyComparisonTable').style = 'TableStyleMedium2';
headers(comparison, 'A5:W5');
comparison.getRange('A36:W36').format.fill = '#DFE9F1';
comparison.getRange('A36:W36').format.font = { name: 'Arial', size: 10, bold: true, color: navy };
for (const c of ['C', 'D', 'E', 'F', 'G', 'H', 'J', 'U']) column(comparison, c, 13, integer);
for (const c of ['I', 'S']) column(comparison, c, 16, '#,##0.0');
for (const c of ['K', 'L', 'M', 'N', 'O', 'W']) column(comparison, c, 16, percent);
for (const c of ['Q', 'R', 'T', 'V']) column(comparison, c, 13, '0');
column(comparison, 'A', 12, '@'); column(comparison, 'B', 24); column(comparison, 'P', 21, dollars);
comparison.freezePanes.freezeRows(5); comparison.freezePanes.freezeColumns(2);
comparison.tabColor = blue;

// Completeness is tested against the separate expected county roster.
heading(coverage, 'County-year coverage', 'Each expected county-year must occur exactly once. Zero means missing; more than one means duplicate.', 'I', 39);
coverage.getRange('A5:I5').values = [['County FIPS', 'County', 2020, 2021, 2022, 2023, 2024, 2025, 'Years present once']];
coverage.getRange('A6:B34').values = input.roster.map(r => [r.county_fips5, r.county_name]);
coverage.getRange('C6').formulas = [["=COUNTIFS('County annual'!$C$6:$C$179,$A6,'County annual'!$A$6:$A$179,C$5)"]];
coverage.getRange('C6:H6').fillRight(); coverage.getRange('C6:H34').fillDown();
coverage.getRange('I6').formulas = [['=COUNTIFS(C6:H6,1)']]; coverage.getRange('I6:I34').fillDown();
coverage.getRange('B36').values = [['Expected pairs present once']];
coverage.getRange('C36').formulas = [['=COUNTIFS(C6:H34,1)']];
coverage.getRange('B37').values = [['Expected total']]; coverage.getRange('C37').values = [[174]];
coverage.getRange('B39').values = [['Roster source: data/counties.csv; five-digit county FIPS codes are text identifiers.']];
coverage.getRange('B39').format.font = { name: 'Arial', size: 10, color: muted, italic: true };
headers(coverage, 'A5:I5'); band(coverage, 6, 34, 'A', 'I');
column(coverage, 'A', 13, '@'); column(coverage, 'B', 28);
for (const c of ['C', 'D', 'E', 'F', 'G', 'H']) column(coverage, c, 10, '0');
column(coverage, 'I', 19, '0');
coverage.getRange('C6:I34').format.horizontalAlignment = 'center';
failFormat(coverage.getRange('C6:H34'), 'notEqual', 1);
failFormat(coverage.getRange('I6:I34'), 'notEqual', 6);
coverage.freezePanes.freezeRows(5);

// Each raw source line is parsed independently of the prepared CSVs/workbook.
heading(sourceChecks, 'Source comparison', 'All 174 county-years are traced to unchanged Census files. Four housing categories, total units, valuation and reported units are compared.', 'U', 181);
sourceChecks.getRange('A5:U5').values = [[
  'Year', 'County', 'County FIPS', 'Raw 1-unit', 'Raw 2-unit', 'Raw 3–4-unit', 'Raw 5+ units',
  'Raw total units', 'Workbook total units', 'Unit difference', 'Raw valuation USD',
  'Workbook valuation USD', 'Value difference', 'Raw reported units', 'Workbook reported units',
  'Reported difference', 'Category mismatches', 'All match', 'Source ID', 'Source file', 'Source line',
]];
sourceChecks.getRange('A6:G179').values = input.raw_counties.map(r => [r.year, r.county_name, r.county_fips5, ...r.units]);
sourceChecks.getRange('K6:K179').values = input.raw_counties.map(r => [r.valuation_usd]);
sourceChecks.getRange('N6:N179').values = input.raw_counties.map(r => [r.reported_units]);
sourceChecks.getRange('S6:U179').values = input.raw_counties.map(r => [r.source_id, r.source_file, r.source_line]);
for (let r = 6; r <= 179; r++) {
  sourceChecks.getRange(`H${r}:J${r}`).formulas = [[`=SUM(D${r}:G${r})`, `=${sourceAnnual('H', r)}`, `=I${r}-H${r}`]];
  sourceChecks.getRange(`L${r}:M${r}`).formulas = [[`=${sourceAnnual('J', r)}`, `=L${r}-K${r}`]];
  sourceChecks.getRange(`O${r}:R${r}`).formulas = [[
    `=${sourceAnnual('K', r)}`, `=O${r}-N${r}`,
    `=${['D', 'E', 'F', 'G'].map(c => `IF(${sourceAnnual(c, r)}=${c}${r},0,1)`).join('+')}`,
    `=IF(AND(J${r}=0,M${r}=0,P${r}=0,Q${r}=0),"Match","Mismatch")`,
  ]];
}
sourceChecks.tables.add('A5:U179', true, 'SourceComparisonTable').style = 'TableStyleMedium2';
headers(sourceChecks, 'A5:U5');
column(sourceChecks, 'A', 9, '0'); column(sourceChecks, 'B', 24); column(sourceChecks, 'C', 13, '@');
for (const c of ['D', 'E', 'F', 'G', 'H', 'I', 'J', 'N', 'O', 'P', 'Q']) column(sourceChecks, c, 16, integer);
for (const c of ['K', 'L', 'M']) column(sourceChecks, c, 21, dollars);
column(sourceChecks, 'R', 12); column(sourceChecks, 'S', 17); column(sourceChecks, 'T', 31); column(sourceChecks, 'U', 12, '0');
for (const c of ['J', 'M', 'P', 'Q']) failFormat(sourceChecks.getRange(`${c}6:${c}179`), 'notEqual', 0);
sourceChecks.freezePanes.freezeRows(5); sourceChecks.freezePanes.freezeColumns(3);

heading(stateChecks, 'County-to-state reconciliation', '144 independent comparisons. State-file valuations are multiplied by 1,000; rounding tolerance is $500 per category.', 'L', 152);
stateChecks.getRange('A5:L5').values = [['Year', 'Structure type', 'Basis', 'Measure', 'County sum', 'State control', 'Difference', 'Tolerance', 'Within tolerance', 'Source ID', 'Source line', 'Source file']];
const structureCols = { estimated: { buildings: 'E', units: 'F', valuation_usd: 'G' }, reported: { buildings: 'I', units: 'H', valuation_usd: 'J' } };
input.state_controls.forEach((c, i) => {
  const r = i + 6, sc = structureCols[c.basis][c.measure];
  stateChecks.getRange(`A${r}:D${r}`).values = [[c.year, c.structure_type, c.basis, c.measure]];
  stateChecks.getRange(`E${r}`).formulas = [[`=SUMIFS('By structure'!$${sc}$6:$${sc}$701,'By structure'!$A$6:$A$701,A${r},'By structure'!$D$6:$D$701,B${r})`]];
  stateChecks.getRange(`F${r}`).values = [[c.state_value]];
  stateChecks.getRange(`G${r}`).formulas = [[`=E${r}-F${r}`]];
  stateChecks.getRange(`H${r}`).values = [[c.tolerance]];
  stateChecks.getRange(`I${r}`).formulas = [[`=IF(ABS(G${r})<=H${r},"Pass","Check")`]];
  stateChecks.getRange(`J${r}:L${r}`).values = [[c.source_id, c.source_line, c.source_file]];
});
stateChecks.tables.add('A5:L149', true, 'StateReconciliationTable').style = 'TableStyleMedium2';
headers(stateChecks, 'A5:L5');
column(stateChecks, 'A', 9, '0'); column(stateChecks, 'B', 16); column(stateChecks, 'C', 14); column(stateChecks, 'D', 18);
for (const c of ['E', 'F']) column(stateChecks, c, 19, integer);
for (const c of ['G', 'H']) column(stateChecks, c, 14, integer);
column(stateChecks, 'I', 17); column(stateChecks, 'J', 17); column(stateChecks, 'K', 12, '0'); column(stateChecks, 'L', 30);
failFormat(stateChecks.getRange('I6:I149'), 'equal', '"Check"');
stateChecks.freezePanes.freezeRows(5);

// Checks are terminal: no analysis or output references these results.
heading(log, 'Validation log', 'Validation completed October 4, 2026. Formula results remain linked to the workbook inputs and independent source controls.', 'H', 28);
log.getRange('A5:E5').values = [['Check', 'Expected', 'Actual', 'Pass', 'Evidence / interpretation']];
const checks = [
  ['Total county-year records', 174, "=COUNTA('County annual'!B6:B179)", 'Annual data has 29 counties × 6 years.'],
  ['Unique county-year records', 174, "=COUNTIFS('County annual'!Q6:Q179,1)", 'Each row must have exactly one matching year/FIPS key.'],
  ['Years with 29 records', 6, '=COUNTIFS(H6:H11,29)', 'Annual counts are shown at right.'],
  ['Expected county-years present once', 174, "=COUNTIFS('County coverage'!C6:H34,1)", 'Compared with the separate county FIPS roster.'],
  ['Blank year / county / FIPS cells', 0, "=COUNTBLANK('County annual'!A6:C179)", 'Blank identifiers would prevent reliable joins.'],
  ['Numeric housing-category inputs', 696, "=COUNT('County annual'!D6:G179)", '174 rows × 4 housing categories.'],
  ['Negative housing-category inputs', 0, "=COUNTIFS('County annual'!D6:G179,\"<0\")", 'Authorized unit counts must be nonnegative.'],
  ['County-years matching source lines', 174, '=COUNTIFS(\'Source comparison\'!R6:R179,"Match")', 'Full comparison, not a sample: four unit categories plus totals, values and reported units.'],
  ['County-to-state controls within tolerance', 144, '=COUNTIFS(\'State reconciliation\'!I6:I149,"Pass")', 'Counts exact; nominal USD differences no larger than $500.'],
  ['Negative structure measures', 0, "=COUNTIFS('By structure'!E6:J701,\"<0\")", 'Estimated and reported buildings, units and values.'],
  ['Numeric structure measures', 4176, "=COUNT('By structure'!E6:J701)", '696 records × 6 numeric measures.'],
  ['Invalid imputed unit shares', 0, "=COUNTIFS('County annual'!L6:L179,\"<0\")+COUNTIFS('County annual'!L6:L179,\">1\")", 'Shares must be between 0% and 100%; blank is allowed when units are zero.'],
];
checks.forEach(([label, expected, formula, note], i) => {
  const r = i + 6;
  log.getRange(`A${r}:B${r}`).values = [[label, expected]];
  log.getRange(`C${r}:D${r}`).formulas = [[formula, `=IF(C${r}=B${r},"Pass","Check")`]];
  log.getRange(`E${r}`).values = [[note]];
});
log.getRange('G5:H5').values = [['Year', 'Records']];
log.getRange('G6:G11').values = [2020, 2021, 2022, 2023, 2024, 2025].map(y => [y]);
log.getRange('H6').formulas = [["=COUNTIFS('County annual'!$A$6:$A$179,G6)"]]; log.getRange('H6:H11').fillDown();
log.getRange('A20').values = [['All workbook checks pass']]; log.getRange('D20').formulas = [['=IF(COUNTIFS(D6:D17,"Pass")=12,"Pass","Check")']];
log.getRange('A23:E24').merge();
log.getRange('A23').values = [['A source match verifies preparation, not whether authorized housing was built. Census estimates include imputation; the survey coverage changed in 2023.']];
log.getRange('A23:E24').format.wrapText = true;
headers(log, 'A5:E5'); headers(log, 'G5:H5'); band(log, 6, 17, 'A', 'E');
column(log, 'A', 39); column(log, 'B', 12, integer); column(log, 'C', 12, integer); column(log, 'D', 11); column(log, 'E', 68); column(log, 'F', 3); column(log, 'G', 10, '0'); column(log, 'H', 12, '0');
log.getRange('E6:E17').format.wrapText = true;
log.getRange('A6:E17').format.rowHeight = 35;
failFormat(log.getRange('D6:D17'), 'equal', '"Check"');
failFormat(log.getRange('D20'), 'equal', '"Check"');
log.freezePanes.freezeRows(5);

// The existing first sheet becomes the concise recruiter-facing analysis view.
summary.getRange('A1:J65').clear({ applyTo: 'all' });
styleRange(summary, 'A1:J65');
summary.getRange('A1:A65').format.columnWidth = 3;
summary.getRange('J1:J65').format.columnWidth = 3;
summary.getRange('B1:B65').format.columnWidth = 26;
summary.getRange('C1:I65').format.columnWidth = 15;
summary.getRange('B2').values = [['Utah residential construction markets']];
summary.getRange('B2').format.font = { name: 'Arial', size: 16, bold: true, color: navy };
summary.getRange('B2').format.rowHeight = 31;
summary.getRange('B3').values = [['County-level expansion screening for a hypothetical construction supplier | October 4, 2026']];
summary.getRange('B3').format.font = { name: 'Arial', size: 10, italic: true, color: muted };
summary.getRange('B4:I4').format.borders = { bottom: { style: 'thin', color: '#BCD0DF' } };
summary.getRange('B6:E6').values = [['Utah statewide', '2023', '2024', '2025']];
headers(summary, 'B6:E6');
summary.getRange('B7:B9').values = [['Authorized units'], ['Multifamily share'], ['Imputed unit share']];
for (let i = 0; i < 3; i++) {
  const dest = ['C', 'D', 'E'][i], origin = ['F', 'G', 'H'][i], year = 2023 + i;
  summary.getRange(`${dest}7`).formulas = [[`='County comparison'!${origin}36`]];
  summary.getRange(`${dest}8`).formulas = [[`=SUMIFS('County annual'!$I$6:$I$179,'County annual'!$A$6:$A$179,${year})/${dest}7`]];
  summary.getRange(`${dest}9`).formulas = [[`=(${dest}7-SUMIFS('County annual'!$K$6:$K$179,'County annual'!$A$6:$A$179,${year}))/${dest}7`]];
}
summary.getRange('C7:E7').setNumberFormat(integer); summary.getRange('C8:E9').setNumberFormat(percent);
summary.getRange('G6:I6').merge(); summary.getRange('G6').values = [['Decision supported']];
summary.getRange('G6:I6').format.font = { name: 'Arial', size: 10, bold: true, color: navy };
summary.getRange('G7:I9').merge();
summary.getRange('G7').values = [['Prioritize market research and builder outreach in Utah, Salt Lake and Washington counties. Facility placement needs additional evidence.']];
summary.getRange('G7:I9').format.wrapText = true;
summary.getRange('B12').values = [['Three markets to investigate']];
summary.getRange('B12').format.font = { name: 'Arial', size: 14, bold: true, color: navy };
summary.getRange('B14:I14').values = [['County', '2025 units', '3-year avg', '2025 change', 'State share', 'Multifamily', 'Imputed', '2025 rank']];
headers(summary, 'B14:I14');
const shortlistNames = ['Utah County', 'Salt Lake County', 'Washington County'];
summary.getRange('B15:B17').values = shortlistNames.map(n => [n]);
const pull = (col, row) => `INDEX('County comparison'!$${col}$6:$${col}$34,MATCH($B${row},'County comparison'!$B$6:$B$34,0))`;
for (let r = 15; r <= 17; r++) {
  summary.getRange(`C${r}:I${r}`).formulas = [[...['H', 'I', 'K', 'L', 'N', 'O', 'Q'].map(c => `=${pull(c, r)}`)]];
}
summary.getRange('C15:C17').setNumberFormat(integer); summary.getRange('D15:D17').setNumberFormat('#,##0.0');
summary.getRange('E15:H17').setNumberFormat(percent); summary.getRange('I15:I17').setNumberFormat('0');
band(summary, 15, 17, 'B', 'I');
summary.getRange('B19:I20').merge();
summary.getRange('B19').values = [['Utah leads 2025 volume; Salt Lake leads the 3-year average. Washington ranks third in both, but its 2025 activity declined. Their different housing mixes call for different builder outreach.']];
summary.getRange('B19:I20').format.wrapText = true;
summary.getRange('B22:I23').merge();
summary.getRange('B22').values = [['The same three counties lead the 3-year average, 5-year average and reported-only checks. Reported-only counts test sensitivity to imputation; they do not replace the official estimates.']];
summary.getRange('B22:I23').format.wrapText = true;
summary.getRange('B22:I23').format.font = { name: 'Arial', size: 10, color: muted };
summary.getRange('B44').values = [['Interpretation and next evidence']];
summary.getRange('B44').format.font = { name: 'Arial', size: 14, bold: true, color: navy };
const notes = [
  'Selection rule: top three counties by 2025 estimated housing units. This is a transparent market screen, not a composite score or a revenue forecast.',
  'Permits authorize new private residential construction. They are not starts, completions, orders or supplier sales. Buildings and housing units are different measures.',
  'Coverage changed in 2023. Longer trends remain useful context, but changes across 2022–2023 are not entirely like-for-like. Dollar valuations are nominal.',
  'Next evidence: supplier product fit, named builder pipelines, competitor locations, delivery times, land/lease costs and customer interviews.',
];
notes.forEach((text, i) => {
  const r = 46 + i * 2;
  summary.getRange(`B${r}:I${r + 1}`).merge(); summary.getRange(`B${r}`).values = [[text]];
  summary.getRange(`B${r}:I${r + 1}`).format.wrapText = true;
});
summary.getRange('B55:E55').values = [['Year', 'Utah County', 'Salt Lake County', 'Washington County']];
headers(summary, 'B55:E55');
summary.getRange('B56:B61').values = [2020, 2021, 2022, 2023, 2024, 2025].map(y => [String(y)]);
for (let r = 56; r <= 61; r++) for (const col of ['C', 'D', 'E']) {
  summary.getRange(`${col}${r}`).formulas = [[`=SUMIFS('County annual'!$H$6:$H$179,'County annual'!$B$6:$B$179,${col}$55,'County annual'!$A$6:$A$179,$B${r})`]];
}
summary.getRange('C56:E61').setNumberFormat(integer);
summary.getRange('G55:I55').merge(); summary.getRange('G55').values = [['Read the supporting sheets']];
summary.getRange('G55:I55').format.font = { name: 'Arial', size: 10, bold: true, color: navy };
summary.getRange('G56:I59').merge(); summary.getRange('G56').values = [['County comparison holds the metrics and alternative rankings. Validation log links the coverage, raw-source and state checks. Sources and Dictionary preserve provenance and definitions.']];
summary.getRange('G56:I59').format.wrapText = true;
summary.getRange('G61:I62').merge(); summary.getRange('G61').values = [['Census Building Permits Survey, 2020–2025. Source snapshots collected October 1, 2026.']];
summary.getRange('G61:I62').format.wrapText = true;
summary.getRange('G61:I62').format.font = { name: 'Arial', size: 10, italic: true, color: muted };
const chart = summary.charts.add('line', summary.getRange('B55:E61'));
chart.title = 'Authorized housing units in the three shortlisted counties';
chart.titleTextStyle.typeface = 'Arial'; chart.titleTextStyle.fontSize = 14;
chart.legend = { position: 'top', textStyle: { typeface: 'Arial', fontSize: 11 } };
chart.xAxis = { axisType: 'textAxis', textStyle: { typeface: 'Arial', fontSize: 11 } };
chart.yAxis = { numberFormatCode: '#,##0', numberFormatSourceLinked: false, textStyle: { typeface: 'Arial', fontSize: 11 } };
chart.setPosition('B26', 'I42');
['#193D55', '#00888E', '#C56F24'].forEach((color, i) => { chart.series.items[i].line = { fill: color, style: 'solid', width: 2 }; chart.series.items[i].fill = color; });
summary.freezePanes.unfreeze(); summary.tabColor = navy;

wb.recalculate();

// Exercise live dependencies in memory, then restore every input before export.
// This verifies the artifact calculation engine; it is not a native Excel test.
const annualKeys = annual.getRange('A6:C179').values;
const testRow = annualKeys.findIndex(r => r[0] === 2025 && r[2] === '49049') + 6;
const testSourceRow = input.raw_counties.findIndex(r => r.year === 2025 && r.county_fips5 === '49049') + 6;
const originalUnits = annual.getRange(`D${testRow}`).values[0][0];
const originalShortlist = summary.getRange('C15').values[0][0];
annual.getRange(`D${testRow}`).values = [[originalUnits + 1]];
wb.recalculate();
assert.equal(summary.getRange('C15').values[0][0], originalShortlist + 1, 'Summary must update after a source-unit edit');
assert.equal(summary.getRange('C61').values[0][0], originalShortlist + 1, 'Chart source must update after a source-unit edit');
assert.equal(sourceChecks.getRange(`R${testSourceRow}`).values[0][0], 'Mismatch', 'Source check must flag an altered input');
assert.equal(log.getRange('D13').values[0][0], 'Check', 'Validation must expose the source mismatch');
annual.getRange(`D${testRow}`).values = [[null]];
wb.recalculate();
assert.equal(log.getRange('C11').values[0][0], 695, 'Numeric input count must flag a blank');
assert.equal(log.getRange('D11').values[0][0], 'Check');
annual.getRange(`D${testRow}`).values = [[originalUnits]];
annual.getRange(`A${testRow}`).values = [[2024]];
wb.recalculate();
assert.equal(annual.getRange(`Q${testRow}`).values[0][0], 2, 'Duplicate-year key must be detected');
assert.equal(log.getRange('C7').values[0][0], 172, 'Both duplicate-key rows must be excluded from the unique count');
assert.equal(log.getRange('C9').values[0][0], 172, 'Missing and duplicate expected county-years must fail coverage');
annual.getRange(`A${testRow}`).values = [[2025]];
wb.recalculate();

// Numerical checks use controls parsed directly from archived raw files.
function close(actual, expected, label) {
  assert.equal(typeof actual, 'number', `${label}: expected numeric result, got ${actual}`);
  assert.ok(Math.abs(actual - expected) < 1e-7, `${label}: ${actual} != ${expected}`);
}
const actualRows = comparison.getRange('A6:W34').values;
for (const row of actualRows) {
  const records = input.raw_counties.filter(r => r.county_fips5 === row[0]).sort((a, b) => a.year - b.year);
  const totals = records.map(r => r.units.reduce((a, b) => a + b, 0));
  totals.forEach((total, i) => close(row[i + 2], total, `${row[1]} ${2020 + i}`));
  close(row[8], totals.slice(3).reduce((a, b) => a + b, 0) / 3, `${row[1]} 3-year mean`);
  close(row[9], totals[5] - totals[4], `${row[1]} absolute change`);
  close(row[15], records[5].valuation_usd, `${row[1]} valuation`);
  close(row[20], records[5].reported_units, `${row[1]} reported units`);
}
assert.ok(coverage.getRange('C6:H34').values.flat().every(v => v === 1), 'Coverage check failed');
assert.ok(sourceChecks.getRange('R6:R179').values.flat().every(v => v === 'Match'), 'Raw source comparison failed');
assert.ok(stateChecks.getRange('I6:I149').values.flat().every(v => v === 'Pass'), 'State reconciliation failed');
if (!log.getRange('D6:D17').values.flat().every(v => v === 'Pass')) console.log(JSON.stringify(log.getRange('A6:D17').values));
assert.ok(log.getRange('D6:D17').values.flat().every(v => v === 'Pass'), 'Validation log failed');
assert.equal(log.getRange('D20').values[0][0], 'Pass');
const errors = await wb.inspect({ kind: 'match', searchTerm: '#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!', options: { useRegex: true, maxResults: 100 }, summary: 'Final workbook error scan' });
await fs.mkdir(path.join(root, 'work/workbook-qa'), { recursive: true });
await fs.writeFile(path.join(root, 'work/workbook-qa/error_scan.ndjson'), errors.ndjson + '\n');
await fs.writeFile(path.join(root, 'work/workbook-qa/checks.json'), JSON.stringify({
  county_years_compared: 174, source_comparisons_passed: 174, state_controls_passed: 144,
  input_change_checks: ['unit edit updates summary/chart and fails source check', 'blank unit input fails numeric completeness', 'duplicate/missing county-year keys fail uniqueness and coverage'],
  coverage_cells: 174, validation_checks_passed: 12, chart_series: chart.series.items.map(s => ({ formula: s.formula, categories: s.categoryFormula })),
}, null, 2) + '\n');

// Render every sheet's principal view plus wide-table right-hand columns.
const previews = [
  ['Start here', 'B2:I42', 'summary'], ['Start here', 'B44:I62', 'method'],
  ['County comparison', 'A1:K18', 'comparison'], ['County comparison', 'L5:W18', 'comparison_mix'],
  ['County coverage', 'A1:I39', 'coverage'], ['Validation log', 'A1:H24', 'validation'],
  ['Source comparison', 'A1:J14', 'source_comparison'], ['Source comparison', 'K5:U14', 'source_comparison_details'],
  ['State reconciliation', 'A1:L15', 'state_reconciliation'],
  ['County annual', 'A1:J13', 'annual'], ['By structure', 'A1:L13', 'structure'],
  ['Sources', 'A1:D12', 'sources'], ['Dictionary', 'A1:F12', 'dictionary'],
];
for (const [sheetName, range, name] of previews) {
  const image = await wb.render({ sheetName, range, scale: 1, format: 'png' });
  await fs.writeFile(path.join(root, `work/workbook-qa/${name}.png`), new Uint8Array(await image.arrayBuffer()));
}
await fs.mkdir(path.join(root, 'outputs'), { recursive: true });
const xlsx = await SpreadsheetFile.exportXlsx(wb);
await xlsx.save(path.join(root, 'outputs/Utah_Construction_Analysis.xlsx'));
console.log('Saved outputs/Utah_Construction_Analysis.xlsx; 174 county controls, 144 state comparisons, and 12 validation checks passed.');
