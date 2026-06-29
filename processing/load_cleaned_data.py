import duckdb


def setup_duckdb_schema(
    clean_csv="data/azure_billing_clean.csv",
    db_path="data/cloudlens.db"
):
    print("Setting up DuckDB schema...")
    conn = duckdb.connect(db_path)

    # Table 1: cleaned_costs
    conn.execute("DROP TABLE IF EXISTS cleaned_costs")
    conn.execute(f"""
        CREATE TABLE cleaned_costs AS
        SELECT * FROM read_csv_auto('{clean_csv}')
    """)
    print(f"cleaned_costs: "
          f"{conn.execute('SELECT COUNT(*) FROM cleaned_costs').fetchone()[0]}")

    # Table 2: team_daily_costs
    conn.execute("DROP TABLE IF EXISTS team_daily_costs")
    conn.execute("""
        CREATE TABLE team_daily_costs AS
        SELECT
            usage_date,
            mac_id,
            replace(team_tag, 'team:', '') as team,
            meter_category as resource_category,
            ROUND(SUM(cost_inr), 2) as total_cost_inr,
            COUNT(*) as resource_count
        FROM cleaned_costs
        GROUP BY usage_date, mac_id, team_tag, meter_category
        ORDER BY usage_date, mac_id, team
    """)
    print(f"team_daily_costs: "
          f"{conn.execute('SELECT COUNT(*) FROM team_daily_costs').fetchone()[0]}")

    # Table 3: mac_daily_costs
    conn.execute("DROP TABLE IF EXISTS mac_daily_costs")
    conn.execute("""
        CREATE TABLE mac_daily_costs AS
        SELECT
            usage_date,
            mac_id,
            meter_category as resource_category,
            ROUND(SUM(cost_inr), 2) as total_cost_inr,
            COUNT(*) as resource_count
        FROM cleaned_costs
        GROUP BY usage_date, mac_id, meter_category
        ORDER BY usage_date, mac_id
    """)
    print(f"mac_daily_costs: "
          f"{conn.execute('SELECT COUNT(*) FROM mac_daily_costs').fetchone()[0]}")

    # Table 4: monthly_summary
    conn.execute("DROP TABLE IF EXISTS monthly_summary")
    conn.execute("""
        CREATE TABLE monthly_summary AS
        SELECT
            STRFTIME(usage_date, '%Y-%m') as month,
            mac_id,
            replace(team_tag, 'team:', '') as team,
            meter_category as resource_category,
            ROUND(SUM(cost_inr), 2) as total_cost_inr
        FROM cleaned_costs
        GROUP BY month, mac_id, team_tag, meter_category
        ORDER BY month, mac_id, team
    """)
    print(f"monthly_summary: "
          f"{conn.execute('SELECT COUNT(*) FROM monthly_summary').fetchone()[0]}")

    # Table 5: budget_limits (team level)
    conn.execute("DROP TABLE IF EXISTS budget_limits")
    conn.execute("""
        CREATE TABLE budget_limits (
            mac_id VARCHAR,
            team VARCHAR,
            monthly_budget_inr DOUBLE
        )
    """)
    conn.execute("""
        INSERT INTO budget_limits VALUES
            ('MAC-01','DevOps',45000),
            ('MAC-01','Platform',40000),
            ('MAC-02','DataEngineering',55000),
            ('MAC-02','Analytics',50000),
            ('MAC-03','Product',30000),
            ('MAC-03','Frontend',25000),
            ('MAC-04','Backend',38000),
            ('MAC-04','QA',20000),
            ('MAC-05','Security',35000),
            ('MAC-05','Compliance',28000),
            ('MAC-06','Infrastructure',60000),
            ('MAC-06','CloudOps',55000),
            ('MAC-07','ML',65000),
            ('MAC-07','Research',48000),
            ('MAC-08','Finance',25000),
            ('MAC-08','Operations',30000)
    """)
    print("budget_limits: 16 rows")

    print("\n=== ALL TABLES ===")
    print(conn.execute("SHOW TABLES").df())

    print("\n=== COST BY MAC (monthly_summary) ===")
    print(conn.execute("""
        SELECT mac_id,
               ROUND(SUM(total_cost_inr), 2) as total
        FROM monthly_summary
        GROUP BY mac_id
        ORDER BY total DESC
    """).df())

    conn.close()
    print("\n✅ DuckDB schema setup complete!")


if __name__ == "__main__":
    setup_duckdb_schema()