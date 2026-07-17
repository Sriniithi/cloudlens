import duckdb
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import PolynomialFeatures
from datetime import datetime, timedelta
import os
import sys

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))


def load_team_spending_history(db_path="data/cloudlens.db"):
    """Load daily cost data per team from DuckDB."""
    conn = duckdb.connect(db_path, read_only=True)
    df = conn.execute("""
        SELECT
            usage_date,
            mac_id,
            team,
            ROUND(SUM(total_cost_inr), 2) as daily_cost
        FROM team_daily_costs
        GROUP BY usage_date, mac_id, team
        ORDER BY mac_id, team, usage_date
    """).df()
    conn.close()
    df['usage_date'] = pd.to_datetime(df['usage_date'])
    return df


def load_budget_limits(db_path="data/cloudlens.db"):
    """Load monthly budget per team."""
    conn = duckdb.connect(db_path, read_only=True)
    df = conn.execute("SELECT * FROM budget_limits").df()
    conn.close()
    return df


def forecast_team_spend(daily_df, team, days_ahead=30):
    """
    Fits a linear regression on the team's daily spend history.
    Returns forecast for next N days.
    """
    team_data = daily_df[daily_df['team'] == team].copy()
    team_data = team_data.sort_values('usage_date')

    if len(team_data) < 10:
        return None, None

    # Convert dates to numeric day numbers for regression
    team_data['day_num'] = (
        team_data['usage_date'] -
        team_data['usage_date'].min()
    ).dt.days

    X = team_data['day_num'].values.reshape(-1, 1)
    y = team_data['daily_cost'].values

    # Fit linear regression
    model = LinearRegression()
    model.fit(X, y)

    # Generate forecast days
    last_day = team_data['day_num'].max()
    future_days = np.arange(
        last_day + 1,
        last_day + days_ahead + 1
    ).reshape(-1, 1)

    forecast = model.predict(future_days)
    forecast = np.maximum(forecast, 0)  # no negative spend

    # Generate future dates
    last_date = team_data['usage_date'].max()
    future_dates = [
        last_date + timedelta(days=i+1)
        for i in range(days_ahead)
    ]

    return future_dates, forecast, model.coef_[0], model.intercept_


def generate_scenarios(daily_df, budget_df, db_path="data/cloudlens.db"):
    """
    Scenario 1 (BAU): If current spending trend continues.
    Scenario 2 (Optimized): If AI savings recommendations applied (25% reduction).
    """
    print("\n" + "=" * 60)
    print("CLOUDLENS AI — BUDGET FORECAST ENGINE")
    print("=" * 60)

    teams = daily_df['team'].unique()
    budget_lookup = dict(
        zip(budget_df['team'], budget_df['monthly_budget_inr'])
    )
    mac_lookup = dict(zip(budget_df['team'], budget_df['mac_id'])) \
        if 'mac_id' in budget_df.columns \
        else {}

    scenario_rows = []
    alert_rows = []

    for team in teams:
        budget = budget_lookup.get(team, 0)
        if budget == 0:
            continue

        result = forecast_team_spend(daily_df, team, days_ahead=30)
        if result[0] is None:
            continue

        future_dates, forecast_bau, slope, intercept = result

        # Scenario 1: Business As Usual
        projected_monthly_bau = float(np.sum(forecast_bau))

        # Scenario 2: Optimized (apply 25% reduction from AI recs)
        forecast_optimized = forecast_bau * 0.75
        projected_monthly_optimized = float(np.sum(forecast_optimized))

        # Budget breach detection
        bau_breach = projected_monthly_bau > budget
        opt_breach = projected_monthly_optimized > budget

        # Days until breach (BAU scenario)
        cumsum = np.cumsum(forecast_bau)
        breach_days = None
        for i, cs in enumerate(cumsum):
            if cs >= budget:
                breach_days = i + 1
                break

        # Trend direction
        if slope > 50:
            trend = "Increasing rapidly"
        elif slope > 10:
            trend = "Increasing steadily"
        elif slope > -10:
            trend = "Stable"
        else:
            trend = "Decreasing"

        mac_id = mac_lookup.get(team, "")

        scenario_rows.append({
            "mac_id":                     mac_id,
            "team":                       team,
            "monthly_budget_inr":         budget,
            "projected_bau_inr":          round(projected_monthly_bau, 2),
            "projected_optimized_inr":    round(projected_monthly_optimized, 2),
            "bau_vs_budget_pct":          round(projected_monthly_bau / budget * 100, 1),
            "optimized_vs_budget_pct":    round(projected_monthly_optimized / budget * 100, 1),
            "bau_breach":                 bau_breach,
            "optimized_breach":           opt_breach,
            "breach_day_bau":             breach_days,
            "spend_trend":                trend,
            "daily_slope_inr":            round(float(slope), 2),
        })

        # Generate alerts
        if bau_breach:
            severity = "CRITICAL" if projected_monthly_bau > budget * 1.2 \
                else "WARNING"
            alert_rows.append({
                "mac_id":      mac_id,
                "team":        team,
                "alert_type":  "Budget Breach Projected",
                "severity":    severity,
                "message":     (
                    f"{team} (MAC: {mac_id}) is projected to spend "
                    f"₹{projected_monthly_bau:,.0f} this month against "
                    f"a budget of ₹{budget:,.0f} "
                    f"({round(projected_monthly_bau/budget*100,1)}%). "
                    f"Breach expected in {breach_days} days."
                    if breach_days else
                    f"{team} (MAC: {mac_id}) is projected to spend "
                    f"₹{projected_monthly_bau:,.0f} against "
                    f"budget ₹{budget:,.0f} — over by "
                    f"₹{projected_monthly_bau - budget:,.0f}."
                ),
                "projected_spend_inr":    round(projected_monthly_bau, 2),
                "budget_inr":             budget,
                "pct_over_budget":        round(
                    (projected_monthly_bau - budget) / budget * 100, 1
                ),
            })

    scenarios_df = pd.DataFrame(scenario_rows)
    alerts_df = pd.DataFrame(alert_rows)

    # Print results
    print("\n=== SCENARIO 1: BUSINESS AS USUAL (No changes) ===")
    bau_view = scenarios_df[[
        'mac_id', 'team', 'monthly_budget_inr',
        'projected_bau_inr', 'bau_vs_budget_pct', 'bau_breach', 'spend_trend'
    ]].copy()
    print(bau_view.to_string(index=False))

    print("\n=== SCENARIO 2: OPTIMIZED (AI savings applied — 25% reduction) ===")
    opt_view = scenarios_df[[
        'mac_id', 'team', 'monthly_budget_inr',
        'projected_optimized_inr', 'optimized_vs_budget_pct', 'optimized_breach'
    ]].copy()
    print(opt_view.to_string(index=False))

    print(f"\n=== BUDGET ALERTS ({len(alerts_df)} teams at risk) ===")
    if not alerts_df.empty:
        for _, alert in alerts_df.iterrows():
            print(f"\n[{alert['severity']}] {alert['message']}")
    else:
        print("No teams projected to breach budget in next 30 days.")

    # Save to DuckDB
    write_conn = duckdb.connect(db_path)

    write_conn.execute("DROP TABLE IF EXISTS budget_forecast")
    write_conn.execute("""
        CREATE TABLE budget_forecast AS
        SELECT * FROM scenarios_df
    """)
    print(f"\nSaved {len(scenarios_df)} team forecasts to budget_forecast table")

    write_conn.execute("DROP TABLE IF EXISTS budget_alerts")
    if not alerts_df.empty:
        write_conn.execute("""
            CREATE TABLE budget_alerts AS
            SELECT * FROM alerts_df
        """)
    else:
        write_conn.execute("""
            CREATE TABLE budget_alerts (
                mac_id VARCHAR, team VARCHAR,
                alert_type VARCHAR, severity VARCHAR,
                message VARCHAR, projected_spend_inr DOUBLE,
                budget_inr DOUBLE, pct_over_budget DOUBLE
            )
        """)
    print(f"Saved {len(alerts_df)} alerts to budget_alerts table")

    write_conn.close()
    return scenarios_df, alerts_df


def run_forecast(db_path="data/cloudlens.db"):
    """Main entry point — load data, run scenarios, save results."""
    daily_df = load_team_spending_history(db_path)
    budget_df = load_budget_limits(db_path)
    scenarios_df, alerts_df = generate_scenarios(
        daily_df, budget_df, db_path
    )

    print("\n=== SUMMARY ===")
    total_bau = scenarios_df['projected_bau_inr'].sum()
    total_opt = scenarios_df['projected_optimized_inr'].sum()
    total_budget = scenarios_df['monthly_budget_inr'].sum()
    teams_at_risk = scenarios_df['bau_breach'].sum()

    print(f"Total projected spend (BAU):       ₹{total_bau:,.0f}")
    print(f"Total projected spend (Optimized): ₹{total_opt:,.0f}")
    print(f"Total budget across all teams:     ₹{total_budget:,.0f}")
    print(f"Potential savings from AI recs:    ₹{total_bau - total_opt:,.0f}")
    print(f"Teams at risk of budget breach:    {teams_at_risk}")
    print(f"\n✅ Forecast complete.")

    return scenarios_df, alerts_df


if __name__ == "__main__":
    run_forecast()