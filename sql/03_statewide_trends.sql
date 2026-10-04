-- Aggregate counts first, then divide. Averaging county percentages is incorrect.
CREATE VIEW statewide_trends AS
WITH totals AS (
    SELECT year, SUM(total_units) AS total_units,
           SUM(total_buildings) AS total_buildings,
           SUM(single_family_units) AS single_family_units,
           SUM(multifamily_units) AS multifamily_units,
           SUM(total_valuation_usd) AS valuation_usd,
           SUM(reported_units) AS reported_units,
           SUM(imputed_units) AS imputed_units
    FROM county_annual
    GROUP BY year
), lagged AS (
    SELECT *, LAG(total_units) OVER (ORDER BY year) AS prior_year_units
    FROM totals
)
SELECT *,
       total_units - prior_year_units AS yoy_units_change,
       1.0 * (total_units - prior_year_units) / NULLIF(prior_year_units, 0) AS yoy_pct_change,
       1.0 * single_family_units / NULLIF(total_units, 0) AS single_family_share,
       1.0 * multifamily_units / NULLIF(total_units, 0) AS multifamily_share,
       1.0 * imputed_units / NULLIF(total_units, 0) AS imputed_share,
       CASE WHEN year = 2023 THEN 1 ELSE 0 END AS yoy_crosses_2023_coverage_change
FROM lagged;
