from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any


def health_snapshot(sql_ping: Callable[[], bool]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "mcp_status": "ok",
        "sql_source_status": "unknown",
        "server_time_utc": datetime.now(timezone.utc).isoformat(),
    }
    try:
        result["sql_source_status"] = "ok" if sql_ping() else "error"
    except Exception as exc:
        result["sql_source_status"] = "error"
        result["detail"] = str(exc)
    return result
