import duckdb
import os

def load_csv_to_duckdb(
    csv_path="data/azure_billing_raw.csv",
    db_path="data/cloudlens.db"
):
    print(f"Loading {csv_path} into DuckDB...")
    conn = duckdb.connect(db_path)
    conn.execute("DROP TABLE IF EXISTS raw_costs")
    conn.execute(f"""
        CREATE TABLE raw_costs AS
        SELECT * FROM read_csv_auto('{csv_path}')
    """)
    count = conn.execute(
        "SELECT COUNT(*) FROM raw_costs"
    ).fetchone()[0]
    print(f"✅ Loaded {count} rows into raw_costs")

    print("\n💰 Cost by MAC:")
    print(conn.execute("""
        SELECT mac_id,
               ROUND(SUM(cost_inr), 2) as total_cost,
               COUNT(DISTINCT team_tag) as teams
        FROM raw_costs
        GROUP BY mac_id
        ORDER BY total_cost DESC
    """).df())

    print("\n💰 Cost by category:")
    print(conn.execute("""
        SELECT meter_category,
               ROUND(SUM(cost_inr), 2) as total_cost
        FROM raw_costs
        GROUP BY meter_category
        ORDER BY total_cost DESC
    """).df())

    conn.close()
    print(f"\n✅ DuckDB saved at: {db_path}")


if __name__ == "__main__":
    load_csv_to_duckdb()