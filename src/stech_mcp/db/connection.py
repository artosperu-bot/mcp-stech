from __future__ import annotations

from collections.abc import Callable
from typing import Any

from stech_mcp.config import Settings, build_mcp_connection_string, build_source_connection_string


def make_source_connection_factory(settings: Settings) -> Callable[[], Any]:
    connection_string = build_source_connection_string(settings)

    def connect() -> Any:
        import pyodbc

        return pyodbc.connect(connection_string, timeout=5)

    return connect


def make_mcp_connection_factory(settings: Settings) -> Callable[[], Any]:
    connection_string = build_mcp_connection_string(settings)

    def connect() -> Any:
        import pyodbc

        return pyodbc.connect(connection_string, timeout=5)

    return connect


def sql_ping(connection_factory: Callable[[], Any]) -> bool:
    connection = connection_factory()
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT 1")
        row = cursor.fetchone()
        return bool(row and row[0] == 1)
    finally:
        close = getattr(connection, "close", None)
        if callable(close):
            close()
