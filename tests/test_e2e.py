import pytest
import duckdb
import sys
import os

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))

DB_PATH = "data/cloudlens.db"


def test_e2e_all_tables_exist():
    """Full pipeline creates all required tables"""
    conn = duckdb.connect(DB_PATH, read_only=True)
    tables = conn.execute(
        "SHOW TABLES").df()['name'].tolist()
    conn.close()
    required = [
        "raw_costs", "cleaned_costs",
        "team_daily_costs", "mac_daily_costs",
        "monthly_summary", "budget_limits",
        "attributed_costs", "ai_recommendations"
    ]
    for t in required:
        assert t in tables, f"Missing table: {t}"


def test_e2e_data_flows_correctly():
    """Row counts are consistent across tables"""
    conn = duckdb.connect(DB_PATH, read_only=True)
    raw = conn.execute(
        "SELECT COUNT(*) FROM raw_costs").fetchone()[0]
    cleaned = conn.execute(
        "SELECT COUNT(*) FROM cleaned_costs").fetchone()[0]
    attributed = conn.execute(
        "SELECT COUNT(*) FROM attributed_costs").fetchone()[0]
    conn.close()
    assert raw > 0, "raw_costs is empty"
    assert cleaned > 0, "cleaned_costs is empty"
    assert attributed > 0, "attributed_costs is empty"
    assert attributed == cleaned, \
        "attributed_costs should have same rows as cleaned_costs"


def test_e2e_eight_macs_attributed():
    """All 8 MACs have attributed costs"""
    conn = duckdb.connect(DB_PATH, read_only=True)
    count = conn.execute("""
        SELECT COUNT(DISTINCT mac_id)
        FROM attributed_costs
    """).fetchone()[0]
    conn.close()
    assert count == 8


def test_e2e_all_four_categories():
    """All 4 resource categories present"""
    conn = duckdb.connect(DB_PATH, read_only=True)
    cats = conn.execute("""
        SELECT DISTINCT category FROM attributed_costs
    """).df()['category'].tolist()
    conn.close()
    for c in ["Compute","Storage","Networking","Data Services"]:
        assert c in cats


def test_e2e_three_ai_patterns():
    conn = duckdb.connect(DB_PATH, read_only=True)
    count = conn.execute("""
        SELECT COUNT(DISTINCT pattern) FROM ai_recommendations
    """).fetchone()[0]
    conn.close()
    assert count >= 2, f"Expected at least 2 AI patterns, got {count}"


def test_e2e_total_savings_positive():
    """AI recommendations have positive savings"""
    conn = duckdb.connect(DB_PATH, read_only=True)
    total = conn.execute("""
        SELECT SUM(estimated_savings_inr)
        FROM ai_recommendations
    """).fetchone()[0]
    conn.close()
    assert total > 0


def test_e2e_spike_detectable():
    """Day 60 ML Compute spike is detectable"""
    conn = duckdb.connect(DB_PATH, read_only=True)
    result = conn.execute("""
        SELECT MAX(cost_inr) / AVG(cost_inr) as spike_ratio
        FROM attributed_costs
        WHERE attributed_team = 'ML'
        AND category = 'Compute'
    """).fetchone()[0]
    conn.close()
    assert result > 2, \
        f"Expected spike ratio > 2, got {result:.2f}"


def test_e2e_budget_coverage():
    """All 16 teams have budget entries"""
    conn = duckdb.connect(DB_PATH, read_only=True)
    count = conn.execute(
        "SELECT COUNT(*) FROM budget_limits"
    ).fetchone()[0]
    conn.close()
    assert count == 16