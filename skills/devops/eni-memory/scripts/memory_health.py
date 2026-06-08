"""Database diagnostics: gaps, orphans, size, stats."""
import os
import sys
from db_utils import get_conn, DB_PATH


def health_check():
    conn = get_conn()
    stats = {}

    stats['db_size_kb'] = os.path.getsize(DB_PATH) / 1024

    for table in ['sessions', 'messages', 'decisions', 'artifacts', 'issues']:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        stats[f'{table}_count'] = count

    active = conn.execute(
        "SELECT COUNT(*) FROM sessions WHERE status = 'active'"
    ).fetchone()[0]
    stats['active_sessions'] = active

    gaps = conn.execute('''
        SELECT session_id, turn_id, next_turn
        FROM (
            SELECT session_id, turn_id,
                   LEAD(turn_id) OVER (PARTITION BY session_id ORDER BY turn_id) AS next_turn
            FROM messages
        )
        WHERE next_turn IS NOT NULL AND next_turn != turn_id + 1
    ''').fetchall()
    stats['turn_gaps'] = len(gaps)

    orphans = conn.execute('''
        SELECT COUNT(*) FROM messages m
        LEFT JOIN sessions s ON m.session_id = s.id
        WHERE s.id IS NULL
    ''').fetchone()[0]
    stats['orphan_messages'] = orphans

    recommendations = []
    if stats['turn_gaps'] > 0:
        recommendations.append(f"Found {stats['turn_gaps']} turn gaps — run persist.py for missing turns")
    if stats['orphan_messages'] > 0:
        recommendations.append(f"Found {stats['orphan_messages']} orphan messages — check FK integrity")
    if stats['db_size_kb'] > 50000:
        recommendations.append("DB > 50MB — consider compaction (compact_parents.py)")
    if active > 1:
        recommendations.append(f"Multiple active sessions ({active}) — close old ones")

    print("=== Memory Health ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    if recommendations:
        print("\nRecommendations:")
        for r in recommendations:
            print(f"  ⚠ {r}")
    else:
        print("\nAll checks passed.")
    return stats


if __name__ == "__main__":
    health_check()
