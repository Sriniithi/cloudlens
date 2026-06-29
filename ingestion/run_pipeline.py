"""
CloudLens AI — Full E2E Pipeline
Runs: ingest → clean → attribute → AI recommendations
"""
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))


def run_full_pipeline(mode="gemini"):
    print("=" * 60)
    print("CLOUDLENS AI — FULL E2E PIPELINE")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Step 1: Generate / load data
    print("\n📥 STEP 1: Data Ingestion")
    from ingestion.azure_connector import AzureCostConnector
    connector = AzureCostConnector(mode="synthetic")
    df = connector.get_cost_data(days_back=90)
    print(f"✅ Loaded {len(df)} rows")

    # Step 2: Load raw into DuckDB
    print("\n🗄️  STEP 2: Load to DuckDB")
    from ingestion.load_to_duckdb import load_csv_to_duckdb
    load_csv_to_duckdb()
    print("✅ Raw data in DuckDB")

    # Step 3: Setup schema
    print("\n🏗️  STEP 3: Setup DuckDB Schema")
    from processing.load_cleaned_data import setup_duckdb_schema
    setup_duckdb_schema()
    print("✅ Schema ready")

    # Step 4: Run attribution
    print("\n🏷️  STEP 4: Attribution Model")
    from processing.attribution_model import run_attribution
    run_attribution()
    print("✅ Attribution complete")

    # Step 5: AI recommendations
    print("\n🤖 STEP 5: AI Optimization Engine")
    from ai_engine.gemini_engine import run_optimization_engine
    run_optimization_engine(mode=mode)
    print("✅ AI recommendations generated")

    print("\n" + "=" * 60)
    print("✅ PIPELINE COMPLETE")
    print(f"Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)


if __name__ == "__main__":
    run_full_pipeline(mode="gemini")