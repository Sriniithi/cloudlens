import streamlit as st
import duckdb
import pandas as pd
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))
from ai_engine.gemini_engine import get_ai_response

# ── Page Config ───────────────────────────────────────────
st.set_page_config(
    page_title="CloudLens AI — FinOps Chat",
    page_icon="☁️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Custom CSS ────────────────────────────────────────────
st.markdown("""
<style>
    .main { background-color: #F4F6F9; }
    .stChatMessage { border-radius: 12px; margin-bottom: 8px; }
    .metric-card {
        background: white;
        border-radius: 10px;
        padding: 20px;
        border-left: 4px solid #1F3864;
        margin-bottom: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .alert-critical {
        background: #FFEBEE;
        border-left: 4px solid #C62828;
        border-radius: 8px;
        padding: 12px;
        margin: 6px 0;
    }
    .alert-warning {
        background: #FFF8E1;
        border-left: 4px solid #F9A825;
        border-radius: 8px;
        padding: 12px;
        margin: 6px 0;
    }
    h1 { color: #1F3864 !important; }
    .sidebar-title { color: #1F3864; font-weight: bold; font-size: 18px; }
</style>
""", unsafe_allow_html=True)

DB_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'data', 'cloudlens.db'
)

# ── DB Connection ─────────────────────────────────────────
@st.cache_resource
def get_db_connection():
    return duckdb.connect(DB_PATH, read_only=True)

def run_query(sql):
    try:
        conn = duckdb.connect(DB_PATH, read_only=True)
        result = conn.execute(sql).df()
        conn.close()
        return result, None
    except Exception as e:
        return None, str(e)

# ── SQL Generator ─────────────────────────────────────────
def question_to_sql(question):
    """
    Match question to a pre-built SQL template first.
    Only call AI for SQL generation if no template matches.
    """
    q = question.lower().strip()

    # ── Template library ──────────────────────────────────
    templates = {
        # Budget & breach
        ("over budget", "breach", "exceed budget",
         "at risk", "critical"):
            """SELECT mac_id, team, monthly_budget_inr,
                      projected_bau_inr,
                      ROUND(bau_vs_budget_pct,1) as pct_of_budget,
                      spend_trend
               FROM budget_forecast
               WHERE bau_breach = true
               ORDER BY bau_vs_budget_pct DESC""",

        # Highest spend / most spend / top spending
        ("highest spend", "most spend", "top spend",
         "spent the most", "highest cost", "most expensive"):
            """SELECT mac_id, team,
                      ROUND(SUM(total_cost_inr),2) as total_spend
               FROM team_daily_costs
               GROUP BY mac_id, team
               ORDER BY total_spend DESC
               LIMIT 5""",

        # January spend
        ("january", "jan", "2026-01"):
            """SELECT team, mac_id,
                      ROUND(SUM(total_cost_inr),2) as total_spend
               FROM team_daily_costs
               WHERE usage_date >= '2026-01-01'
               AND usage_date <= '2026-01-31'
               GROUP BY team, mac_id
               ORDER BY total_spend DESC""",

        # February spend
        ("february", "feb", "2026-02"):
            """SELECT team, mac_id,
                      ROUND(SUM(total_cost_inr),2) as total_spend
               FROM team_daily_costs
               WHERE usage_date >= '2026-02-01'
               AND usage_date <= '2026-02-28'
               GROUP BY team, mac_id
               ORDER BY total_spend DESC""",

        # March spend
        ("march", "mar", "2026-03"):
            """SELECT team, mac_id,
                      ROUND(SUM(total_cost_inr),2) as total_spend
               FROM team_daily_costs
               WHERE usage_date >= '2026-03-01'
               AND usage_date <= '2026-03-31'
               GROUP BY team, mac_id
               ORDER BY total_spend DESC""",

        # AI recommendations / savings
        ("recommendation", "saving", "optimize",
         "ai suggest", "reduce cost", "cut cost"):
            """SELECT pattern, mac_id,
                      ROUND(estimated_savings_inr,2) as savings,
                      candidate_count
               FROM ai_recommendations
               ORDER BY savings DESC""",

        # MAC level
        ("mac", "managed account", "which mac"):
            """SELECT mac_id,
                      ROUND(SUM(total_cost_inr),2) as total_spend
               FROM team_daily_costs
               GROUP BY mac_id
               ORDER BY total_spend DESC""",

        # Category breakdown
        ("category", "compute", "storage",
         "networking", "data service"):
            """SELECT resource_category,
                      ROUND(SUM(total_cost_inr),2) as total_spend
               FROM team_daily_costs
               GROUP BY resource_category
               ORDER BY total_spend DESC""",

        # Anomaly / spike
        ("anomaly", "spike", "unusual", "abnormal", "sudden"):
            """SELECT detection_date, mac_id, team,
                      category, daily_cost, rolling_mean,
                      pct_deviation, direction
               FROM anomaly_detections
               ORDER BY pct_deviation DESC
               LIMIT 10""",

        # Budget forecast
        ("forecast", "predict", "next month", "projection"):
            """SELECT mac_id, team, monthly_budget_inr,
                      projected_bau_inr,
                      projected_optimized_inr,
                      ROUND(bau_vs_budget_pct,1) as pct_used,
                      spend_trend
               FROM budget_forecast
               ORDER BY bau_vs_budget_pct DESC""",

        # ML team specifically
        ("ml team", "machine learning team"):
            """SELECT usage_date, category,
                      ROUND(SUM(total_cost_inr),2) as daily_spend
               FROM team_daily_costs
               WHERE team = 'ML'
               GROUP BY usage_date, category
               ORDER BY usage_date DESC
               LIMIT 30""",

        # Compare teams
        ("compare devops", "devops vs", "devops and"):
            """SELECT team, mac_id,
                      ROUND(SUM(total_cost_inr),2) as total_spend
               FROM team_daily_costs
               WHERE team IN ('DevOps', 'ML', 'Platform',
                              'Infrastructure')
               GROUP BY team, mac_id
               ORDER BY total_spend DESC""",

        # Weekly spend
        ("last week", "this week", "weekly"):
            """SELECT team,
                      ROUND(SUM(total_cost_inr),2) as week_spend
               FROM team_daily_costs
               WHERE usage_date >= '2026-03-25'
               AND usage_date <= '2026-03-31'
               GROUP BY team
               ORDER BY week_spend DESC""",

        # Budget summary
        ("budget", "budget usage", "budget utilization"):
            """SELECT f.mac_id, f.team,
                      f.monthly_budget_inr,
                      f.projected_bau_inr,
                      ROUND(f.bau_vs_budget_pct,1) as pct_used,
                      f.bau_breach
               FROM budget_forecast f
               ORDER BY f.bau_vs_budget_pct DESC""",

        # Show all tables / data
        ("show all", "all teams", "all data",
         "total spend", "overall"):
            """SELECT team, mac_id,
                      ROUND(SUM(total_cost_inr),2) as total_spend
               FROM team_daily_costs
               GROUP BY team, mac_id
               ORDER BY total_spend DESC""",
    }

    # Match question to template
    for keywords, sql in templates.items():
        if any(kw in q for kw in keywords):
            return sql

    # Fallback: try Ollama for edge cases
    schema = """
Database tables:
- team_daily_costs(usage_date, mac_id, team, resource_category, total_cost_inr)
- budget_forecast(mac_id, team, monthly_budget_inr, projected_bau_inr, bau_vs_budget_pct, bau_breach)
- budget_alerts(mac_id, team, severity, message, projected_spend_inr, budget_inr)
- ai_recommendations(pattern, mac_id, estimated_savings_inr, candidate_count)
- anomaly_detections(detection_date, mac_id, team, category, daily_cost, pct_deviation, direction)
- attributed_costs(usage_date, mac_id, attributed_team, category, cost_inr)

Return ONLY valid DuckDB SQL. No explanation. No markdown.
"""
    prompt = f'{schema}\nQuestion: "{question}"\nSQL:'
    sql = get_ai_response(prompt, mode="ollama")
    sql = sql.strip()
    for line in sql.split("\n"):
        line = line.strip()
        if line.upper().startswith("SELECT"):
            return sql
    return None

def generate_answer(question, sql, result_df):
    if len(result_df) <= 20:
        data_str = result_df.to_string(index=False)
    else:
        extra = len(result_df) - 10
        data_str = result_df.head(10).to_string(index=False)
        data_str = data_str + "\n... and " + str(extra) + " more rows"

    prompt = f"""
You are CloudLens AI, a FinOps assistant for Psiog Digital.
You help engineering and finance teams understand Azure cloud costs
across 8 MACs and 16 teams.

The user asked: "{question}"

The SQL query returned this data:
{data_str}

Write a clear, concise, business-friendly answer in 2-3 sentences.
Include specific numbers from the data.
If costs are high, suggest looking at the AI recommendations.
Do not mention SQL or technical details.
"""
    return get_ai_response(prompt, mode="ollama")

# ── Sidebar ───────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div class="sidebar-title">☁️ CloudLens AI</div>',
                unsafe_allow_html=True)
    st.markdown("**FinOps Analytics Engine**")
    st.markdown("*Psiog Digital · Azure Cost Intelligence*")
    st.divider()

    st.markdown("### 📊 Quick Stats")
    df_total, _ = run_query(
        "SELECT ROUND(SUM(cost_inr),2) as total FROM attributed_costs"
    )
    df_teams, _ = run_query(
        "SELECT COUNT(DISTINCT attributed_team) as teams FROM attributed_costs"
    )
    df_macs, _ = run_query(
        "SELECT COUNT(DISTINCT mac_id) as macs FROM attributed_costs"
    )
    df_savings, _ = run_query(
        "SELECT ROUND(SUM(estimated_savings_inr),2) as savings FROM ai_recommendations"
    )

    if df_total is not None:
        st.metric("Total Spend (90 days)",
                  f"₹{df_total['total'].iloc[0]:,.0f}")
    if df_teams is not None:
        st.metric("Teams Tracked",
                  f"{df_teams['teams'].iloc[0]}")
    if df_macs is not None:
        st.metric("MACs", f"{df_macs['macs'].iloc[0]}")
    if df_savings is not None:
        st.metric("AI Identified Savings",
                  f"₹{df_savings['savings'].iloc[0]:,.0f}",
                  delta="Recoverable",
                  delta_color="normal")

    st.divider()
    st.markdown("### 💡 Try Asking")
    sample_questions = [
        "Which team spent the most in January?",
        "Which MAC has the highest total spend?",
        "Show me teams that are over budget",
        "What are the AI optimization recommendations?",
        "Which category costs the most across all teams?",
        "Show budget forecast for MAC-07",
        "Which teams are at critical risk?",
        "Compare DevOps and ML spending",
    ]
    for q in sample_questions:
        if st.button(q, use_container_width=True, key=f"btn_{q[:20]}"):
            st.session_state.prefill_question = q

    st.divider()
    ai_mode = st.selectbox(
        "AI Engine",
        ["ollama", "gemini"],
        index=0,
        help="Ollama = local (free). Gemini = API (requires key)."
    )
    st.session_state.ai_mode = ai_mode

# ── Main Area ─────────────────────────────────────────────
st.title("☁️ CloudLens AI — FinOps Chat")
st.markdown(
    "Ask questions about Psiog Digital's Azure cloud costs in plain English. "
    "Powered by local AI + DuckDB."
)

tab1, tab2, tab3, tab4 = st.tabs([
    "💬 Ask a Question",
    "⚡ Budget Alerts",
    "🤖 AI Recommendations",
    "📰 Weekly Narrative"
])

# ── TAB 1: Chat ───────────────────────────────────────────
with tab1:
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if "dataframe" in msg:
                st.dataframe(msg["dataframe"],
                             use_container_width=True)

    prefill = st.session_state.pop("prefill_question", None)

    question = st.chat_input(
        "Ask about Azure costs, team spend, budgets, or savings..."
    )
    if prefill:
        question = prefill

    if question:
        st.session_state.messages.append({
            "role": "user", "content": question
        })
        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                mode = st.session_state.get("ai_mode", "ollama")

                sql = question_to_sql(question)

                result_df, error = run_query(sql)

                if error or result_df is None:
                    fallback_prompt = f"""
You are CloudLens AI, a FinOps assistant.
The user asked: "{question}"
You could not generate a valid SQL query for this.
Provide a helpful general answer about Azure FinOps,
Psiog's 8 MACs, 16 teams, or cost management best practices.
Keep it to 2-3 sentences.
"""
                    answer = get_ai_response(
                        fallback_prompt, mode=mode
                    )
                    st.markdown(answer)
                    st.session_state.messages.append({
                        "role": "assistant", "content": answer
                    })
                else:
                    answer = generate_answer(
                        question, sql, result_df
                    )
                    st.markdown(answer)
                    if len(result_df) > 0:
                        st.dataframe(
                            result_df, use_container_width=True
                        )
                    with st.expander("🔍 SQL Query Used"):
                        st.code(sql, language="sql")

                    msg_data = {
                        "role": "assistant",
                        "content": answer
                    }
                    if len(result_df) > 0:
                        msg_data["dataframe"] = result_df
                    st.session_state.messages.append(msg_data)

    if st.button("🗑️ Clear conversation"):
        st.session_state.messages = []
        st.rerun()

# ── TAB 2: Budget Alerts ──────────────────────────────────
with tab2:
    st.subheader("⚡ Live Budget Alerts")
    st.markdown(
        "Teams projected to breach their monthly budget "
        "based on current spend trajectory."
    )

    alerts_df, err = run_query(
        "SELECT * FROM budget_alerts ORDER BY pct_over_budget DESC"
    )

    if err or alerts_df is None or len(alerts_df) == 0:
        st.info("No budget alerts at this time.")
    else:
        col1, col2 = st.columns(2)
        critical = alerts_df[
            alerts_df['severity'] == 'CRITICAL'
        ]
        warning = alerts_df[
            alerts_df['severity'] == 'WARNING'
        ]
        with col1:
            st.metric("🔴 Critical Alerts",
                      len(critical),
                      delta="Immediate action required",
                      delta_color="inverse")
        with col2:
            st.metric("🟡 Warning Alerts",
                      len(warning),
                      delta="Monitor closely",
                      delta_color="off")

        st.divider()
        for _, alert in alerts_df.iterrows():
            css_class = (
                "alert-critical"
                if alert['severity'] == 'CRITICAL'
                else "alert-warning"
            )
            icon = "🔴" if alert['severity'] == 'CRITICAL' else "🟡"
            st.markdown(f"""
<div class="{css_class}">
<strong>{icon} {alert['team']} ({alert['mac_id']})</strong>
— {alert['severity']}<br>
{alert['message']}<br>
<small>Projected: ₹{alert['projected_spend_inr']:,.0f}
| Budget: ₹{alert['budget_inr']:,.0f}
| Over by: {alert['pct_over_budget']:.1f}%</small>
</div>
""", unsafe_allow_html=True)

# ── TAB 3: AI Recommendations ────────────────────────────
with tab3:
    st.subheader("🤖 AI Optimization Recommendations")
    st.markdown(
        "Cost-saving opportunities identified by CloudLens AI "
        "across your Azure infrastructure."
    )

    recs_df, err = run_query(
        "SELECT * FROM ai_recommendations ORDER BY estimated_savings_inr DESC"
    )

    if err or recs_df is None or len(recs_df) == 0:
        st.info(
            "No recommendations available. "
            "Run the AI engine first: python ai_engine/gemini_engine.py"
        )
    else:
        total_savings = recs_df['estimated_savings_inr'].sum()
        st.metric(
            "💰 Total Estimated Savings",
            f"₹{total_savings:,.0f}",
            delta="Across all 3 patterns",
            delta_color="normal"
        )
        st.divider()

        pattern_icons = {
            "right-sizing":  "📐",
            "idle-cleanup":  "🗑️",
            "reservation":   "📅"
        }
        pattern_colors = {
            "right-sizing":  "#1F3864",
            "idle-cleanup":  "#2E5FA3",
            "reservation":   "#1B5E20"
        }

        for _, rec in recs_df.iterrows():
            icon = pattern_icons.get(rec['pattern'], "💡")
            color = pattern_colors.get(rec['pattern'], "#333")
            with st.expander(
                f"{icon} {rec['pattern'].upper()} — "
                f"₹{rec['estimated_savings_inr']:,.0f} savings potential",
                expanded=True
            ):
                col1, col2 = st.columns([2, 1])
                with col1:
                    st.markdown(
                        f"**AI Recommendation:**\n\n"
                        f"{rec.get('recommendation_summary', 'See details.')}"
                    )
                with col2:
                    st.metric(
                        "Candidates",
                        rec['candidate_count']
                    )
                    st.metric(
                        "MAC",
                        rec.get('mac_id', 'Multiple')
                    )
                    st.metric(
                        "Est. Savings",
                        f"₹{rec['estimated_savings_inr']:,.0f}"
                    )

# ── TAB 4: Weekly Narrative ───────────────────────────────
with tab4:
    st.subheader("📰 AI-Generated Weekly Cost Narrative")
    st.markdown(
        "Executive summary of this week's Azure cloud "
        "spending — written by CloudLens AI."
    )

    narrative_df, err = run_query(
        "SELECT * FROM weekly_narratives ORDER BY generated_at DESC LIMIT 1"
    )

    if err or narrative_df is None or len(narrative_df) == 0:
        st.info(
            "No weekly narrative yet. "
            "Run: python ai_engine/anomaly_engine.py"
        )
    else:
        row = narrative_df.iloc[0]
        st.markdown(f"**Week ending:** {row['week_ending']}")
        st.markdown(f"**Generated:** {row['generated_at']}")
        st.divider()
        st.markdown(
            f"""
<div style="background:white; border-radius:10px; padding:24px;
border-left:4px solid #1F3864; box-shadow:0 2px 8px rgba(0,0,0,0.1);">
{row['narrative']}
</div>
""",
            unsafe_allow_html=True
        )

    st.divider()
    st.subheader("🔍 Anomaly Log")
    anomaly_df, err2 = run_query(
        "SELECT * FROM anomaly_detections ORDER BY pct_deviation DESC"
    )
    if err2 or anomaly_df is None or len(anomaly_df) == 0:
        st.info("No anomalies detected.")
    else:
        st.dataframe(
            anomaly_df[[
                'detection_date', 'mac_id', 'team',
                'category', 'daily_cost', 'rolling_mean',
                'pct_deviation', 'direction'
            ]],
            use_container_width=True
        )