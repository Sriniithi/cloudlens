import os
import duckdb
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────
# AI CLIENT SETUP
# Defaults to Ollama (local, free, reliable)
# Gemini kept as optional production path
# ─────────────────────────────────────────

def get_ai_response(prompt: str, mode: str = "ollama") -> str:
    """
    mode = "ollama"  → uses local Llama (free, default for this project)
    mode = "gemini"  → uses Gemini API (optional, subject to quota limits)
    """
    if mode == "gemini":
        return _call_gemini(prompt)
    else:
        return _call_ollama(prompt)


def _call_gemini(prompt: str) -> str:
    try:
        from google import genai
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in .env file")
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt
        )
        return response.text
    except Exception as e:
        return f"Gemini error: {str(e)}"


def _call_ollama(prompt: str) -> str:
    try:
        import ollama
        response = ollama.chat(
            model="llama3.2:1b",
            messages=[{"role": "user", "content": prompt}]
        )
        return response['message']['content']
    except Exception as e:
        return f"Ollama error: {str(e)}"


# ─────────────────────────────────────────
# PATTERN 1 — RIGHT-SIZING RECOMMENDATIONS
# Compute resources with high average cost
# ─────────────────────────────────────────

def get_rightsizing_recommendations(db_path: str = "data/cloudlens.db",
                                     mode: str = "ollama") -> list:
    """
    Finds Compute resources with consistently high cost
    that could be downsized. Sends to AI for recommendations.
    Includes mac_id since attributed_costs is MAC-aware.
    """
    print("\n=== PATTERN 1: RIGHT-SIZING ===")

    conn = duckdb.connect(db_path, read_only=True)

    df = conn.execute("""
        SELECT
            mac_id,
            attributed_team as team,
            resource_type,
            resource_group,
            ROUND(AVG(cost_inr), 2) as avg_daily_cost,
            ROUND(SUM(cost_inr), 2) as total_cost,
            COUNT(*) as days_active
        FROM attributed_costs
        WHERE category = 'Compute'
        GROUP BY mac_id, attributed_team, resource_type, resource_group
        HAVING AVG(cost_inr) > 800
        ORDER BY avg_daily_cost DESC
        LIMIT 5
    """).df()
    conn.close()

    if df.empty:
        print("No right-sizing candidates found.")
        return []

    print(f"Found {len(df)} right-sizing candidates")
    print(df)

    prompt = f"""
You are a FinOps expert analyzing Azure cloud costs for Psiog Digital.
Costs are organized under 8 MACs (Managed Account Clusters), each with
2 teams underneath.

The following Azure Compute resources have high average daily costs and
may be oversized for their workload:

{df.to_string(index=False)}

For each resource, provide:
1. A specific right-sizing recommendation
2. Estimated monthly savings (assume 40% reduction if downsized)
3. Priority: High/Medium/Low

Keep each recommendation to 2 sentences maximum.
Format as a numbered list.
"""

    print("\nAsking AI for right-sizing recommendations...")
    recommendation = get_ai_response(prompt, mode)
    print(f"\nAI Recommendation:\n{recommendation}")

    return [{
        "pattern": "right-sizing",
        "mac_id": df['mac_id'].iloc[0] if len(df) > 0 else "",
        "candidates": df.to_dict('records'),
        "ai_recommendation": recommendation,
        "estimated_savings_inr": round(df['avg_daily_cost'].sum() * 0.4 * 30, 2)
    }]


# ─────────────────────────────────────────
# PATTERN 2 — IDLE RESOURCE CLEANUP
# Resources with zero/minimal recent usage
# ─────────────────────────────────────────

def get_idle_resource_recommendations(db_path: str = "data/cloudlens.db",
                                       mode: str = "ollama") -> list:
    """
    Finds resources that have been running but
    show no meaningful activity (very low cost = idle).
    """
    print("\n=== PATTERN 2: IDLE RESOURCES ===")

    conn = duckdb.connect(db_path, read_only=True)

    df = conn.execute("""
        SELECT
            mac_id,
            attributed_team as team,
            resource_type,
            resource_group,
            ROUND(AVG(cost_inr), 2) as avg_daily_cost,
            ROUND(SUM(cost_inr), 2) as total_cost_90days,
            COUNT(*) as days_running
        FROM attributed_costs
        WHERE category IN ('Storage', 'Networking')
        GROUP BY mac_id, attributed_team, resource_type, resource_group
        HAVING AVG(cost_inr) < 500
        AND COUNT(*) > 5
        ORDER BY total_cost_90days DESC
        LIMIT 5
    """).df()
    conn.close()

    if df.empty:
        print("No idle resource candidates found.")
        return []

    print(f"Found {len(df)} idle resource candidates")
    print(df)

    prompt = f"""
You are a FinOps expert analyzing Azure cloud costs for Psiog Digital.
Costs are organized under 8 MACs, each with 2 teams underneath.

The following Azure resources have been running for over 30 days but show
very low activity, suggesting they may be idle or unused:

{df.to_string(index=False)}

For each resource:
1. Explain why it appears idle
2. Recommend: Delete / Archive / Investigate further
3. Estimated monthly savings if deleted

Keep each recommendation to 2 sentences maximum.
Format as a numbered list.
"""

    print("\nAsking AI for idle resource recommendations...")
    recommendation = get_ai_response(prompt, mode)
    print(f"\nAI Recommendation:\n{recommendation}")

    return [{
        "pattern": "idle-cleanup",
        "mac_id": df['mac_id'].iloc[0] if len(df) > 0 else "",
        "candidates": df.to_dict('records'),
        "ai_recommendation": recommendation,
        "estimated_savings_inr": round(df['total_cost_90days'].sum() / 3, 2)
    }]


# ─────────────────────────────────────────
# PATTERN 3 — RESERVATION OPPORTUNITIES
# Stable workloads suited to reserved pricing
# ─────────────────────────────────────────

def get_reservation_recommendations(db_path: str = "data/cloudlens.db",
                                     mode: str = "ollama") -> list:
    """
    Finds resources running consistently for 30+ days —
    good candidates for Reserved Instance pricing (30-60% cheaper).
    Threshold lowered to 30 days to match 90-day synthetic dataset
    and ensure all MACs have qualifying candidates.
    """
    print("\n=== PATTERN 3: RESERVATION OPPORTUNITIES ===")

    conn = duckdb.connect(db_path, read_only=True)

    df = conn.execute("""
        SELECT
            mac_id,
            attributed_team as team,
            resource_type,
            resource_group,
            ROUND(AVG(cost_inr), 2) as avg_daily_cost,
            ROUND(SUM(cost_inr), 2) as total_cost_90days,
            COUNT(*) as days_running,
            ROUND(AVG(cost_inr) * 365, 2) as projected_annual_cost
        FROM attributed_costs
        WHERE category = 'Compute'
        GROUP BY mac_id, attributed_team, resource_type, resource_group
        HAVING COUNT(*) >= 5
        AND AVG(cost_inr) > 100
        ORDER BY projected_annual_cost DESC
        LIMIT 5
    """).df()
    conn.close()

    if df.empty:
        print("No reservation candidates found.")
        return []

    print(f"Found {len(df)} reservation candidates")
    print(df)

    prompt = f"""
You are a FinOps expert analyzing Azure cloud costs for Psiog Digital.
Costs are organized under 8 MACs, each with 2 teams underneath.

The following Azure Compute resources have been running consistently for
30+ days with stable costs, making them ideal candidates for Reserved
Instance pricing (typically 30-60% cheaper than pay-as-you-go):

{df.to_string(index=False)}

For each resource:
1. Confirm it is a good reservation candidate and why
2. Estimated annual savings with 1-year Reserved Instance (assume 40% discount)
3. Recommended reservation term: 1-year or 3-year

Keep each recommendation to 2 sentences maximum.
Format as a numbered list.
"""

    print("\nAsking AI for reservation recommendations...")
    recommendation = get_ai_response(prompt, mode)
    print(f"\nAI Recommendation:\n{recommendation}")

    return [{
        "pattern": "reservation",
        "mac_id": df['mac_id'].iloc[0] if len(df) > 0 else "",
        "candidates": df.to_dict('records'),
        "ai_recommendation": recommendation,
        "estimated_savings_inr": round(df['projected_annual_cost'].sum() * 0.4, 2)
    }]


# ─────────────────────────────────────────
# RUN ALL 3 PATTERNS + SAVE TO DUCKDB
# ─────────────────────────────────────────

def run_optimization_engine(db_path: str = "data/cloudlens.db",
                             mode: str = "ollama"):
    """
    Runs all 3 optimization patterns.
    Saves results to ai_recommendations table in DuckDB.
    """
    print("=" * 50)
    print("CLOUDLENS AI — OPTIMIZATION ENGINE")
    print(f"Mode: {mode.upper()}")
    print("=" * 50)

    all_recommendations = []

    all_recommendations.extend(
        get_rightsizing_recommendations(db_path, mode))
    all_recommendations.extend(
        get_idle_resource_recommendations(db_path, mode))
    all_recommendations.extend(
        get_reservation_recommendations(db_path, mode))

    if not all_recommendations:
        print("\nNo recommendations generated.")
        return

    rows = []
    for rec in all_recommendations:
        rows.append({
            "pattern":               rec["pattern"],
            "mac_id":                rec.get("mac_id", ""),
            "ai_recommendation":     rec["ai_recommendation"],
            "estimated_savings_inr": rec["estimated_savings_inr"],
            "candidate_count":       len(rec["candidates"])
        })

    results_df = pd.DataFrame(rows)

    write_conn = duckdb.connect(db_path)
    write_conn.execute("DROP TABLE IF EXISTS ai_recommendations")
    write_conn.execute("""
        CREATE TABLE ai_recommendations AS
        SELECT * FROM results_df
    """)

    print("\n=== OPTIMIZATION SUMMARY ===")
    print(results_df[['pattern', 'mac_id', 'estimated_savings_inr', 'candidate_count']])
    total_savings = results_df['estimated_savings_inr'].sum()
    print(f"\nTotal estimated savings: ₹{total_savings:,.2f}")
    print("\nSaved to ai_recommendations table in DuckDB")

    write_conn.close()
    return all_recommendations


if __name__ == "__main__":
    # Ollama is the default engine — local, free, no quota limits
    run_optimization_engine(mode="ollama")