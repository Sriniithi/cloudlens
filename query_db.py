import duckdb
conn = duckdb.connect('data/cloudlens.db', read_only=True)

# Query 1 — Show all tables
print('=== TABLES ===')
print(conn.execute('SHOW TABLES').df())

# Query 2 — Cost by MAC
print('\n=== COST BY MAC ===')
print(conn.execute('''
    SELECT mac_id, ROUND(SUM(total_cost_inr),2) as total
    FROM team_daily_costs
    GROUP BY mac_id ORDER BY total DESC
''').df())

# Query 3 — AI Recommendations
print('\n=== AI RECOMMENDATIONS ===')
print(conn.execute('''
    SELECT pattern, mac_id, 
           estimated_savings_inr, candidate_count,
           SUBSTR(ai_recommendation, 1, 200) as recommendation_preview
    FROM ai_recommendations
''').df())

conn.close()
