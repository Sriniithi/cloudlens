"""
Scale and performance tests.
Validates the pipeline handles large datasets
within acceptable time limits.
"""
import pytest
import time
import duckdb
import pandas as pd
import os
import sys

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))

DB_PATH = "data/cloudlens.db"
SCALE_CSV = "data/azure_billing_scale.csv"


# ─────────────────────────────────────────
# TEST 1 — Scale data file exists
# ─────────────────────────────────────────
def test_scale_data_file_exists():
    assert os.path.exists(SCALE_CSV), \
        "Run python ingestion/generate_scale_data.py first"


# ─────────────────────────────────────────
# TEST 2 — Scale data has enough rows
# ─────────────────────────────────────────
def test_scale_data_has_40k_plus_rows():
    df = pd.read_csv(SCALE_CSV)
    assert len(df) >= 40000, \
        f"Expected 40K+ rows, got {len(df):,}"
    print(f"\nScale dataset: {len(df):,} rows")


# ─────────────────────────────────────────
# TEST 3 — DuckDB loads scale data fast
# ─────────────────────────────────────────
def test_duckdb_loads_scale_data_under_30_seconds():
    start = time.time()

    conn = duckdb.connect(":memory:")
    conn.execute(f"""
        CREATE TABLE scale_test AS
        SELECT * FROM read_csv_auto('{SCALE_CSV}')
    """)
    count = conn.execute(
        "SELECT COUNT(*) FROM scale_test"
    ).fetchone()[0]
    conn.close()

    elapsed = time.time() - start
    print(f"\nLoaded {count:,} rows in {elapsed:.2f}s")
    assert elapsed < 30, \
        f"Load took {elapsed:.2f}s — expected under 30s"
    assert count >= 40000


# ─────────────────────────────────────────
# TEST 4 — Attribution query fast on scale data
# ─────────────────────────────────────────
def test_attribution_query_under_5_seconds():
    conn = duckdb.connect(":memory:")
    conn.execute(f"""
        CREATE TABLE scale_test AS
        SELECT * FROM read_csv_auto('{SCALE_CSV}')
    """)

    start = time.time()
    result = conn.execute("""
        SELECT
            CASE WHEN team_tag = '' OR team_tag IS NULL
                 THEN 'Untagged'
                 ELSE replace(team_tag, 'team:', '')
            END as team,
            mac_id,
            meter_category,
            ROUND(SUM(cost_inr), 2) as total_cost,
            COUNT(*) as records
        FROM scale_test
        GROUP BY team_tag, mac_id, meter_category
        ORDER BY total_cost DESC
    """).df()
    elapsed = time.time() - start

    print(f"\nAttribution query: {elapsed:.3f}s, {len(result)} groups")
    conn.close()
    assert elapsed < 5, \
        f"Attribution query took {elapsed:.2f}s — expected under 5s"
    assert len(result) > 0


# ─────────────────────────────────────────
# TEST 5 — Aggregation query fast on scale
# ─────────────────────────────────────────
def test_aggregation_query_under_3_seconds():
    conn = duckdb.connect(":memory:")
    conn.execute(f"""
        CREATE TABLE scale_test AS
        SELECT * FROM read_csv_auto('{SCALE_CSV}')
    """)

    start = time.time()
    result = conn.execute("""
        SELECT
            mac_id,
            ROUND(SUM(cost_inr), 2) as total_cost,
            COUNT(*) as records,
            COUNT(DISTINCT usage_date) as days,
            COUNT(DISTINCT team_tag) as teams
        FROM scale_test
        GROUP BY mac_id
        ORDER BY total_cost DESC
    """).df()
    elapsed = time.time() - start

    print(f"\nMAC aggregation: {elapsed:.3f}s")
    conn.close()
    assert elapsed < 3, \
        f"MAC aggregation took {elapsed:.2f}s — expected under 3s"
    assert len(result) == 8


# ─────────────────────────────────────────
# TEST 6 — Monthly summary on scale data
# ─────────────────────────────────────────
def test_monthly_summary_under_5_seconds():
    conn = duckdb.connect(":memory:")
    conn.execute(f"""
        CREATE TABLE scale_test AS
        SELECT * FROM read_csv_auto('{SCALE_CSV}')
    """)

    start = time.time()
    result = conn.execute("""
        SELECT
            STRFTIME(CAST(usage_date AS DATE), '%Y-%m') as month,
            mac_id,
            ROUND(SUM(cost_inr), 2) as monthly_cost
        FROM scale_test
        GROUP BY month, mac_id
        ORDER BY month, mac_id
    """).df()
    elapsed = time.time() - start

    months = result['month'].nunique()
    print(f"\nMonthly summary: {elapsed:.3f}s, {months} months")
    conn.close()
    assert elapsed < 5
    assert months >= 6


# ─────────────────────────────────────────
# TEST 7 — Existing DuckDB tables still intact
# ─────────────────────────────────────────
def test_existing_tables_unaffected_by_scale_test():
    conn = duckdb.connect(DB_PATH, read_only=True)
    tables = conn.execute("SHOW TABLES").df()['name'].tolist()
    conn.close()
    required = [
        "raw_costs", "cleaned_costs", "team_daily_costs",
        "attributed_costs", "ai_recommendations",
        "budget_forecast", "budget_alerts",
        "anomaly_detections", "weekly_narratives"
    ]
    for t in required:
        assert t in tables, f"Table {t} missing after scale test"


# ─────────────────────────────────────────
# TEST 8 — Z-score anomaly detection on scale data
# ─────────────────────────────────────────
def test_anomaly_detection_runs_on_scale_data():
    from ai_engine.anomaly_engine import detect_anomalies

    df = pd.read_csv(SCALE_CSV)
    df['usage_date'] = pd.to_datetime(df['usage_date'])

    # Reshape to match expected format
    daily_df = df.groupby([
        'usage_date', 'mac_id', 'team_tag', 'meter_category'
    ])['cost_inr'].sum().reset_index()
    daily_df.columns = [
        'usage_date', 'mac_id', 'team', 'category', 'daily_cost'
    ]

    start = time.time()
    anomalies = detect_anomalies(
        daily_df, window=30, threshold=2.0
    )
    elapsed = time.time() - start

    print(f"\nAnomaly detection on scale data: "
          f"{elapsed:.2f}s, {len(anomalies)} anomalies")
    assert elapsed < 60, \
        f"Anomaly detection took {elapsed:.2f}s — expected under 60s"
    assert isinstance(anomalies, pd.DataFrame)


# ─────────────────────────────────────────
# TEST 9 — Chat query response time
# ─────────────────────────────────────────
def test_chat_query_response_under_2_seconds():
    from chat_interface.utils import run_query

    start = time.time()
    result, error = run_query("""
        SELECT team, mac_id,
               ROUND(SUM(total_cost_inr),2) as total_spend
        FROM team_daily_costs
        GROUP BY team, mac_id
        ORDER BY total_spend DESC
        LIMIT 10
    """)
    elapsed = time.time() - start

    print(f"\nChat query response: {elapsed:.3f}s")
    assert elapsed < 2, \
        f"Chat query took {elapsed:.2f}s — expected under 2s"
    assert result is not None
    assert error is None


# ─────────────────────────────────────────
# TEST 10 — Template matching is instant
# ─────────────────────────────────────────
def test_template_matching_is_instant():
    from chat_interface.utils import question_to_sql

    questions = [
        "Show me teams that are over budget",
        "Which team spent the most?",
        "Show anomalies and spikes",
        "What are the AI recommendations?",
        "Show budget forecast",
    ]

    start = time.time()
    for q in questions:
        sql = question_to_sql(q)
        assert sql is not None, f"No SQL for: {q}"
    elapsed = time.time() - start

    print(f"\nTemplate matching for 5 questions: {elapsed:.4f}s")
    assert elapsed < 0.1, \
        f"Template matching took {elapsed:.4f}s — should be instant"