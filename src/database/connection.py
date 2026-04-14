"""
src/database/connection.py — Database connection pool manager
=============================================================
This module creates and manages the SQLAlchemy engine and sessions.

KEY CONCEPTS:

  Engine:
    The engine is the core interface to the database. It manages
    a connection POOL — a set of pre-opened connections that are
    reused across requests. Creating a new database connection is
    expensive (TCP handshake + authentication). A pool opens a few
    connections at startup and keeps them ready to use instantly.

  Session:
    A session is a "unit of work" — a conversation with the database.
    You open a session, do your reads/writes, commit or rollback,
    then close it. Always close sessions after use (we use a context
    manager to enforce this automatically).

  Context Manager (the "with" statement):
    We expose get_session() as a context manager using @contextmanager.
    This guarantees the session is always closed, even if an exception
    is raised. The pattern is:

        with get_session() as session:
            session.add(some_object)
        # session is automatically committed and closed here

  pool_pre_ping:
    Databases drop idle connections after a timeout. pool_pre_ping=True
    tells SQLAlchemy to test each connection before using it and
    reconnect if it was dropped. Without this, you get "connection
    closed" errors after the app has been idle for a while.

WHY we don't import config values at the top of this module:
    Importing POSTGRES_URL at module load time means the database URL
    is read when Python first imports this file — even in tests that
    don't need a real database. We import inside the function to allow
    tests to patch config values before the engine is created.
"""

import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

# Module-level singletons — created once, reused everywhere.
# We initialise them to None and create them on first use via
# _get_engine() / _get_session_factory().
_engine = None
_SessionFactory = None


def _get_engine():
    """
    Create the SQLAlchemy engine (once) and return it.
    Uses module-level caching so the engine is only created once
    per process, no matter how many times this function is called.
    """
    global _engine
    if _engine is None:
        # Import here (not at module top) so tests can patch the URL
        from src.config import POSTGRES_URL

        logger.info("Creating database engine...")
        _engine = create_engine(
            POSTGRES_URL,

            # Test connections before using them — handles database restarts
            # and idle connection timeouts gracefully.
            pool_pre_ping=True,

            # Keep up to 5 connections open and ready in the pool.
            # For our single-process pipeline, 5 is more than enough.
            pool_size=5,

            # Allow up to 10 extra connections beyond pool_size during spikes.
            max_overflow=10,

            # Log the actual SQL statements (useful for debugging).
            # Set to False in production to reduce log noise.
            echo=False,
        )
        logger.info("Database engine created.")
    return _engine


def _get_session_factory():
    """Create the session factory (once) and return it."""
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=_get_engine())
    return _SessionFactory


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """
    Context manager that provides a database session.

    Usage:
        with get_session() as session:
            session.add(stock_price_object)
        # Automatically committed and closed

    On exception:
        The session is automatically rolled back and closed.
        The exception is re-raised so the caller knows about it.

    WHY a context manager?
        If we returned a plain session and the caller forgot to close it,
        the connection would leak back to the pool in a dirty state.
        The context manager makes correct usage the only possible usage.
    """
    session: Session = _get_session_factory()()
    try:
        yield session
        session.commit()
        logger.debug("Session committed.")
    except Exception as e:
        session.rollback()
        logger.error(f"Session rolled back due to error: {e}")
        raise
    finally:
        session.close()
        logger.debug("Session closed.")


def check_connection() -> bool:
    """
    Test that the database is reachable.
    Returns True if connected, False otherwise.

    Use this for health checks — e.g. before starting the pipeline,
    verify the database is up rather than failing mid-run.
    """
    try:
        with _get_engine().connect() as conn:
            # "SELECT 1" is the standard lightweight health-check query.
            # Every database supports it and it returns instantly.
            conn.execute(text("SELECT 1"))
        logger.info("Database connection check: OK")
        return True
    except Exception as e:
        logger.error(f"Database connection check FAILED: {e}")
        return False
