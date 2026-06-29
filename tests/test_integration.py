import pytest
import duckdb

DB_PATH = "data/cloudlens.db"


def test_all_tables_exist():
    conn = duckdb.connect(DB_PATH, read_only=True)
    tables = conn.execute("SHOW TABLES").df()['name'].tolist()
    conn.close()
    expected = {
        "raw_costs", "cleaned_costs", "team_daily_costs",
        "mac_daily_costs", "monthly_summary", "budget_limits"
    }
    for t in expected:
        assert t in tables, f"Missing table: {t}"


def test_no_nulls_in_key_columns():
    conn = duckdb.connect(DB_PATH, read_only=True)
    result = conn.execute("""
        SELECT COUNT(*) FROM cleaned_costs
        WHERE usage_date IS NULL
        OR cost_inr IS NULL
        OR meter_category IS NULL
    """).fetchone()[0]
    conn.close()
    assert result == 0


def test_eight_macs_in_daily_costs():
    conn = duckdb.connect(DB_PATH, read_only=True)
    count = conn.execute("""
        SELECT COUNT(DISTINCT mac_id) FROM mac_daily_costs
    """).fetchone()[0]
    conn.close()
    assert count == 8


def test_budget_limits_has_16_teams():
    conn = duckdb.connect(DB_PATH, read_only=True)
    count = conn.execute(
        "SELECT COUNT(*) FROM budget_limits"
    ).fetchone()[0]
    conn.close()
    assert count == 16


def test_monthly_summary_has_three_months():
    conn = duckdb.connect(DB_PATH, read_only=True)
    months = conn.execute("""
        SELECT COUNT(DISTINCT month) FROM monthly_summary
    """).fetchone()[0]
    conn.close()
    assert months == 3


def test_no_negative_costs_cleaned():
    conn = duckdb.connect(DB_PATH, read_only=True)
    result = conn.execute("""
        SELECT COUNT(*) FROM cleaned_costs WHERE cost_inr < 0
    """).fetchone()[0]
    conn.close()
    assert result == 0


def test_cost_totals_match():
    conn = duckdb.connect(DB_PATH, read_only=True)
    total_cleaned = conn.execute(
        "SELECT ROUND(SUM(cost_inr), 0) FROM cleaned_costs"
    ).fetchone()[0]
    total_daily = conn.execute(
        "SELECT ROUND(SUM(total_cost_inr), 0) FROM team_daily_costs"
    ).fetchone()[0]
    conn.close()
    assert total_cleaned == total_daily


def test_all_four_categories_present():
    conn = duckdb.connect(DB_PATH, read_only=True)
    cats = conn.execute("""
        SELECT DISTINCT resource_category FROM team_daily_costs
    """).df()['resource_category'].tolist()
    conn.close()
    for cat in ["Compute","Storage","Networking","Data Services"]:
        assert cat in cats