import pytest
import sys
import os
import duckdb

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))

DB_PATH = "data/cloudlens.db"


def test_db_has_all_required_tables_for_chat():
    conn = duckdb.connect(DB_PATH, read_only=True)
    tables = conn.execute("SHOW TABLES").df()['name'].tolist()
    conn.close()
    required = [
        "team_daily_costs", "monthly_summary",
        "budget_limits", "attributed_costs",
        "ai_recommendations", "budget_forecast", "budget_alerts"
    ]
    for t in required:
        assert t in tables, f"Table {t} missing — chat needs it"


def test_budget_alerts_has_data():
    conn = duckdb.connect(DB_PATH, read_only=True)
    count = conn.execute(
        "SELECT COUNT(*) FROM budget_alerts"
    ).fetchone()[0]
    conn.close()
    assert count >= 0


def test_ai_recommendations_has_3_patterns():
    conn = duckdb.connect(DB_PATH, read_only=True)
    patterns = conn.execute(
        "SELECT DISTINCT pattern FROM ai_recommendations"
    ).df()['pattern'].tolist()
    conn.close()
    for p in ["right-sizing", "idle-cleanup", "reservation"]:
        assert p in patterns


def test_team_daily_costs_queryable():
    conn = duckdb.connect(DB_PATH, read_only=True)
    df = conn.execute("""
        SELECT team, ROUND(SUM(total_cost_inr),2) as total
        FROM team_daily_costs
        GROUP BY team
        ORDER BY total DESC
        LIMIT 5
    """).df()
    conn.close()
    assert len(df) == 5
    assert 'team' in df.columns
    assert 'total' in df.columns


def test_budget_forecast_has_two_scenario_columns():
    conn = duckdb.connect(DB_PATH, read_only=True)
    cols = conn.execute(
        "SELECT * FROM budget_forecast LIMIT 1"
    ).df().columns.tolist()
    conn.close()
    assert 'projected_bau_inr' in cols
    assert 'projected_optimized_inr' in cols


def test_question_to_sql_import():
    from chat_interface.app import question_to_sql
    assert callable(question_to_sql)


def test_run_query_import():
    from chat_interface.app import run_query
    result, error = run_query(
        "SELECT COUNT(*) as cnt FROM attributed_costs"
    )
    assert result is not None
    assert error is None
    assert result['cnt'].iloc[0] > 0