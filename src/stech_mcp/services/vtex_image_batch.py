from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


_IMAGE_NAME_RE = re.compile(
    r"^(?P<partnumber>.+)_(?P<position>\d{2})\.(?:jpe?g|png|webp|gif|ico|svg)$",
    re.IGNORECASE,
)


def _normalize_partnumber(value: Any) -> str:
    return str(value or "").strip().upper()


def _bounded_limit(value: int, *, maximum: int = 100) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise ValueError("limit must be greater than zero")
    return min(parsed, maximum)


def _unique_partnumbers(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        partnumber = _normalize_partnumber(value)
        if not partnumber or partnumber in seen:
            continue
        result.append(partnumber)
        seen.add(partnumber)
    return result


class VtexImageBatchService:
    """Discover and synchronize local image folders through the safe VTEX image flow."""

    def __init__(self, *, root: str | Path, sync_service: Any):
        self.root = Path(root)
        self.sync_service = sync_service

    def discover_partnumbers(self) -> list[str]:
        if not self.root.exists():
            return []

        found: set[str] = set()
        for path in self.root.rglob("*"):
            if not path.is_file():
                continue
            match = _IMAGE_NAME_RE.match(path.name)
            if match is None:
                continue
            partnumber = _normalize_partnumber(match.group("partnumber"))
            if not partnumber:
                continue
            if _normalize_partnumber(path.parent.name) != partnumber:
                continue
            found.add(partnumber)
        return sorted(found)

    def _pending_summary(
        self,
        *,
        partnumber: str,
        local: dict[str, Any],
        status: dict[str, Any],
    ) -> dict[str, Any]:
        images = sorted(
            [dict(row) for row in (local.get("images") or []) if isinstance(row, dict)],
            key=lambda row: (int(row.get("position") or 0), int(row.get("product_image_id") or 0)),
        )
        local_files = [Path(str(row.get("storage_path") or "")).name for row in images]
        remote_files = [dict(row) for row in (status.get("remote_files") or []) if isinstance(row, dict)]
        remote_names = {
            str(row.get("name") or row.get("id") or "").strip().lower()
            for row in remote_files
            if str(row.get("name") or row.get("id") or "").strip()
        }
        pending_files = [name for name in local_files if name.lower() not in remote_names]

        state = str(status.get("state") or local.get("state") or "UNKNOWN").upper()
        local_state = str(local.get("state") or status.get("local_state") or "UNKNOWN").upper()
        write_blocked = bool(status.get("write_blocked"))
        actionable = local_state == "READY" and not write_blocked and state in {
            "READY",
            "PARTIAL",
        }

        return {
            "partnumber": partnumber,
            "state": state,
            "reason": status.get("reason") or local.get("reason"),
            "actionable": actionable,
            "write_blocked": write_blocked,
            "local_state": local_state,
            "local_image_count": int(local.get("image_count") or status.get("local_image_count") or 0),
            "remote_image_count": status.get("remote_image_count"),
            "pending_image_count": len(pending_files),
            "pending_files": pending_files,
            "remote_main_file": status.get("remote_main_file"),
            "transport": status.get("transport"),
        }

    def missing_list(
        self,
        *,
        after_partnumber: str = "",
        limit: int = 50,
        account_code: str = "VTEX_STECH",
        include_blocked: bool = True,
    ) -> dict[str, Any]:
        page_limit = _bounded_limit(limit)
        cursor = _normalize_partnumber(after_partnumber)
        account = str(account_code or "VTEX_STECH").strip().upper()
        candidates = [pn for pn in self.discover_partnumbers() if not cursor or pn > cursor]

        items: list[dict[str, Any]] = []
        inspected_count = 0
        last_inspected: str | None = None
        stopped_index: int | None = None

        for index, partnumber in enumerate(candidates):
            if len(items) >= page_limit:
                stopped_index = index
                break

            inspected_count += 1
            last_inspected = partnumber
            local = dict(self.sync_service.local_service.sync(partnumber) or {})
            status = dict(self.sync_service.status(partnumber, account_code=account) or {})
            state = str(status.get("state") or local.get("state") or "UNKNOWN").upper()
            if state == "SYNCED":
                continue

            summary = self._pending_summary(partnumber=partnumber, local=local, status=status)
            if summary["actionable"] or include_blocked:
                items.append(summary)

        if stopped_index is None:
            has_more = False
        else:
            has_more = stopped_index < len(candidates)

        actionable_count = sum(1 for row in items if row.get("actionable"))
        blocked_count = len(items) - actionable_count
        return {
            "account_code": account,
            "root": str(self.root),
            "after_partnumber": cursor or None,
            "next_after_partnumber": last_inspected,
            "limit": page_limit,
            "inspected_count": inspected_count,
            "count": len(items),
            "actionable_count": actionable_count,
            "blocked_count": blocked_count,
            "has_more": has_more,
            "items": items,
        }

    def sync_batch(
        self,
        *,
        partnumbers: list[str] | None = None,
        after_partnumber: str = "",
        limit: int = 20,
        account_code: str = "VTEX_STECH",
        stop_on_error: bool = False,
    ) -> dict[str, Any]:
        page_limit = _bounded_limit(limit, maximum=100)
        account = str(account_code or "VTEX_STECH").strip().upper()
        explicit = partnumbers is not None
        blocked_items: list[dict[str, Any]] = []
        discovery: dict[str, Any] | None = None

        if explicit:
            targets = _unique_partnumbers(partnumbers or [])[:page_limit]
            has_more = len(_unique_partnumbers(partnumbers or [])) > page_limit
            next_after = None
        else:
            discovery = self.missing_list(
                after_partnumber=after_partnumber,
                limit=page_limit,
                account_code=account,
                include_blocked=True,
            )
            blocked_items = [row for row in discovery["items"] if not row.get("actionable")]
            targets = [row["partnumber"] for row in discovery["items"] if row.get("actionable")]
            has_more = bool(discovery.get("has_more"))
            next_after = discovery.get("next_after_partnumber")

        results: list[dict[str, Any]] = []
        for partnumber in targets:
            result = dict(self.sync_service.sync(partnumber, account_code=account) or {})
            results.append(result)
            if stop_on_error and str(result.get("state") or "").upper() != "SYNCED":
                break

        states = Counter(str(row.get("state") or "UNKNOWN").upper() for row in results)
        synced_count = int(states.get("SYNCED", 0))
        error_count = sum(
            count for state, count in states.items() if state in {"ERROR", "PARTIAL", "REVIEW"}
        )
        result_blocked_count = int(states.get("BLOCKED", 0))

        return {
            "account_code": account,
            "mode": "explicit" if explicit else "auto_missing",
            "requested_count": len(targets),
            "processed_count": len(results),
            "synced_count": synced_count,
            "error_count": error_count,
            "blocked_count": len(blocked_items) + result_blocked_count,
            "states": dict(states),
            "stop_on_error": bool(stop_on_error),
            "has_more": has_more,
            "next_after_partnumber": next_after,
            "blocked_items": blocked_items,
            "results": results,
            "discovery": discovery,
        }
