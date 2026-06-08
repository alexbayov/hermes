"""FTS5 + sqlite-vec hybrid search for messages.

Based on Viktor architecture review (2026-06-08).
Stdlib + sqlite3 only. Requires sqlite-vec loadable extension.
"""
import struct
import sqlite3
from typing import List, Optional, Callable, Dict, Iterator

# ------------------------------------------------------------------
# Vector serialization
# ------------------------------------------------------------------

def serialize_f32(vec: List[float]) -> bytes:
    """Serialize a float vector as little-endian float32 blob."""
    return struct.pack(f"{len(vec)}f", *vec)


def deserialize_f32(data: bytes, dim: int) -> List[float]:
    """Deserialize little-endian float32 blob to float list."""
    return list(struct.unpack(f"{dim}f", data))


# ------------------------------------------------------------------
# Bootstrap
# ------------------------------------------------------------------

def _load_vec_extension(conn: sqlite3.Connection, so_path: str = "/usr/lib/sqlite-vec.so") -> None:
    conn.enable_load_extension(True)
    try:
        conn.load_extension(so_path)
    except sqlite3.OperationalError as e:
        # Try common fallback paths
        for path in ("./sqlite-vec.so", "sqlite-vec", "/usr/local/lib/sqlite-vec.so"):
            try:
                conn.load_extension(path)
                break
            except sqlite3.OperationalError:
                continue
        else:
            raise RuntimeError(f"Could not load sqlite-vec extension: {e}")
    finally:
        conn.enable_load_extension(False)


def init_all(db_path: str, dim: int = 384, vec_so_path: str = "/usr/lib/sqlite-vec.so") -> sqlite3.Connection:
    """Create FTS5 + vec0 virtual tables, triggers, and backfill existing data."""
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")

    # FTS5 external-content virtual table
    conn.execute(f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
            content,
            content='messages',
            content_rowid='id',
            tokenize='unicode61 remove_diacritics 2'
        );
    """)

    # Sync triggers for FTS5
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
            INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
        END;
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
            INSERT INTO messages_fts(messages_fts, rowid, content)
            VALUES ('delete', old.id, old.content);
        END;
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
            INSERT INTO messages_fts(messages_fts, rowid, content)
            VALUES ('delete', old.id, old.content);
            INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
        END;
    """)

    # sqlite-vec virtual table
    _load_vec_extension(conn, vec_so_path)
    conn.execute(f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS messages_vec USING vec0(
            message_id INTEGER PRIMARY KEY,
            session_id TEXT,
            embedding FLOAT[{dim}] distance_metric=cosine
        );
    """)

    # DELETE trigger for vec table
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS messages_vec_ad AFTER DELETE ON messages BEGIN
            DELETE FROM messages_vec WHERE message_id = old.id;
        END;
    """)

    conn.commit()

    # One-time backfill of existing rows into FTS5
    conn.execute("INSERT INTO messages_fts(messages_fts) VALUES ('rebuild');")
    conn.commit()
    return conn


def rebuild_fts(conn: sqlite3.Connection) -> None:
    """Rebuild FTS5 index from scratch (useful after bulk edits)."""
    conn.execute("INSERT INTO messages_fts(messages_fts) VALUES ('rebuild');")
    conn.commit()


# ------------------------------------------------------------------
# Embedding backfill
# ------------------------------------------------------------------

def iter_unembedded(conn: sqlite3.Connection, batch_size: int = 256) -> Iterator[List[sqlite3.Row]]:
    """Generator yielding batches of messages missing embeddings."""
    while True:
        rows = conn.execute(
            """
            SELECT m.id, m.session_id, m.content
            FROM messages m
            LEFT JOIN messages_vec v ON m.id = v.message_id
            WHERE v.message_id IS NULL
            ORDER BY m.id
            LIMIT ?
            """,
            (batch_size,),
        ).fetchall()
        if not rows:
            break
        yield rows


def backfill_embeddings(
    conn: sqlite3.Connection,
    embed_fn: Callable[[List[str]], List[List[float]]],
    batch_size: int = 256,
) -> int:
    """Resumable backfill: only embeds rows missing a vector. Returns count processed."""
    total = 0
    for rows in iter_unembedded(conn, batch_size):
        contents = [r["content"] for r in rows]
        vectors = embed_fn(contents)
        conn.executemany(
            "INSERT INTO messages_vec(message_id, session_id, embedding) VALUES (?,?,?)",
            [
                (r["id"], r["session_id"], serialize_f32(v))
                for r, v in zip(rows, vectors)
            ],
        )
        conn.commit()
        total += len(rows)
    return total


def reembed_one(
    conn: sqlite3.Connection,
    msg_id: int,
    session_id: str,
    content: str,
    embed_fn: Callable[[str], List[float]],
) -> None:
    """Re-embed a single message (DELETE then INSERT because vec0 has no UPSERT)."""
    conn.execute("DELETE FROM messages_vec WHERE message_id = ?", (msg_id,))
    vec = embed_fn(content)
    conn.execute(
        "INSERT INTO messages_vec(message_id, session_id, embedding) VALUES (?,?,?)",
        (msg_id, session_id, serialize_f32(vec)),
    )
    conn.commit()


# ------------------------------------------------------------------
# Search
# ------------------------------------------------------------------

def search_fts(
    conn: sqlite3.Connection,
    query: str,
    limit: int = 10,
) -> List[Dict]:
    """BM25-ranked full-text search with snippets."""
    rows = conn.execute(
        """
        SELECT m.id, m.session_id, m.role, m.created_at,
               bm25(messages_fts) AS score,
               snippet(messages_fts, 0, '[', ']', ' ... ', 12) AS snippet
        FROM messages_fts
        JOIN messages m ON m.id = messages_fts.rowid
        WHERE messages_fts MATCH ?
        ORDER BY score ASC
        LIMIT ?
        """,
        (query, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def search_vec(
    conn: sqlite3.Connection,
    query_vec: List[float],
    k: int = 10,
    session_id: Optional[str] = None,
) -> List[Dict]:
    """KNN cosine similarity search. Returns rows with distance + similarity."""
    params: List = [serialize_f32(query_vec), k]
    sql = """
        SELECT v.message_id AS id, v.distance, (1.0 - v.distance) AS cosine_sim,
               m.session_id, m.role, m.content, m.created_at
        FROM messages_vec v
        JOIN messages m ON m.id = v.message_id
        WHERE v.embedding MATCH ?
          AND k = ?
    """
    if session_id:
        sql += " AND v.session_id = ?"
        params.append(session_id)
    sql += " ORDER BY v.distance LIMIT ?"
    params.append(k)

    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def hybrid_search(
    conn: sqlite3.Connection,
    query_text: str,
    query_vec: List[float],
    limit: int = 10,
    pool: int = 50,
    k_rrf: int = 60,
) -> List[Dict]:
    """Reciprocal Rank Fusion (RRF) of BM25 + cosine KNN. Higher score = better."""
    fts_rows = search_fts(conn, query_text, limit=pool)
    vec_rows = search_vec(conn, query_vec, k=pool)

    scores: Dict[int, float] = {}
    ranks: Dict[int, Dict[str, Optional[int]]] = {}

    for rank, r in enumerate(fts_rows, 1):
        rid = r["id"]
        scores[rid] = scores.get(rid, 0.0) + 1.0 / (k_rrf + rank)
        ranks[rid] = {"fts_rank": rank}

    for rank, r in enumerate(vec_rows, 1):
        rid = r["id"]
        scores[rid] = scores.get(rid, 0.0) + 1.0 / (k_rrf + rank)
        if rid not in ranks:
            ranks[rid] = {}
        ranks[rid]["vec_rank"] = rank

    # Fetch merged row details for top results
    top_ids = sorted(scores.keys(), key=lambda i: scores[i], reverse=True)[:limit]
    if not top_ids:
        return []

    placeholders = ",".join("?" * len(top_ids))
    rows = conn.execute(
        f"""
        SELECT id, session_id, role, content, created_at
        FROM messages WHERE id IN ({placeholders})
        """,
        top_ids,
    ).fetchall()

    results = []
    for r in rows:
        rid = r["id"]
        results.append({
            **dict(r),
            "rrf_score": scores[rid],
            "fts_rank": ranks[rid].get("fts_rank"),
            "vec_rank": ranks[rid].get("vec_rank"),
        })
    # Sort by RRF score descending
    results.sort(key=lambda x: x["rrf_score"], reverse=True)
    return results


def hybrid_search_weighted(
    conn: sqlite3.Connection,
    query_text: str,
    query_vec: List[float],
    limit: int = 10,
    pool: int = 50,
    w_text: float = 0.5,
    w_vec: float = 0.5,
) -> List[Dict]:
    """Min-max normalized score blending. Tunable weights."""
    fts_rows = search_fts(conn, query_text, limit=pool)
    vec_rows = search_vec(conn, query_vec, k=pool)

    # Min-max normalize scores (invert distance for vec)
    fts_scores: Dict[int, float] = {r["id"]: r["score"] for r in fts_rows}
    vec_scores: Dict[int, float] = {r["id"]: 1.0 - r["distance"] for r in vec_rows}

    all_ids = set(fts_scores.keys()) | set(vec_scores.keys())

    # Normalize each side to [0,1]
    if fts_scores:
        fts_min = min(fts_scores.values())
        fts_max = max(fts_scores.values())
        fts_range = fts_max - fts_min or 1.0
    else:
        fts_min = fts_max = fts_range = 0.0

    if vec_scores:
        vec_min = min(vec_scores.values())
        vec_max = max(vec_scores.values())
        vec_range = vec_max - vec_min or 1.0
    else:
        vec_min = vec_max = vec_range = 0.0

    blended: Dict[int, float] = {}
    for rid in all_ids:
        n_fts = (fts_scores.get(rid, fts_min) - fts_min) / fts_range if fts_range else 0.0
        n_vec = (vec_scores.get(rid, vec_min) - vec_min) / vec_range if vec_range else 0.0
        blended[rid] = w_text * n_fts + w_vec * n_vec

    top_ids = sorted(blended.keys(), key=lambda i: blended[i], reverse=True)[:limit]
    if not top_ids:
        return []

    placeholders = ",".join("?" * len(top_ids))
    rows = conn.execute(
        f"""
        SELECT id, session_id, role, content, created_at
        FROM messages WHERE id IN ({placeholders})
        """,
        top_ids,
    ).fetchall()

    results = []
    for r in rows:
        rid = r["id"]
        results.append({
            **dict(r),
            "blended_score": blended[rid],
            "fts_score": fts_scores.get(rid),
            "vec_score": vec_scores.get(rid),
        })
    results.sort(key=lambda x: x["blended_score"], reverse=True)
    return results
