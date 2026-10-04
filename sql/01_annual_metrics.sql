-- Calculate LAG before filtering out 2020, so 2021 retains its growth baseline.
-- NULLIF prevents a zero baseline from becoming an infinite growth rate.
CREATE VIEW annual_metrics AS
WITH lagged AS (
    SELECT *,
           LAG(total_units) OVER (PARTITION BY county_fips5 ORDER BY year) AS prior_year_units,
           SUM(total_units) OVER (PARTITION BY year) AS statewide_units
    FROM county_annual
)
SELECT year, county_fips5, county_name, total_units, total_buildings,
       single_family_units, multifamily_units, total_valuation_usd,
       reported_units, imputed_units, imputed_unit_share,
       prior_year_units,
       total_units - prior_year_units AS yoy_units_change,
       1.0 * (total_units - prior_year_units) / NULLIF(prior_year_units, 0) AS yoy_pct_change,
       1.0 * total_units / NULLIF(statewide_units, 0) AS state_unit_share,
       1.0 * single_family_units / NULLIF(total_units, 0) AS single_family_share,
       1.0 * multifamily_units / NULLIF(total_units, 0) AS multifamily_share,
       CASE WHEN year = 2023 THEN 1 ELSE 0 END AS yoy_crosses_2023_coverage_change,
       period_role, coverage_basis, source_id, source_file, source_line
FROM lagged;
