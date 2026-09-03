"""
Scale test data generator.
Generates ~50,000 rows for performance testing.
Uses same structure as generate_data.py but with:
- 365 days (full year)
- 2 instances per resource
"""
import sys
import os
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))

from ingestion.generate_data import generate_billing_data
import pandas as pd
import random
import os
from datetime import datetime, timedelta

MAC_TEAM_STRUCTURE = {
    "MAC-01": ["DevOps", "Platform"],
    "MAC-02": ["DataEngineering", "Analytics"],
    "MAC-03": ["Product", "Frontend"],
    "MAC-04": ["Backend", "QA"],
    "MAC-05": ["Security", "Compliance"],
    "MAC-06": ["Infrastructure", "CloudOps"],
    "MAC-07": ["ML", "Research"],
    "MAC-08": ["Finance", "Operations"],
}

SUBSCRIPTION_ID = "sub-psiog-001"

RESOURCES_EXTENDED = {
    "Compute": [
        ("Microsoft.Compute/virtualMachines",          "Virtual Machines"),
        ("Microsoft.ContainerService/managedClusters", "AKS Clusters"),
        ("Microsoft.Compute/virtualMachineScaleSets",  "VM Scale Sets"),
        ("Microsoft.Compute/disks",                    "Managed Disks"),
        ("Microsoft.Compute/snapshots",                "Disk Snapshots"),
    ],
    "Storage": [
        ("Microsoft.Storage/storageAccounts",              "Blob Storage"),
        ("Microsoft.Storage/storageAccounts/fileServices", "File Storage"),
        ("Microsoft.Storage/storageAccounts/tableServices","Table Storage"),
        ("Microsoft.Storage/storageAccounts/queueServices","Queue Storage"),
    ],
    "Networking": [
        ("Microsoft.Network/loadBalancers",          "Load Balancers"),
        ("Microsoft.Network/virtualNetworks",        "Virtual Networks"),
        ("Microsoft.Network/publicIPAddresses",      "Public IPs"),
        ("Microsoft.Network/applicationGateways",    "App Gateways"),
        ("Microsoft.Network/expressRouteCircuits",   "ExpressRoute"),
    ],
    "Data Services": [
        ("Microsoft.Sql/servers/databases",          "SQL Database"),
        ("Microsoft.DocumentDB/databaseAccounts",    "Cosmos DB"),
        ("Microsoft.DBforPostgreSQL/servers",        "PostgreSQL"),
        ("Microsoft.Synapse/workspaces",             "Synapse"),
        ("Microsoft.DataFactory/factories",          "Data Factory"),
    ],
}

BASE_COSTS = {
    "Compute": {
        "DevOps": 1200, "Platform": 1100,
        "DataEngineering": 900, "Analytics": 850,
        "Product": 600, "Frontend": 500,
        "Backend": 950, "QA": 400,
        "Security": 700, "Compliance": 350,
        "Infrastructure": 1400, "CloudOps": 1300,
        "ML": 1600, "Research": 800,
        "Finance": 300, "Operations": 450,
    },
    "Storage": {
        "DevOps": 300, "Platform": 280,
        "DataEngineering": 600, "Analytics": 550,
        "Product": 200, "Frontend": 150,
        "Backend": 350, "QA": 180,
        "Security": 250, "Compliance": 220,
        "Infrastructure": 400, "CloudOps": 380,
        "ML": 500, "Research": 450,
        "Finance": 200, "Operations": 300,
    },
    "Networking": {
        "DevOps": 200, "Platform": 250,
        "DataEngineering": 180, "Analytics": 160,
        "Product": 120, "Frontend": 100,
        "Backend": 220, "QA": 90,
        "Security": 300, "Compliance": 150,
        "Infrastructure": 350, "CloudOps": 320,
        "ML": 200, "Research": 180,
        "Finance": 100, "Operations": 130,
    },
    "Data Services": {
        "DevOps": 400, "Platform": 380,
        "DataEngineering": 900, "Analytics": 850,
        "Product": 300, "Frontend": 200,
        "Backend": 500, "QA": 250,
        "Security": 350, "Compliance": 300,
        "Infrastructure": 420, "CloudOps": 400,
        "ML": 700, "Research": 650,
        "Finance": 450, "Operations": 380,
    },
}


def generate_scale_data(
    days=180,
    spike_day=60,
    output_path="data/azure_billing_scale.csv"
):
    rows = []
    start_date = datetime(2026, 1, 1)

    for day_num in range(days):
        current_date = start_date + timedelta(days=day_num)
        date_str = current_date.strftime("%Y-%m-%d")

        for mac, teams in MAC_TEAM_STRUCTURE.items():
            for team in teams:
                for category, resource_list in RESOURCES_EXTENDED.items():
                    for resource_type, service_name in resource_list:
                        resource_group = (
                            f"rg-{mac.lower()}-{team.lower()}-prod"
                        )

                        base = BASE_COSTS[category][team]
                        variation = random.uniform(0.85, 1.15)
                        growth = 1 + (day_num * 0.002)
                        cost = round(base * variation * growth, 2)

                        if (day_num == spike_day
                                and team == "ML"
                                and category == "Compute"
                                and resource_type == "Microsoft.Compute/virtualMachines"):
                            cost = round(cost * 4.5, 2)

                        team_tag = (
                            "" if random.random() < 0.10
                            else f"team:{team}"
                        )

                        rows.append({
                            "usage_date":      date_str,
                            "subscription_id": SUBSCRIPTION_ID,
                            "mac_id":          mac,
                            "resource_group":  resource_group,
                            "resource_type":   resource_type,
                            "service_name":    service_name,
                            "meter_category":  category,
                            "team_tag":        team_tag,
                            "cost_inr":        cost,
                            "currency":        "INR",
                            "quantity":        round(random.uniform(1, 100), 2),
                            "unit_of_measure": "1 Hour",
                        })

    df = pd.DataFrame(rows)
    os.makedirs("data", exist_ok=True)
    df.to_csv(output_path, index=False)

    print(f"✅ Scale dataset: {len(df):,} rows")
    print(f"📅 Date range: {df['usage_date'].min()} → "
          f"{df['usage_date'].max()}")
    print(f"🏢 MACs: {df['mac_id'].nunique()}")
    print(f"💰 Total cost: ₹{df['cost_inr'].sum():,.2f}")
    print(f"📁 Saved to: {output_path}")
    return df


if __name__ == "__main__":
    generate_scale_data()