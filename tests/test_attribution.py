import pytest
import pandas as pd
import duckdb
import sys
import os

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))
from processing.attribution_model import (
    categorize_resource, attribute_team
)

DB_PATH = "data/cloudlens.db"


def test_compute_category():
    assert categorize_resource(
        "Microsoft.Compute/virtualMachines") == "Compute"


def test_storage_category():
    assert categorize_resource(
        "Microsoft.Storage/storageAccounts") == "Storage"


def test_networking_category():
    assert categorize_resource(
        "Microsoft.Network/loadBalancers") == "Networking"


def test_data_services_category():
    assert categorize_resource(
        "Microsoft.Sql/servers/databases") == "Data Services"


def test_fallback_meter_category():
    assert categorize_resource(
        "Microsoft.Unknown/resource", "Compute") == "Compute"


def test_high_confidence_tag():
    team, conf = attribute_team(
        "team:ML", "rg-mac-07-ml-prod", "MAC-07")
    assert team == "ML"
    assert conf == "high"


def test_medium_confidence_rg():
    team, conf = attribute_team(
        "", "rg-mac-01-devops-prod", "MAC-01")
    assert team == "DevOps"
    assert conf == "medium"


def test_low_confidence_mac_fallback():
    team, conf = attribute_team(
        "", "rg-unknown-prod", "MAC-03")
    assert team == "Product"
    assert conf == "low"


def test_accuracy_on_labeled_dataset():
    df = pd.read_csv("data/attribution_test_dataset.csv")
    correct_team = 0
    correct_cat = 0
    total = len(df)
    for _, row in df.iterrows():
        team, conf = attribute_team(
            row['team_tag'],
            row['resource_group'],
            row['mac_id']
        )
        if team == row['expected_team']:
            correct_team += 1
        cat = categorize_resource(
            row['resource_type'], row['meter_category']
        )
        if cat == row['expected_category']:
            correct_cat += 1
    team_acc = correct_team / total * 100
    cat_acc = correct_cat / total * 100
    print(f"\nTeam accuracy: {team_acc:.1f}%")
    print(f"Category accuracy: {cat_acc:.1f}%")
    assert team_acc >= 95
    assert cat_acc == 100


def test_attributed_costs_exists():
    conn = duckdb.connect(DB_PATH, read_only=True)
    tables = conn.execute(
        "SHOW TABLES"
    ).df()['name'].tolist()
    conn.close()
    assert 'attributed_costs' in tables


def test_no_null_attributed_teams():
    conn = duckdb.connect(DB_PATH, read_only=True)
    result = conn.execute("""
        SELECT COUNT(*) FROM attributed_costs
        WHERE attributed_team IS NULL
    """).fetchone()[0]
    conn.close()
    assert result == 0


def test_high_confidence_above_80_pct():
    conn = duckdb.connect(DB_PATH, read_only=True)
    total = conn.execute(
        "SELECT COUNT(*) FROM attributed_costs"
    ).fetchone()[0]
    high = conn.execute("""
        SELECT COUNT(*) FROM attributed_costs
        WHERE attribution_confidence = 'high'
    """).fetchone()[0]
    conn.close()
    assert (high / total * 100) >= 80


def test_all_8_macs_attributed():
    conn = duckdb.connect(DB_PATH, read_only=True)
    count = conn.execute("""
        SELECT COUNT(DISTINCT mac_id) FROM attributed_costs
    """).fetchone()[0]
    conn.close()
    assert count == 8