import duckdb
import pandas as pd

MAC_TEAM_STRUCTURE = {
    "MAC-01": ["DevOps", "Platform"],
    "MAC-02": ["DataEngineering", "Analytics"],
    "MAC-03": ["Product", "Frontend"],
    "MAC-04": ["Backend", "QA"],
    "MAC-05": ["Security", "Compliance"],
    "MAC-06": ["Infrastructure", "CloudOps"],
    "MAC-07": ["ML", "Research"],
    "MAC-08": ["Finance", "Operations"],
}

RESOURCE_CATEGORY_MAP = {
    "microsoft.compute/virtualmachines":              "Compute",
    "microsoft.compute/virtualmachinescalesets":      "Compute",
    "microsoft.containerservice/managedclusters":     "Compute",
    "microsoft.storage/storageaccounts":              "Storage",
    "microsoft.storage/storageaccounts/fileservices": "Storage",
    "microsoft.network/loadbalancers":                "Networking",
    "microsoft.network/virtualnetworks":              "Networking",
    "microsoft.sql/servers/databases":                "Data Services",
    "microsoft.documentdb/databaseaccounts":          "Data Services",
}

METER_CATEGORY_MAP = {
    "compute":       "Compute",
    "storage":       "Storage",
    "networking":    "Networking",
    "network":       "Networking",
    "sql":           "Data Services",
    "data services": "Data Services",
}


def categorize_resource(
    resource_type: str,
    meter_category: str = ""
) -> str:
    rt = str(resource_type).lower().strip()
    if rt in RESOURCE_CATEGORY_MAP:
        return RESOURCE_CATEGORY_MAP[rt]
    for key, cat in RESOURCE_CATEGORY_MAP.items():
        if key in rt:
            return cat
    mc = str(meter_category).lower().strip()
    for key, cat in METER_CATEGORY_MAP.items():
        if key in mc:
            return cat
    return "Uncategorized"


def attribute_team(
    team_tag: str,
    resource_group: str,
    mac_id: str = ""
) -> tuple:
    tag = str(team_tag).strip() \
        if team_tag and str(team_tag) != 'nan' else ""
    rg = str(resource_group).lower().strip()

    # HIGH: valid tag
    if tag and tag.startswith("team:"):
        return tag.replace("team:", "").strip(), "high"

    # MEDIUM: extract from resource_group
    # format: rg-mac01-teamname-prod
    teams_lower = {
        t.lower(): t
        for teams in MAC_TEAM_STRUCTURE.values()
        for t in teams
    }
    for team_lower, team_name in teams_lower.items():
        if team_lower in rg:
            return team_name, "medium"

    # LOW: use MAC to assign first team
    if mac_id and mac_id in MAC_TEAM_STRUCTURE:
        return MAC_TEAM_STRUCTURE[mac_id][0], "low"

    return "Untagged", "low"


def run_attribution(db_path: str = "data/cloudlens.db"):
    print("Running attribution model...")

    read_conn = duckdb.connect(db_path, read_only=True)
    df = read_conn.execute(
        "SELECT * FROM cleaned_costs"
    ).df()
    read_conn.close()
    print(f"Loaded {len(df)} rows")

    df['category'] = df.apply(
        lambda r: categorize_resource(
            r['resource_type'], r.get('meter_category', '')
        ), axis=1
    )

    results = df.apply(
        lambda r: attribute_team(
            r.get('team_tag', ''),
            r.get('resource_group', ''),
            r.get('mac_id', '')
        ), axis=1
    )
    df['attributed_team'] = results.apply(lambda x: x[0])
    df['attribution_confidence'] = results.apply(lambda x: x[1])

    write_conn = duckdb.connect(db_path)
    write_conn.execute("DROP TABLE IF EXISTS attributed_costs")
    write_conn.execute(
        "CREATE TABLE attributed_costs AS SELECT * FROM df"
    )

    total = len(df)
    high = len(df[df['attribution_confidence'] == 'high'])
    medium = len(df[df['attribution_confidence'] == 'medium'])
    low = len(df[df['attribution_confidence'] == 'low'])

    print(f"\n=== ATTRIBUTION SUMMARY ===")
    print(f"Total:  {total}")
    print(f"High:   {high} ({round(high/total*100,1)}%)")
    print(f"Medium: {medium} ({round(medium/total*100,1)}%)")
    print(f"Low:    {low} ({round(low/total*100,1)}%)")

    print("\n=== COST BY ATTRIBUTED TEAM ===")
    print(write_conn.execute("""
        SELECT attributed_team, mac_id,
               ROUND(SUM(cost_inr), 2) as total_cost,
               MAX(attribution_confidence) as confidence
        FROM attributed_costs
        GROUP BY attributed_team, mac_id
        ORDER BY total_cost DESC
        LIMIT 10
    """).df())

    write_conn.close()
    print("\n✅ Attribution complete!")


if __name__ == "__main__":
    run_attribution()