-- Alternative objectives can change the shortlist. Reported-only is a
-- sensitivity comparison, NOT a replacement for Census estimated totals.
CREATE VIEW ranking_sensitivity AS
WITH scenarios AS (
    SELECT 'latest_total_units' AS scenario, county_fips5, county_name,
           units_2025 AS metric_value, rank_units_2025 AS metric_rank FROM county_metrics
    UNION ALL
    SELECT 'recent_average_units', county_fips5, county_name,
           avg_units_2023_2025, rank_avg_units_2023_2025 FROM county_metrics
    UNION ALL
    SELECT 'five_year_average_units', county_fips5, county_name,
           avg_units_2021_2025, rank_avg_units_2021_2025 FROM county_metrics
    UNION ALL
    SELECT 'single_family_units', county_fips5, county_name,
           single_family_units_2025, rank_single_family_2025 FROM county_metrics
    UNION ALL
    SELECT 'multifamily_units', county_fips5, county_name,
           multifamily_units_2025, rank_multifamily_2025 FROM county_metrics
    UNION ALL
    SELECT 'reported_only_units', county_fips5, county_name,
           reported_units_2025, rank_reported_units_2025 FROM county_metrics
    UNION ALL
    SELECT 'absolute_growth_2024_2025', county_fips5, county_name,
           absolute_change_2024_2025, rank_absolute_growth_2024_2025 FROM county_metrics
    UNION ALL
    SELECT 'percent_growth_2024_2025', county_fips5, county_name,
           pct_change_2024_2025, rank_pct_growth_2024_2025 FROM county_metrics
)
SELECT *, CASE WHEN metric_rank <= 3 THEN 1 ELSE 0 END AS top_three_in_scenario
FROM scenarios;
