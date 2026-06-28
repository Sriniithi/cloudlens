import pytest
import pandas as pd
import duckdb
import os
import sys

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))
from ingestion.azure_connector import AzureCostConnector


def test_csv_has_required_columns():
    df = pd.read_csv("data/azure_billing_raw.csv")
    required = [
        "usage_date", "subscription_id", "mac_id",
        "resource_group", "resource_type", "service_name",
        "meter_category", "team_tag", "cost_inr", "currency"
    ]
    for col in required:
        assert col in df.columns, f"Missing: {col}"


def test_no_negative_costs():
    df = pd.read_csv("data/azure_billing_raw.csv")
    assert (df['cost_inr'] >= 0).all()


def test_four_resource_categories():
    df = pd.read_csv("data/azure_billing_raw.csv")
    expected = {"Compute", "Storage", "Networking", "Data Services"}
    assert expected == set(df['meter_category'].unique())


def test_eight_macs_present():
    df = pd.read_csv("data/azure_billing_raw.csv")
    assert df['mac_id'].nunique() == 8


def test_sixteen_teams_present():
    df = pd.read_csv("data/azure_billing_raw.csv")
    tagged = df[df['team_tag'].notna() & (df['team_tag'] != '')]
    teams = set(tagged['team_tag'].str.replace('team:', '').unique())
    assert len(teams) == 16


def test_date_range_is_90_days():
    df = pd.read_csv("data/azure_billing_raw.csv")
    df['usage_date'] = pd.to_datetime(df['usage_date'])
    day_range = (
        df['usage_date'].max() - df['usage_date'].min()
    ).days
    assert day_range == 89


def test_some_rows_untagged():
    df = pd.read_csv("data/azure_billing_raw.csv")
    untagged = df[df['team_tag'].isna() | (df['team_tag'] == '')]
    assert len(untagged) > 0


def test_duckdb_loads():
    conn = duckdb.connect("data/cloudlens.db", read_only=True)
    count = conn.execute(
        "SELECT COUNT(*) FROM raw_costs"
    ).fetchone()[0]
    conn.close()
    assert count > 0


def test_connector_returns_dataframe():
    c = AzureCostConnector(mode="synthetic")
    df = c.get_cost_data(days_back=30)
    assert isinstance(df, pd.DataFrame)
    assert len(df) > 0


def test_budget_has_16_teams():
    c = AzureCostConnector(mode="synthetic")
    budgets = c.get_budget_data()
    assert len(budgets) == 16


def test_mac_budgets_has_8_macs():
    c = AzureCostConnector(mode="synthetic")
    macs = c.get_mac_budgets()
    assert len(macs) == 8


def test_spike_exists():
    df = pd.read_csv("data/azure_billing_raw.csv")
    df['usage_date'] = pd.to_datetime(df['usage_date'])
    spike_date = (
        df['usage_date'].min() + pd.Timedelta(days=60)
    )
    spike = df[
        (df['usage_date'] == spike_date) &
        (df['team_tag'] == 'team:ML') &
        (df['meter_category'] == 'Compute')
    ]
    avg = df[
        (df['team_tag'] == 'team:ML') &
        (df['meter_category'] == 'Compute')
    ]['cost_inr'].mean()
    assert spike['cost_inr'].values[0] > avg * 2