# Project notes

## Business question

Which Utah counties merit further investigation by a residential construction supplier, and how do market size, recent activity, and housing mix affect that decision?

## Workflow

1. Preserve the annual Census downloads and source fingerprints.
2. Prepare tables with explicit observation levels and stable geographic identifiers.
3. Verify complete county-year coverage, uniqueness, numeric values, and source agreement.
4. Reconcile county measures with separately published state controls.
5. Calculate county metrics using readable SQL and independently check the results in Python.
6. Compare the leading markets, examine alternative ranking measures, and present the tradeoffs.
7. Provide a workbook, charts, query files, and repeatable commands alongside the written findings.

## Spreadsheet issues resolved during development

- The initial county coverage grid contained the year `2020` in the county identifier column. The corrected grid uses the five-digit county identifiers from the reference table.
- Filling an Excel structured reference horizontally shifted the source columns. The corrected formulas lock their source columns or use fixed ranges, while allowing the county row and year header to change deliberately.
- The yearly validation summary originally counted six passing years. The final check explicitly compares that count with the six expected years to produce a meaningful pass/fail result.
- Source comparison checks use preserved original Census values. Repeating the same workbook sum is treated as an arithmetic check rather than independent evidence that the source values were imported correctly.

## Authorship and assistance

This is Ethan Hall's independent portfolio case study using public Census data and a hypothetical business scenario. Initial Excel validation work was completed with guided assistance. AI assistance was used for source preparation, remaining validation, analysis code, workbook formatting, charts, and documentation. The repository provides the underlying code and evidence so the work can be inspected and reproduced. No real supplier engagement or measured business outcome is claimed.

## Review prompts

- What does one row in each table represent, and which join could accidentally multiply a total?
- Why do the checks use a county identifier together with year?
- Why show both absolute and percentage change?
- Why might a market's single-family rank differ from its total-unit rank?
- What additional evidence would be needed before recommending an actual expansion investment?
- How could the 2023 coverage change or a high imputed share affect the interpretation?

