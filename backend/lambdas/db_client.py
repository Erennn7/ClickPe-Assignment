"""
Database Connection Client and Query Utilities
Optimized for high-throughput batch operations and AWS Lambda reuse.
"""

import os
import logging
from contextlib import contextmanager
from typing import List, Tuple, Any, Dict, Optional
import psycopg2
from psycopg2 import pool, extras

logger = logging.getLogger("db_client")
logger.setLevel(logging.INFO)

# Global connection pool for Lambda container reuse
_connection_pool: Optional[pool.SimpleConnectionPool] = None


def get_db_url() -> str:
    """Resolve database URL from environment with fallback defaults."""
    if os.getenv("DATABASE_URL"):
        return os.environ["DATABASE_URL"]

    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "postgres")
    dbname = os.getenv("POSTGRES_DB", "loan_engine")
    return f"postgresql://{user}:{password}@{host}:{port}/{dbname}"


def init_connection_pool(minconn: int = 1, maxconn: int = 10) -> pool.SimpleConnectionPool:
    """Initialize or reuse existing thread-safe connection pool."""
    global _connection_pool
    if _connection_pool is None or _connection_pool.closed:
        db_url = get_db_url()
        logger.info(f"Initializing PostgreSQL connection pool to {db_url.split('@')[-1]}")
        _connection_pool = pool.SimpleConnectionPool(minconn, maxconn, db_url)
    return _connection_pool


@contextmanager
def get_db_cursor(commit: bool = True):
    """
    Context manager that yields a cursor from the pool and handles commits/rollbacks.
    """
    db_pool = init_connection_pool()
    conn = db_pool.getconn()
    try:
        with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
            yield cur
        if commit:
            conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database transaction error: {e}")
        raise e
    finally:
        db_pool.putconn(conn)


def bulk_insert_rows(
    table: str, 
    columns: List[str], 
    rows: List[Tuple[Any, ...]], 
    page_size: int = 1000
) -> int:
    """
    High-speed batch insertion using psycopg2 execute_values.
    Significantly outperforms iterative INSERT statements by 10-50x.
    """
    if not rows:
        return 0

    col_str = ", ".join(columns)
    sql = f"INSERT INTO {table} ({col_str}) VALUES %s ON CONFLICT (user_id) DO NOTHING"

    with get_db_cursor(commit=True) as cur:
        extras.execute_values(cur, sql, rows, template=None, page_size=page_size)
    
    return len(rows)


def execute_sql(sql: str, params: Optional[Tuple[Any, ...]] = None, commit: bool = True) -> List[Dict[str, Any]]:
    """Execute arbitrary query, commit if needed, and safely return records if any."""
    with get_db_cursor(commit=commit) as cur:
        cur.execute(sql, params or ())
        try:
            return cur.fetchall()
        except psycopg2.ProgrammingError:
            # Expected for non-returning INSERT / UPDATE / DELETE statements
            return []
