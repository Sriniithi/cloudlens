import pytest
import duckdb
import pandas as pd
import sys
import os

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))
from processing.budget_forecast import (
    load_team_spending_history,
    load_budget_limits,
    forecast_team_spend,
    run_forecast
)

DB_PATH = "data/cloudlens.db"


def test_load_spending_history_not_empty():
    df = load_team_spending_history(DB_PATH)
    assert len(df) > 0
    assert 'team' in df.columns
    assert 'daily_cost' in df.columns
    assert 'mac_id' in df.columns


def test_load_budget_limits_has_16_teams():
    df = load_budget_limits(DB_PATH)
    assert len(df) == 16


def test_forecast_returns_valid_structure():
    daily_df = load_team_spending_history(DB_PATH)
    future_dates, forecast, slope, intercept = \
        forecast_team_spend(daily_df, "ML", days_ahead=30)
    assert future_dates is not None
    assert len(future_dates) == 30
    assert len(forecast) == 30
    assert all(f >= 0 for f in forecast)


def test_forecast_no_negative_values():
    daily_df = load_team_spending_history(DB_PATH)
    for team in ["DevOps", "ML", "Platform"]:
        result = forecast_team_spend(daily_df, team, days_ahead=30)
        if result[0] is not None:
            _, forecast, _, _ = result
            assert all(f >= 0 for f in forecast)


def test_run_forecast_creates_tables():
    run_forecast(DB_PATH)
    conn = duckdb.connect(DB_PATH, read_only=True)
    tables = conn.execute("SHOW TABLES").df()['name'].tolist()
    conn.close()
    assert 'budget_forecast' in tables
    assert 'budget_alerts' in tables


def test_budget_forecast_has_two_scenarios():
    conn = duckdb.connect(DB_PATH, read_only=True)
    df = conn.execute("SELECT * FROM budget_forecast").df()
    conn.close()
    assert 'projected_bau_inr' in df.columns
    assert 'projected_optimized_inr' in df.columns
    assert len(df) == 16


def test_optimized_always_less_than_bau():
    conn = duckdb.connect(DB_PATH, read_only=True)
    df = conn.execute("""
        SELECT projected_bau_inr, projected_optimized_inr
        FROM budget_forecast
    """).df()
    conn.close()
    assert (df['projected_optimized_inr'] <=
            df['projected_bau_inr']).all()


def test_breach_flags_are_boolean():
    conn = duckdb.connect(DB_PATH, read_only=True)
    df = conn.execute("""
        SELECT bau_breach, optimized_breach FROM budget_forecast
    """).df()
    conn.close()
    assert df['bau_breach'].dtype == bool or \
           df['bau_breach'].isin([True, False, 0, 1]).all()


def test_all_8_macs_in_forecast():
    conn = duckdb.connect(DB_PATH, read_only=True)
    count = conn.execute("""
        SELECT COUNT(DISTINCT mac_id) FROM budget_forecast
    """).fetchone()[0]
    conn.close()
    assert count == 8


def test_alerts_table_exists_and_has_correct_columns():
    conn = duckdb.connect(DB_PATH, read_only=True)
    df = conn.execute("SELECT * FROM budget_alerts").df()
    conn.close()
    expected_cols = ['mac_id', 'team', 'severity', 'message']
    for col in expected_cols:
        assert col in df.columns


def test_trend_column_values_are_valid():
    conn = duckdb.connect(DB_PATH, read_only=True)
    trends = conn.execute("""
        SELECT DISTINCT spend_trend FROM budget_forecast
    """).df()['spend_trend'].tolist()
    conn.close()
    valid_trends = {
        "Increasing rapidly", "Increasing steadily",
        "Stable", "Decreasing"
    }
    for t in trends:
        assert t in valid_trends, f"Unexpected trend: {t}"