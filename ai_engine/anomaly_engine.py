import duckdb
import pandas as pd
import numpy as np
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))
from ai_engine.gemini_engine import get_ai_response


def load_daily_costs(db_path="data/cloudlens.db"):
    conn = duckdb.connect(db_path, read_only=True)
    df = conn.execute("""
        SELECT
            usage_date,
            mac_id,
            attributed_team as team,
            category,
            ROUND(SUM(cost_inr), 2) as daily_cost
        FROM attributed_costs
        GROUP BY usage_date, mac_id, attributed_team, category
        ORDER BY usage_date, mac_id, attributed_team
    """).df()
    conn.close()
    df['usage_date'] = pd.to_datetime(df['usage_date'])
    return df


def detect_anomalies(df, window=30, threshold=2.0):
    """
    Z-score based anomaly detection.
    Flags any day where spend deviates more than
    `threshold` standard deviations from the rolling mean.
    """
    anomalies = []

    groups = df.groupby(['mac_id', 'team', 'category'])

    for (mac_id, team, category), group in groups:
        group = group.sort_values('usage_date').copy()
        if len(group) < 10:
            continue

        group['rolling_mean'] = group['daily_cost'].rolling(
            window=window, min_periods=5
        ).mean()
        group['rolling_std'] = group['daily_cost'].rolling(
            window=window, min_periods=5
        ).std()

        group['z_score'] = (
            group['daily_cost'] - group['rolling_mean']
        ) / (group['rolling_std'] + 1e-9)

        flagged = group[abs(group['z_score']) > threshold]

        for _, row in flagged.iterrows():
            pct_deviation = (
                (row['daily_cost'] - row['rolling_mean'])
                / row['rolling_mean'] * 100
            )
            anomalies.append({
                "detection_date":    row['usage_date'].strftime("%Y-%m-%d"),
                "mac_id":            mac_id,
                "team":              team,
                "category":          category,
                "daily_cost":        round(row['daily_cost'], 2),
                "rolling_mean":      round(row['rolling_mean'], 2),
                "z_score":           round(row['z_score'], 2),
                "pct_deviation":     round(pct_deviation, 1),
                "direction":         "spike" if row['z_score'] > 0 else "drop",
            })

    return pd.DataFrame(anomalies)


def generate_anomaly_narrative(anomaly_row, mode="ollama"):
    prompt = f"""
You are CloudLens AI, a FinOps expert for Psiog Digital.

A cost anomaly was detected in the Azure billing data:

Team: {anomaly_row['team']} (MAC: {anomaly_row['mac_id']})
Resource Category: {anomaly_row['category']}
Date: {anomaly_row['detection_date']}
Daily Cost: ₹{anomaly_row['daily_cost']:,.0f}
30-Day Rolling Average: ₹{anomaly_row['rolling_mean']:,.0f}
Deviation: {anomaly_row['pct_deviation']:+.1f}% ({anomaly_row['direction']})
Z-Score: {anomaly_row['z_score']:.2f}

Write a 3-sentence explanation:
1. State what happened clearly
2. Suggest the most likely cause (new VM, data pipeline job, deployment, etc.)
3. Recommend immediate action

Keep it concise and business-friendly.
"""
    return get_ai_response(prompt, mode=mode)


def generate_weekly_narrative(df, mode="ollama"):
    """Generate an AI-written weekly cost summary."""
    latest_week = df['usage_date'].max()
    week_start = latest_week - timedelta(days=6)

    week_data = df[df['usage_date'] >= week_start]

    team_summary = week_data.groupby('team')['daily_cost'].sum().round(2)
    top_team = team_summary.idxmax()
    top_spend = team_summary.max()

    mac_summary = week_data.groupby('mac_id')['daily_cost'].sum().round(2)
    top_mac = mac_summary.idxmax()

    cat_summary = week_data.groupby('category')['daily_cost'].sum().round(2)
    top_cat = cat_summary.idxmax()

    total_week = week_data['daily_cost'].sum()

    prior_week_start = week_start - timedelta(days=7)
    prior_data = df[
        (df['usage_date'] >= prior_week_start) &
        (df['usage_date'] < week_start)
    ]
    total_prior = prior_data['daily_cost'].sum()
    wow_change = ((total_week - total_prior) / total_prior * 100
                  if total_prior > 0 else 0)

    prompt = f"""
You are CloudLens AI writing a weekly cost summary for Psiog Digital leadership.

Week: {week_start.strftime('%d %b')} to {latest_week.strftime('%d %b %Y')}
Total spend this week: ₹{total_week:,.0f}
Week-over-week change: {wow_change:+.1f}%
Highest spending team: {top_team} (₹{top_spend:,.0f})
Highest spending MAC: {top_mac}
Highest cost category: {top_cat}

Team breakdown (top 5):
{team_summary.nlargest(5).to_string()}

Write a 4-sentence executive summary:
1. Overall spend trend this week
2. Key driver — which team/category drove the most cost
3. Any concern or positive trend to highlight
4. One specific recommended action for next week

Write in a professional, concise tone suitable for a CFO or CTO.
"""
    return get_ai_response(prompt, mode=mode)


def run_anomaly_detection(
    db_path="data/cloudlens.db",
    mode="ollama"
):
    print("=" * 60)
    print("CLOUDLENS AI — ANOMALY DETECTION ENGINE")
    print("=" * 60)

    df = load_daily_costs(db_path)
    print(f"Loaded {len(df)} daily cost records")

    print("\n--- Running Z-Score Anomaly Detection ---")
    anomalies_df = detect_anomalies(df, window=30, threshold=2.0)
    print(f"Detected {len(anomalies_df)} anomalies")

    if not anomalies_df.empty:
        print("\n=== ANOMALIES DETECTED ===")
        print(anomalies_df[[
            'detection_date', 'mac_id', 'team',
            'category', 'daily_cost', 'rolling_mean',
            'pct_deviation', 'direction'
        ]].to_string(index=False))

        print("\n=== AI EXPLANATIONS ===")
        narratives = []
        for _, anomaly in anomalies_df.head(5).iterrows():
            print(f"\n[{anomaly['team']} / {anomaly['category']} / {anomaly['detection_date']}]")
            narrative = generate_anomaly_narrative(anomaly, mode)
            print(narrative)
            narratives.append({
                **anomaly.to_dict(),
                "ai_narrative": narrative
            })
        anomalies_df['ai_narrative'] = ""
        for i, n in enumerate(narratives):
            if i < len(anomalies_df):
                anomalies_df.iloc[i, anomalies_df.columns.get_loc('ai_narrative')] = \
                    n.get('ai_narrative', '')
    else:
        print("No anomalies detected above threshold.")

    print("\n=== WEEKLY COST NARRATIVE ===")
    weekly_narrative = generate_weekly_narrative(df, mode)
    print(weekly_narrative)

    write_conn = duckdb.connect(db_path)

    write_conn.execute("DROP TABLE IF EXISTS anomaly_detections")
    if not anomalies_df.empty:
        write_conn.execute("""
            CREATE TABLE anomaly_detections AS
            SELECT * FROM anomalies_df
        """)
    else:
        write_conn.execute("""
            CREATE TABLE anomaly_detections (
                detection_date VARCHAR, mac_id VARCHAR,
                team VARCHAR, category VARCHAR,
                daily_cost DOUBLE, rolling_mean DOUBLE,
                z_score DOUBLE, pct_deviation DOUBLE,
                direction VARCHAR, ai_narrative VARCHAR
            )
        """)

    write_conn.execute("DROP TABLE IF EXISTS weekly_narratives")
    narratives_df = pd.DataFrame([{
        "week_ending": df['usage_date'].max().strftime("%Y-%m-%d"),
        "narrative":   weekly_narrative,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }])
    write_conn.execute("""
        CREATE TABLE weekly_narratives AS
        SELECT * FROM narratives_df
    """)

    print(f"\nSaved {len(anomalies_df)} anomalies to anomaly_detections table")
    print("Saved weekly narrative to weekly_narratives table")

    write_conn.close()
    return anomalies_df, weekly_narrative


if __name__ == "__main__":
    run_anomaly_detection(mode="ollama")