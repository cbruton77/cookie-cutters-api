"""
Snowflake connection pool manager.

Supports both password and key-pair authentication.

Usage:
    from app.db.snowflake import get_db

    @router.get("/shifts")
    async def get_shifts(db = Depends(get_db)):
        result = db.execute_all("SELECT * FROM SHIFTS WHERE SHIFT_DATE = %s", [date])
        return result
"""

import snowflake.connector
from snowflake.connector import DictCursor
from contextlib import contextmanager
from threading import Lock
from queue import Queue, Empty
from app.config import get_settings
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
import base64
import logging

logger = logging.getLogger(__name__)


def _load_private_key(settings):
    """
    Load the RSA private key for key-pair authentication.
    Supports two modes:
      1. File path:  SNOWFLAKE_PRIVATE_KEY_PATH=/path/to/rsa_key.p8
      2. Base64:     SNOWFLAKE_PRIVATE_KEY_BASE64=MIIEvgIBADANBg...
                     (for serverless environments like Vercel where you can't store files)
    """
    passphrase = None
    if settings.snowflake_private_key_passphrase and settings.snowflake_private_key_passphrase.strip():
        passphrase = settings.snowflake_private_key_passphrase.encode()

    if settings.snowflake_private_key_base64:
        # Decode from base64 (for serverless deployments)
        key_bytes = base64.b64decode(settings.snowflake_private_key_base64)
        private_key = serialization.load_pem_private_key(
            key_bytes, password=None, backend=default_backend()
        )
    elif settings.snowflake_private_key_path:
        # Read from file (for local dev / VM hosting)
        with open(settings.snowflake_private_key_path, "rb") as f:
            private_key = serialization.load_pem_private_key(
                f.read(), password=None, backend=default_backend()
            )
    else:
        raise ValueError(
            "Key-pair auth requires either SNOWFLAKE_PRIVATE_KEY_PATH or "
            "SNOWFLAKE_PRIVATE_KEY_BASE64 to be set."
        )

    # Convert to the DER format that the Snowflake connector expects
    return private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


class SnowflakePool:
    """
    Thread-safe connection pool for Snowflake.
    Keeps connections warm and reuses them across requests.
    """

    def __init__(self):
        self._settings = get_settings()
        self._pool: Queue = Queue(maxsize=self._settings.snowflake_pool_size)
        self._size = 0
        self._lock = Lock()
        self._max_size = self._settings.snowflake_pool_size

    def _create_connection(self) -> snowflake.connector.SnowflakeConnection:
        """Create a new Snowflake connection using password or key-pair auth."""
        s = self._settings

        connect_params = dict(
            account=s.snowflake_account,
            user=s.snowflake_user,
            warehouse=s.snowflake_warehouse,
            database=s.snowflake_database,
            schema=s.snowflake_schema,
            role=s.snowflake_role,
            client_session_keep_alive=True,
        )

        if s.snowflake_auth_method == "keypair":
            connect_params["private_key"] = _load_private_key(s)
            logger.info("Connecting to Snowflake with key-pair auth")
        else:
            connect_params["password"] = s.snowflake_password
            logger.info("Connecting to Snowflake with password auth")

        conn = snowflake.connector.connect(**connect_params)
        logger.info("Created new Snowflake connection (pool size: %d)", self._size)
        return conn

    def get_connection(self) -> snowflake.connector.SnowflakeConnection:
        """Get a connection from the pool, creating one if needed."""
        # Try to get an existing connection
        try:
            conn = self._pool.get_nowait()
            # Validate the connection is still alive
            try:
                conn.cursor().execute("SELECT 1")
                return conn
            except Exception:
                logger.warning("Stale connection found, creating new one")
                try:
                    conn.close()
                except Exception:
                    pass
                with self._lock:
                    self._size -= 1
        except Empty:
            pass

        # Create a new connection if under the limit
        with self._lock:
            if self._size < self._max_size:
                self._size += 1
                return self._create_connection()

        # Pool is full — wait for one to be returned
        try:
            conn = self._pool.get(timeout=self._settings.snowflake_pool_timeout)
            return conn
        except Empty:
            raise ConnectionError(
                "Could not get a Snowflake connection — pool exhausted. "
                "Try increasing SNOWFLAKE_POOL_SIZE."
            )

    def return_connection(self, conn: snowflake.connector.SnowflakeConnection):
        """Return a connection to the pool for reuse."""
        try:
            self._pool.put_nowait(conn)
        except Exception:
            # Pool is full, close the excess connection
            try:
                conn.close()
            except Exception:
                pass
            with self._lock:
                self._size -= 1

    def close_all(self):
        """Close all connections in the pool (for shutdown)."""
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                conn.close()
            except Exception:
                pass
        with self._lock:
            self._size = 0
        logger.info("All Snowflake connections closed")


# Global pool instance — created once, shared across the app
_pool: SnowflakePool | None = None


def get_pool() -> SnowflakePool:
    global _pool
    if _pool is None:
        _pool = SnowflakePool()
    return _pool


class SnowflakeSession:
    """
    A session wrapper that provides a clean interface for queries.
    Automatically returns the connection to the pool when done.
    """

    def __init__(self, pool: SnowflakePool):
        self._pool = pool
        self._conn = pool.get_connection()

    def execute(self, query: str, params: list | tuple | dict = None):
        """Execute a query and return the cursor."""
        cursor = self._conn.cursor(DictCursor)
        cursor.execute(query, params or [])
        return cursor

    def execute_one(self, query: str, params=None) -> dict | None:
        """Execute and return a single row as a dict."""
        cursor = self.execute(query, params)
        row = cursor.fetchone()
        cursor.close()
        return row

    def execute_all(self, query: str, params=None) -> list[dict]:
        """Execute and return all rows as a list of dicts."""
        cursor = self.execute(query, params)
        rows = cursor.fetchall()
        cursor.close()
        return rows

    def execute_scalar(self, query: str, params=None):
        """Execute and return a single scalar value."""
        row = self.execute_one(query, params)
        if row:
            return list(row.values())[0]
        return None

    def close(self):
        """Return the connection to the pool."""
        if self._conn:
            self._pool.return_connection(self._conn)
            self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def get_db() -> SnowflakeSession:
    """
    FastAPI dependency that provides a database session.
    Usage:
        @router.get("/items")
        async def get_items(db: SnowflakeSession = Depends(get_db)):
            return db.execute_all("SELECT * FROM ITEMS")

    The connection is automatically returned to the pool after the request.
    """
    pool = get_pool()
    session = SnowflakeSession(pool)
    try:
        yield session
    finally:
        session.close()
