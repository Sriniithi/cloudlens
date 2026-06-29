import os
import duckdb
import pandas as pd
from dotenv import load_dotenv

load_dotenv()


def get_ai_response(prompt: str, mode: str = "gemini") -> str:
    if mode == "gemini":
        return _call_gemini(prompt)
    return _call_ollama(prompt)


def _call_gemini(prompt: str) -> str:
    try:
        import google.generativeai as genai
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise ValueError("GEMINI_API_KEY not in .env")
        genai.configure(api_key=key)
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Gemini error: {e}"


def _call_ollama(prompt: str) -> str:
    try:
        import ollama
        response = ollama.chat(
            model="llama3.2",
            messages=[{"role": "user", "content": prompt}]
        )
        return response['message']['content']
    except Exception as e:
        return f"Ollama error: {e}"


def get_rightsizing_recommendations(
    db_path="data/cloudlens.db", mode="gemini"
):
    print("\n=== PATTERN 1: RIGHT-SIZING ===")
    conn = duckdb.connect(db_path, read_only=True)
    df = conn.execute("""
        SELECT mac_id, attributed_team as team,
               resource_type, resource_group,
               ROUND(AVG(cost_inr), 2) as avg_daily_cost,
               ROUND(SUM(cost_inr), 2) as total_cost
        FROM attributed_costs
        WHERE category = 'Compute'
        GROUP BY mac_id, attributed_team,
                 resource_type, resource_group
        HAVING AVG(cost_inr) > 800
        ORDER BY avg_daily_cost DESC
        LIMIT 5
    """).df()
    conn.close()

    if df.empty:
        print("No candidates found.")
        return []

    print(df)
    prompt = f"""
You are a FinOps expert for Psiog Digital.
These Azure Compute resources have high average daily costs
and may be oversized. Each belongs to a MAC (team group):

{df.to_string(index=False)}

For each:
1. Right-sizing recommendation (2 sentences max)
2. Estimated monthly savings (assume 40% reduction)
3. Priority: High/Medium/Low
Format as numbered list.
"""
    rec = get_ai_response(prompt, mode)
    print(f"\nAI Recommendation:\n{rec}")
    return [{
        "pattern": "right-sizing",
        "mac_id": df['mac_id'].iloc[0] if len(df) > 0 else "",
        "candidates": df.to_dict('records'),
        "ai_recommendation": rec,
        "estimated_savings_inr": round(
            df['avg_daily_cost'].sum() * 0.4 * 30, 2)
    }]


def get_idle_resource_recommendations(
    db_path="data/cloudlens.db", mode="gemini"
):
    print("\n=== PATTERN 2: IDLE RESOURCES ===")
    conn = duckdb.connect(db_path, read_only=True)
    df = conn.execute("""
        SELECT mac_id, attributed_team as team,
               resource_type, resource_group,
               ROUND(AVG(cost_inr), 2) as avg_daily_cost,
               ROUND(SUM(cost_inr), 2) as total_cost_90days,
               COUNT(*) as days_running
        FROM attributed_costs
        WHERE category IN ('Storage', 'Networking')
        GROUP BY mac_id, attributed_team,
                 resource_type, resource_group
        HAVING AVG(cost_inr) < 200 AND COUNT(*) > 30
        ORDER BY total_cost_90days DESC
        LIMIT 5
    """).df()
    conn.close()

    if df.empty:
        print("No candidates found.")
        return []

    print(df)
    prompt = f"""
You are a FinOps expert for Psiog Digital.
These Azure resources have been running 30+ days
with very low activity — likely idle:

{df.to_string(index=False)}

For each:
1. Why it appears idle
2. Recommendation: Delete / Archive / Investigate
3. Estimated monthly savings if deleted
Format as numbered list.
"""
    rec = get_ai_response(prompt, mode)
    print(f"\nAI Recommendation:\n{rec}")
    return [{
        "pattern": "idle-cleanup",
        "mac_id": df['mac_id'].iloc[0] if len(df) > 0 else "",
        "candidates": df.to_dict('records'),
        "ai_recommendation": rec,
        "estimated_savings_inr": round(
            df['total_cost_90days'].sum() / 3, 2)
    }]


def get_reservation_recommendations(
    db_path="data/cloudlens.db", mode="gemini"
):
    print("\n=== PATTERN 3: RESERVATIONS ===")
    conn = duckdb.connect(db_path, read_only=True)
    df = conn.execute("""
        SELECT mac_id, attributed_team as team,
               resource_type, resource_group,
               ROUND(AVG(cost_inr), 2) as avg_daily_cost,
               ROUND(SUM(cost_inr), 2) as total_cost_90days,
               COUNT(*) as days_running,
               ROUND(AVG(cost_inr) * 365, 2) as projected_annual
        FROM attributed_costs
        WHERE category = 'Compute'
        GROUP BY mac_id, attributed_team,
                 resource_type, resource_group
        HAVING COUNT(*) >= 60 AND AVG(cost_inr) > 500
        ORDER BY projected_annual DESC
        LIMIT 5
    """).df()
    conn.close()

    if df.empty:
        print("No candidates found.")
        return []

    print(df)
    prompt = f"""
You are a FinOps expert for Psiog Digital.
These Azure Compute resources have run 60+ days
consistently — ideal for Reserved Instance pricing
(30–60% cheaper than pay-as-you-go):

{df.to_string(index=False)}

For each:
1. Confirm reservation suitability and why
2. Annual savings with 1-year Reserved Instance (40% discount)
3. Recommended term: 1-year or 3-year
Format as numbered list.
"""
    rec = get_ai_response(prompt, mode)
    print(f"\nAI Recommendation:\n{rec}")
    return [{
        "pattern": "reservation",
        "mac_id": df['mac_id'].iloc[0] if len(df) > 0 else "",
        "candidates": df.to_dict('records'),
        "ai_recommendation": rec,
        "estimated_savings_inr": round(
            df['projected_annual'].sum() * 0.4, 2)
    }]


def run_optimization_engine(
    db_path="data/cloudlens.db", mode="gemini"
):
    print("=" * 50)
    print("CLOUDLENS AI — OPTIMIZATION ENGINE")
    print(f"Mode: {mode.upper()}")
    print("=" * 50)

    all_recs = []
    all_recs.extend(
        get_rightsizing_recommendations(db_path, mode))
    all_recs.extend(
        get_idle_resource_recommendations(db_path, mode))
    all_recs.extend(
        get_reservation_recommendations(db_path, mode))

    if not all_recs:
        print("No recommendations generated.")
        return

    rows = [{
        "pattern":               r["pattern"],
        "mac_id":                r.get("mac_id", ""),
        "ai_recommendation":     r["ai_recommendation"],
        "estimated_savings_inr": r["estimated_savings_inr"],
        "candidate_count":       len(r["candidates"])
    } for r in all_recs]

    df_results = pd.DataFrame(rows)
    write_conn = duckdb.connect(db_path)
    write_conn.execute(
        "DROP TABLE IF EXISTS ai_recommendations")
    write_conn.execute("""
        CREATE TABLE ai_recommendations AS
        SELECT * FROM df_results
    """)

    print("\n=== OPTIMIZATION SUMMARY ===")
    print(df_results[['pattern', 'mac_id',
                       'estimated_savings_inr',
                       'candidate_count']])
    total = df_results['estimated_savings_inr'].sum()
    print(f"\n💰 Total estimated savings: ₹{total:,.2f}")
    write_conn.close()
    return all_recs


if __name__ == "__main__":
    run_optimization_engine(mode="gemini")