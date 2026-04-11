from __future__ import annotations

import sqlite3

import sqlite_vec
from sqlalchemy import Engine, create_engine, event


def configure_sqlite_connection(dbapi_connection) -> None:
    if not isinstance(dbapi_connection, sqlite3.Connection):
        return

    dbapi_connection.enable_load_extension(True)
    sqlite_vec.load(dbapi_connection)
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def create_engine_with_sqlite_pragmas(database_url: str) -> Engine:
    engine = create_engine(database_url)

    if database_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
            configure_sqlite_connection(dbapi_connection)

    return engine
