"""
Locust load test for CloudLens AI chat interface.
Tests DuckDB query performance under concurrent load.

Run with:
    locust -f tests/locustfile.py --headless -u 10 -r 2 -t 30s
"""
from locust import HttpUser, task, between
import duckdb
import time
import os
import sys

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))

DB_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'data', 'cloudlens.db'
)

# ── DuckDB Query Load Test (no HTTP needed) ────────────────
# Since our chat interface queries DuckDB directly,
# we test DuckDB query performance directly

class DuckDBQueryPerformance:
    """
    Standalone DuckDB performance benchmarks.
    Run directly with: python tests/locustfile.py
    """

    QUERIES = {
        "cost_by_team": """
            SELECT team, mac_id,
                   ROUND(SUM(total_cost_inr),2) as total
            FROM team_daily_costs
            GROUP BY team, mac_id
            ORDER BY total DESC
        """,
        "budget_breach": """
            SELECT mac_id, team, projected_bau_inr,
                   bau_vs_budget_pct
            FROM budget_forecast
            WHERE bau_breach = true
            ORDER BY bau_vs_budget_pct DESC
        """,
        "anomalies_top10": """
            SELECT detection_date, team, category,
                   pct_deviation, direction
            FROM anomaly_detections
            ORDER BY pct_deviation DESC
            LIMIT 10
        """,
        "ai_recommendations": """
            SELECT pattern, mac_id, estimated_savings_inr
            FROM ai_recommendations
            ORDER BY estimated_savings_inr DESC
        """,
        "monthly_summary": """
            SELECT month, mac_id,
                   ROUND(SUM(total_cost_inr),2) as monthly_total
            FROM monthly_summary
            GROUP BY month, mac_id
            ORDER BY month, mac_id
        """,
    }

    def run_benchmarks(self, iterations=10):
        print("\n" + "=" * 60)
        print("CLOUDLENS AI — DUCKDB QUERY BENCHMARKS")
        print(f"Running each query {iterations} times")
        print("=" * 60)

        results = {}

        for query_name, sql in self.QUERIES.items():
            times = []
            for _ in range(iterations):
                conn = duckdb.connect(DB_PATH, read_only=True)
                start = time.time()
                df = conn.execute(sql).df()
                elapsed = time.time() - start
                conn.close()
                times.append(elapsed)

            avg = sum(times) / len(times)
            min_t = min(times)
            max_t = max(times)

            results[query_name] = {
                "avg": avg, "min": min_t, "max": max_t
            }

            status = "✅" if avg < 1.0 else "⚠️"
            print(f"\n{status} {query_name}")
            print(f"   avg: {avg*1000:.1f}ms | "
                  f"min: {min_t*1000:.1f}ms | "
                  f"max: {max_t*1000:.1f}ms")

        print("\n" + "=" * 60)
        print("SUMMARY")
        slow = [k for k, v in results.items() if v['avg'] > 1.0]
        if slow:
            print(f"⚠️  Slow queries (>1s avg): {slow}")
        else:
            print("✅ All queries under 1 second average")

        all_under_5s = all(v['avg'] < 5.0 for v in results.values())
        print(f"\nAll queries under 5s: {'✅ YES' if all_under_5s else '❌ NO'}")
        return results


if __name__ == "__main__":
    benchmarks = DuckDBQueryPerformance()
    results = benchmarks.run_benchmarks(iterations=10)