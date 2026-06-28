import pandas as pd
from datetime import datetime, timedelta
import os


class AzureCostConnector:

    def __init__(self, mode="synthetic"):
        self.mode = mode
        print(f"🔌 AzureCostConnector [{mode} mode]")

    def get_cost_data(self, days_back=30):
        if self.mode == "synthetic":
            return self._read_synthetic(days_back)
        elif self.mode == "api":
            return self._call_azure_api(days_back)

    def _read_synthetic(self, days_back):
        csv_path = "data/azure_billing_raw.csv"
        if not os.path.exists(csv_path):
            raise FileNotFoundError(
                "Run ingestion/generate_data.py first"
            )
        df = pd.read_csv(csv_path)
        df['usage_date'] = pd.to_datetime(df['usage_date'])
        cutoff = df['usage_date'].max() - timedelta(days=days_back)
        df = df[df['usage_date'] >= cutoff]
        print(f"✅ Loaded {len(df)} rows ({days_back} days)")
        return df

    def _call_azure_api(self, days_back):
        raise NotImplementedError(
            "Azure API mode implemented in Week 13"
        )

    def get_budget_data(self):
        # Monthly budgets per team (INR)
        budgets = {
            "DevOps":          45000,
            "Platform":        40000,
            "DataEngineering": 55000,
            "Analytics":       50000,
            "Product":         30000,
            "Frontend":        25000,
            "Backend":         38000,
            "QA":              20000,
            "Security":        35000,
            "Compliance":      28000,
            "Infrastructure":  60000,
            "CloudOps":        55000,
            "ML":              65000,
            "Research":        48000,
            "Finance":         25000,
            "Operations":      30000,
        }
        return budgets

    def get_mac_budgets(self):
        # Monthly budgets per MAC (INR)
        return {
            "MAC-01": 85000,
            "MAC-02": 105000,
            "MAC-03": 55000,
            "MAC-04": 58000,
            "MAC-05": 63000,
            "MAC-06": 115000,
            "MAC-07": 113000,
            "MAC-08": 55000,
        }


def main(timer=None):
    print(f"⏰ Azure Functions trigger: {datetime.now()}")
    connector = AzureCostConnector(mode="synthetic")
    df = connector.get_cost_data(days_back=1)
    import duckdb
    conn = duckdb.connect("data/cloudlens.db")
    conn.execute("INSERT INTO raw_costs SELECT * FROM df")
    conn.close()
    print(f"✅ Daily ingestion: {len(df)} rows added")


if __name__ == "__main__":
    connector = AzureCostConnector(mode="synthetic")
    df = connector.get_cost_data(days_back=30)
    print(df.head())
    print(connector.get_budget_data())
    print(connector.get_mac_budgets())