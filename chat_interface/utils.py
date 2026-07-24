import duckdb
import os
import sys

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))
from ai_engine.gemini_engine import get_ai_response

DB_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'data', 'cloudlens.db'
)


def run_query(sql):
    try:
        conn = duckdb.connect(DB_PATH, read_only=True)
        result = conn.execute(sql).df()
        conn.close()
        return result, None
    except Exception as e:
        return None, str(e)


def question_to_sql(question):
    q = question.lower().strip()

    templates = {
        ("over budget", "breach", "exceed budget",
         "at risk", "critical"):
            """SELECT mac_id, team, monthly_budget_inr,
                      projected_bau_inr,
                      ROUND(bau_vs_budget_pct,1) as pct_of_budget,
                      spend_trend
               FROM budget_forecast
               WHERE bau_breach = true
               ORDER BY bau_vs_budget_pct DESC""",

        ("highest spend", "most spend", "top spend",
         "spent the most", "highest cost", "most expensive"):
            """SELECT mac_id, team,
                      ROUND(SUM(total_cost_inr),2) as total_spend
               FROM team_daily_costs
               GROUP BY mac_id, team
               ORDER BY total_spend DESC
               LIMIT 5""",

        ("january", "jan", "2026-01"):
            """SELECT team, mac_id,
                      ROUND(SUM(total_cost_inr),2) as total_spend
               FROM team_daily_costs
               WHERE usage_date >= '2026-01-01'
               AND usage_date <= '2026-01-31'
               GROUP BY team, mac_id
               ORDER BY total_spend DESC""",

        ("february", "feb", "2026-02"):
            """SELECT team, mac_id,
                      ROUND(SUM(total_cost_inr),2) as total_spend
               FROM team_daily_costs
               WHERE usage_date >= '2026-02-01'
               AND usage_date <= '2026-02-28'
               GROUP BY team, mac_id
               ORDER BY total_spend DESC""",

        ("march", "mar", "2026-03"):
            """SELECT team, mac_id,
                      ROUND(SUM(total_cost_inr),2) as total_spend
               FROM team_daily_costs
               WHERE usage_date >= '2026-03-01'
               AND usage_date <= '2026-03-31'
               GROUP BY team, mac_id
               ORDER BY total_spend DESC""",

        ("recommendation", "saving", "optimize",
         "ai suggest", "reduce cost", "cut cost"):
            """SELECT pattern, mac_id,
                      ROUND(estimated_savings_inr,2) as savings,
                      candidate_count
               FROM ai_recommendations
               ORDER BY savings DESC""",

        ("mac", "managed account", "which mac"):
            """SELECT mac_id,
                      ROUND(SUM(total_cost_inr),2) as total_spend
               FROM team_daily_costs
               GROUP BY mac_id
               ORDER BY total_spend DESC""",

        ("category", "compute", "storage",
         "networking", "data service"):
            """SELECT resource_category,
                      ROUND(SUM(total_cost_inr),2) as total_spend
               FROM team_daily_costs
               GROUP BY resource_category
               ORDER BY total_spend DESC""",

        ("anomaly", "spike", "unusual", "abnormal", "sudden"):
            """SELECT detection_date, mac_id, team,
                      category, daily_cost, rolling_mean,
                      pct_deviation, direction
               FROM anomaly_detections
               ORDER BY pct_deviation DESC
               LIMIT 10""",

        ("forecast", "predict", "next month", "projection"):
            """SELECT mac_id, team, monthly_budget_inr,
                      projected_bau_inr,
                      projected_optimized_inr,
                      ROUND(bau_vs_budget_pct,1) as pct_used,
                      spend_trend
               FROM budget_forecast
               ORDER BY bau_vs_budget_pct DESC""",

        ("weekly", "last week", "this week"):
            """SELECT team,
                      ROUND(SUM(total_cost_inr),2) as week_spend
               FROM team_daily_costs
               WHERE usage_date >= '2026-03-25'
               AND usage_date <= '2026-03-31'
               GROUP BY team
               ORDER BY week_spend DESC""",

        ("budget", "budget usage", "budget utilization"):
            """SELECT f.mac_id, f.team,
                      f.monthly_budget_inr,
                      f.projected_bau_inr,
                      ROUND(f.bau_vs_budget_pct,1) as pct_used,
                      f.bau_breach
               FROM budget_forecast f
               ORDER BY f.bau_vs_budget_pct DESC""",

        ("show all", "all teams", "all data",
         "total spend", "overall"):
            """SELECT team, mac_id,
                      ROUND(SUM(total_cost_inr),2) as total_spend
               FROM team_daily_costs
               GROUP BY team, mac_id
               ORDER BY total_spend DESC""",
    }

    for keywords, sql in templates.items():
        if any(kw in q for kw in keywords):
            return sql

    # Fallback to Ollama
    schema = """
Database tables:
- team_daily_costs(usage_date, mac_id, team, resource_category, total_cost_inr)
- budget_forecast(mac_id, team, monthly_budget_inr, projected_bau_inr, bau_vs_budget_pct, bau_breach)
- budget_alerts(mac_id, team, severity, message, projected_spend_inr, budget_inr)
- ai_recommendations(pattern, mac_id, estimated_savings_inr, candidate_count)
- anomaly_detections(detection_date, mac_id, team, category, daily_cost, pct_deviation, direction)
Return ONLY valid DuckDB SQL. No explanation. No markdown.
"""
    prompt = schema + '\nQuestion: "' + question + '"\nSQL:'
    sql = get_ai_response(prompt, mode="ollama")
    sql = sql.strip()
    if sql.upper().startswith("SELECT"):
        return sql
    return None


def generate_answer(question, sql, result_df):
    if len(result_df) <= 20:
        data_str = result_df.to_string(index=False)
    else:
        extra = len(result_df) - 10
        data_str = result_df.head(10).to_string(index=False)
        data_str = data_str + "\n... and " + str(extra) + " more rows"

    prompt = (
        "You are CloudLens AI, a FinOps assistant for Psiog Digital.\n"
        "The user asked: " + question + "\n\n"
        "The SQL query returned this data:\n" + data_str + "\n\n"
        "Write a clear, concise, business-friendly answer in 2-3 sentences. "
        "Include specific numbers. Do not mention SQL."
    )
    return get_ai_response(prompt, mode="ollama")