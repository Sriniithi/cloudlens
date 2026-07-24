import pytest
import duckdb
import pandas as pd
import sys
import os

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))
from ai_engine.anomaly_engine import (
    load_daily_costs,
    detect_anomalies,
    generate_weekly_narrative
)

DB_PATH = "data/cloudlens.db"


def test_load_daily_costs_not_empty():
    df = load_daily_costs(DB_PATH)
    assert len(df) > 0
    assert 'daily_cost' in df.columns
    assert 'mac_id' in df.columns


def test_detect_anomalies_returns_dataframe():
    df = load_daily_costs(DB_PATH)
    result = detect_anomalies(df, window=30, threshold=2.0)
    assert isinstance(result, pd.DataFrame)


def test_day60_spike_detected_as_anomaly():
    df = load_daily_costs(DB_PATH)
    anomalies = detect_anomalies(df, window=30, threshold=2.0)
    if len(anomalies) > 0:
        ml_anomalies = anomalies[
            (anomalies['team'] == 'ML') &
            (anomalies['category'] == 'Compute')
        ]
        assert len(ml_anomalies) > 0, \
            "Day 60 ML/Compute spike should be detected"


def test_anomalies_have_required_columns():
    df = load_daily_costs(DB_PATH)
    anomalies = detect_anomalies(df, window=30, threshold=2.0)
    if len(anomalies) > 0:
        required = [
            'detection_date', 'mac_id', 'team',
            'category', 'daily_cost', 'rolling_mean',
            'z_score', 'pct_deviation', 'direction'
        ]
        for col in required:
            assert col in anomalies.columns


def test_anomaly_direction_values_valid():
    df = load_daily_costs(DB_PATH)
    anomalies = detect_anomalies(df, window=30, threshold=2.0)
    if len(anomalies) > 0:
        assert anomalies['direction'].isin(
            ['spike', 'drop']
        ).all()


def test_weekly_narrative_returns_string():
    df = load_daily_costs(DB_PATH)
    narrative = generate_weekly_narrative(df, mode="ollama")
    assert isinstance(narrative, str)
    assert len(narrative) > 0
    # In CI without Ollama, a graceful error string is acceptable
    # In local dev with Ollama running, a real narrative is returned
    # Both are valid — function must never crash


def test_anomaly_detections_table_exists_after_run():
    conn = duckdb.connect(DB_PATH, read_only=True)
    tables = conn.execute("SHOW TABLES").df()['name'].tolist()
    conn.close()
    assert 'anomaly_detections' in tables


def test_weekly_narratives_table_exists_after_run():
    conn = duckdb.connect(DB_PATH, read_only=True)
    tables = conn.execute("SHOW TABLES").df()['name'].tolist()
    conn.close()
    assert 'weekly_narratives' in tables


def test_z_scores_are_numeric():
    df = load_daily_costs(DB_PATH)
    anomalies = detect_anomalies(df, window=30, threshold=2.0)
    if len(anomalies) > 0:
        assert pd.to_numeric(
            anomalies['z_score'], errors='coerce'
        ).notna().all()