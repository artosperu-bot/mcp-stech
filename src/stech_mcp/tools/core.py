from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any


def health_snapshot(
    sql_ping: Callable[[], bool],
    extra_snapshot: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
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

    if extra_snapshot is not None:
        try:
            extra = extra_snapshot() or {}
            if isinstance(extra, dict):
                result.update(extra)
        except Exception as exc:
            result["background_snapshot_error"] = f"{type(exc).__name__}: {exc}"
    return result
