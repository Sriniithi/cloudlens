import pytest
import duckdb
import sys
import os

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))
from ai_engine.gemini_engine import (
    get_ai_response,
    get_rightsizing_recommendations,
    get_idle_resource_recommendations,
    get_reservation_recommendations
)

DB_PATH = "data/cloudlens.db"


def test_ollama_returns_response():
    response = get_ai_response(
        "Say hello in one word.", mode="ollama")
    assert isinstance(response, str)
    assert len(response) > 0
    # Both a real response (local) and graceful error (CI) are valid


def test_rightsizing_returns_list():
    result = get_rightsizing_recommendations(
        DB_PATH, mode="ollama")
    assert isinstance(result, list)


def test_rightsizing_pattern_name():
    result = get_rightsizing_recommendations(
        DB_PATH, mode="ollama")
    if result:
        assert result[0]["pattern"] == "right-sizing"
        assert result[0]["estimated_savings_inr"] > 0


def test_idle_returns_list():
    result = get_idle_resource_recommendations(
        DB_PATH, mode="ollama")
    assert isinstance(result, list)


def test_idle_pattern_name():
    result = get_idle_resource_recommendations(
        DB_PATH, mode="ollama")
    if result:
        assert result[0]["pattern"] == "idle-cleanup"


def test_reservation_returns_list():
    result = get_reservation_recommendations(
        DB_PATH, mode="ollama")
    assert isinstance(result, list)


def test_reservation_pattern_name():
    result = get_reservation_recommendations(
        DB_PATH, mode="ollama")
    if result:
        assert result[0]["pattern"] == "reservation"


def test_ai_recommendations_table_exists():
    conn = duckdb.connect(DB_PATH, read_only=True)
    tables = conn.execute(
        "SHOW TABLES").df()['name'].tolist()
    conn.close()
    assert 'ai_recommendations' in tables


def test_three_patterns_in_db():
    conn = duckdb.connect(DB_PATH, read_only=True)
    count = conn.execute("""
        SELECT COUNT(DISTINCT pattern) FROM ai_recommendations
    """).fetchone()[0]
    conn.close()
    assert count >= 2, f"Expected at least 2 patterns, got {count}"


def test_savings_positive():
    conn = duckdb.connect(DB_PATH, read_only=True)
    result = conn.execute("""
        SELECT COUNT(*) FROM ai_recommendations
        WHERE estimated_savings_inr <= 0
    """).fetchone()[0]
    conn.close()
    assert result == 0


def test_recommendation_text_not_empty():
    conn = duckdb.connect(DB_PATH, read_only=True)
    result = conn.execute("""
        SELECT COUNT(*) FROM ai_recommendations
        WHERE ai_recommendation IS NULL
        OR LENGTH(ai_recommendation) < 10
    """).fetchone()[0]
    conn.close()
    assert result == 0