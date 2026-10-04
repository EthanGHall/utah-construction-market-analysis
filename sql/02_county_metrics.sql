-- No composite score. Each rank answers a separately labeled business question.
-- Long-run change is descriptive and crosses the 2023 coverage change.
CREATE VIEW county_metrics AS
WITH periods AS (
    SELECT county_fips5,
           MAX(CASE WHEN year = 2020 THEN total_units END) AS units_2020,
           MAX(CASE WHEN year = 2021 THEN total_units END) AS units_2021,
           MAX(CASE WHEN year = 2022 THEN total_units END) AS units_2022,
           MAX(CASE WHEN year = 2023 THEN total_units END) AS units_2023,
           MAX(CASE WHEN year = 2024 THEN total_units END) AS units_2024,
           MAX(CASE WHEN year = 2025 THEN total_units END) AS units_2025,
           AVG(CASE WHEN year BETWEEN 2023 AND 2025 THEN total_units END) AS avg_units_2023_2025,
           AVG(CASE WHEN year BETWEEN 2021 AND 2025 THEN total_units END) AS avg_units_2021_2025,
           MIN(CASE WHEN year BETWEEN 2021 AND 2025 THEN total_units END) AS min_units_2021_2025,
           MAX(CASE WHEN year BETWEEN 2021 AND 2025 THEN total_units END) AS max_units_2021_2025
    FROM county_annual
    GROUP BY county_fips5
), metrics AS (
    SELECT a.county_fips5, a.county_name,
           p.units_2020, p.units_2021, p.units_2022, p.units_2023, p.units_2024, p.units_2025,
           p.avg_units_2023_2025, p.avg_units_2021_2025,
           p.min_units_2021_2025, p.max_units_2021_2025,
           a.yoy_units_change AS absolute_change_2024_2025,
           a.yoy_pct_change AS pct_change_2024_2025,
           p.units_2025 - p.units_2023 AS absolute_change_2023_2025,
           1.0 * (p.units_2025 - p.units_2023) / NULLIF(p.units_2023, 0) AS pct_change_2023_2025,
           p.units_2025 - p.units_2020 AS absolute_change_2020_2025,
           1.0 * (p.units_2025 - p.units_2020) / NULLIF(p.units_2020, 0) AS pct_change_2020_2025,
           a.state_unit_share AS state_share_2025,
           a.single_family_units AS single_family_units_2025,
           a.multifamily_units AS multifamily_units_2025,
           a.single_family_share AS single_family_share_2025,
           a.multifamily_share AS multifamily_share_2025,
           a.imputed_units AS imputed_units_2025,
           a.imputed_unit_share AS imputed_share_2025,
           a.reported_units AS reported_units_2025,
           a.total_valuation_usd AS valuation_usd_2025
    FROM annual_metrics a
    JOIN periods p USING (county_fips5)
    WHERE a.year = 2025
)
SELECT *,
       RANK() OVER (ORDER BY units_2025 DESC) AS rank_units_2025,
       RANK() OVER (ORDER BY avg_units_2023_2025 DESC) AS rank_avg_units_2023_2025,
       RANK() OVER (ORDER BY avg_units_2021_2025 DESC) AS rank_avg_units_2021_2025,
       RANK() OVER (ORDER BY single_family_units_2025 DESC) AS rank_single_family_2025,
       RANK() OVER (ORDER BY multifamily_units_2025 DESC) AS rank_multifamily_2025,
       RANK() OVER (ORDER BY reported_units_2025 DESC) AS rank_reported_units_2025,
       RANK() OVER (ORDER BY absolute_change_2024_2025 DESC) AS rank_absolute_growth_2024_2025,
       RANK() OVER (ORDER BY pct_change_2024_2025 DESC) AS rank_pct_growth_2024_2025
FROM metrics;
