"""Keyword search across messages, decisions, artifacts, issues."""
import sys
import argparse
from db_utils import get_conn

TABLES = {
    'messages': ['content', 'tool_name'],
    'decisions': ['title', 'choice', 'rationale'],
    'artifacts': ['name', 'description'],
    'issues': ['title', 'symptom', 'root_cause', 'fix'],
}


def search(keyword: str, tables: list = None, limit: int = 20):
    conn = get_conn()
    tables = tables or list(TABLES.keys())

    pattern = f"%{keyword}%"
    results = []

    for table in tables:
        if table not in TABLES:
            continue
        cols = TABLES[table]
        conditions = " OR ".join(f"{c} LIKE ?" for c in cols)
        rows = conn.execute(
            f"SELECT * FROM {table} WHERE {conditions} ORDER BY created_at DESC LIMIT ?",
            [pattern] * len(cols) + [limit],
        ).fetchall()
        for r in rows:
            results.append((table, dict(r)))

    print(f"Found {len(results)} results for '{keyword}':")
    for table, row in results:
        print(f"\n[{table}] id={row.get('id')} session={row.get('session_id')}")
        for k, v in row.items():
            if v and k not in ('id', 'session_id', 'turn_id', 'created_at'):
                print(f"  {k}: {str(v)[:200]}")

    return results


def stats():
    conn = get_conn()
    print("=== Database Stats ===")
    for table in TABLES.keys():
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {count}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("keyword", nargs="?", default=None)
    parser.add_argument("-t", "--tables", nargs="+", choices=list(TABLES.keys()))
    parser.add_argument("-n", "--limit", type=int, default=20)
    parser.add_argument("--stats", action="store_true")
    args = parser.parse_args()

    if args.stats:
        stats()
    elif args.keyword:
        search(args.keyword, args.tables, args.limit)
    else:
        print("Usage: memory_query.py <keyword> OR --stats")
        sys.exit(1)
