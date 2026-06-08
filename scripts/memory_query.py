#!/usr/bin/env python3
"""Query ENI memory: search messages, decisions, artifacts by keyword or session."""
import sqlite3, argparse, sys, json
from pathlib import Path

DB = '/root/.hermes/data/eni_memory.db'

def search(table, column, keyword, session=None, limit=10):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    q = f"SELECT * FROM {table} WHERE {column} LIKE ?"
    params = [f'%{keyword}%']
    if session:
        q += " AND session_id=?"
        params.append(session)
    q += f" ORDER BY created_at DESC LIMIT {limit}"
    c.execute(q, params)
    rows = c.fetchall()
    c.execute(f"PRAGMA table_info({table})")
    cols = [x[1] for x in c.fetchall()]
    conn.close()
    return cols, rows

def main():
    p = argparse.ArgumentParser(description="Query ENI memory")
    p.add_argument('keyword', nargs='?', help='Search keyword')
    p.add_argument('--table', '-t', choices=['messages','decisions','artifacts','issues'], default='messages')
    p.add_argument('--session', '-s', help='Session ID filter')
    p.add_argument('--limit', '-n', type=int, default=10)
    p.add_argument('--stats', action='store_true', help='Show DB stats only')
    args = p.parse_args()

    if not Path(DB).exists():
        print("FAIL: DB not found")
        sys.exit(1)

    if args.stats:
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        for t in ('messages','decisions','artifacts','issues','sessions'):
            c.execute(f"SELECT COUNT(*) FROM {t}")
            print(f"{t}: {c.fetchone()[0]}")
        conn.close()
        return

    if not args.keyword:
        p.print_help()
        sys.exit(1)

    col_map = {'messages': 'content', 'decisions': 'title', 'artifacts': 'name', 'issues': 'title'}
    col = col_map[args.table]
    cols, rows = search(args.table, col, args.keyword, args.session, args.limit)

    print(f"Found {len(rows)} in {args.table} for '{args.keyword}':")
    for r in rows:
        d = dict(zip(cols, r))
        if args.table == 'messages':
            print(f"  turn={d.get('turn_id','?')} role={d.get('role','?')} | {d.get('content','')[:120]}")
        elif args.table == 'decisions':
            print(f"  {d.get('created_at','?')} | {d.get('title','')} | {d.get('decision','')[:120]}")
        elif args.table == 'artifacts':
            print(f"  {d.get('created_at','?')} | {d.get('name','')} ({d.get('type','')}) -> {d.get('path','')}")
        elif args.table == 'issues':
            print(f"  {d.get('created_at','?')} | {d.get('title','')} | {d.get('status','')}")
    print(f"\n✅ Query done")

if __name__ == '__main__':
    main()
