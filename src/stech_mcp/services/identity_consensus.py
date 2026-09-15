from __future__ import annotations

from collections import defaultdict
from typing import Any
from urllib.parse import urlparse

from stech_mcp.services.identity_barcode_extractor import canonical_gtin, validate_gtin


_PRIMARY_TYPES = {"MANUFACTURER", "OFFICIAL_DOCUMENT"}
_STRONG_TYPES = _PRIMARY_TYPES | {"AUTHORIZED_DISTRIBUTOR"}
_STRONG_GRADES = {"A1", "A2", "B"}
_PRIMARY_GRADES = {"A1", "A2"}


def _host(url: Any) -> str:
    return str(urlparse(str(url or "")).hostname or "").strip().lower().rstrip(".")


def _eligible_strong(partnumber: str, candidate: dict[str, Any]) -> bool:
    pn = str(partnumber or "").strip().upper()
    source_pn = str(candidate.get("source_partnumber") or "").strip().upper()
    source_type = str(candidate.get("source_type") or "").strip().upper()
    grade = str(candidate.get("confidence_rank") or "").strip().upper()
    value = candidate.get("normalized_value")
    return (
        bool(pn)
        and source_pn == pn
        and source_type in _STRONG_TYPES
        and grade in _STRONG_GRADES
        and validate_gtin(value)
        and canonical_gtin(value) is not None
    )


def evaluate_identity_consensus(partnumber: str, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply the identity-only Rule B promotion gate.

    A primary manufacturer/official candidate can promote alone. Otherwise at
    least two independent strong hosts must agree and one must be an authorized
    distributor. Retailer/marketplace evidence can remain visible to callers,
    but can never satisfy this gate by itself.
    """
    pn = str(partnumber or "").strip().upper()
    rows = [dict(row or {}) for row in candidates or []]
    strong = [row for row in rows if _eligible_strong(pn, row)]

    by_gtin: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in strong:
        key = canonical_gtin(row.get("normalized_value"))
        if key:
            by_gtin[key].append(row)

    conflicts: list[dict[str, Any]] = []
    if len(by_gtin) > 1:
        conflicts.append({
            "reason": "STRONG_IDENTITY_CONFLICT",
            "canonical_gtins": sorted(by_gtin),
            "values": sorted({str(row.get("normalized_value")) for row in strong}),
        })
        return {
            "decision": "CONFLICT",
            "promotable_candidates": [],
            "conflicts": conflicts,
            "evidence_summary": {
                "strong_source_count": len({_host(row.get("source_url")) for row in strong if _host(row.get("source_url"))}),
                "has_primary": any(str(row.get("source_type") or "").upper() in _PRIMARY_TYPES for row in strong),
                "has_authorized_distributor": any(str(row.get("source_type") or "").upper() == "AUTHORIZED_DISTRIBUTOR" for row in strong),
            },
        }

    if not by_gtin:
        return {
            "decision": "CANDIDATE" if rows else "NO_RESULT",
            "promotable_candidates": [],
            "conflicts": [],
            "evidence_summary": {
                "strong_source_count": 0,
                "has_primary": False,
                "has_authorized_distributor": False,
            },
        }

    matching = next(iter(by_gtin.values()))
    hosts = {_host(row.get("source_url")) for row in matching if _host(row.get("source_url"))}
    primary = [
        row for row in matching
        if str(row.get("source_type") or "").strip().upper() in _PRIMARY_TYPES
        and str(row.get("confidence_rank") or "").strip().upper() in _PRIMARY_GRADES
    ]
    has_distributor = any(
        str(row.get("source_type") or "").strip().upper() == "AUTHORIZED_DISTRIBUTOR"
        for row in matching
    )
    promotable = bool(primary) or (len(hosts) >= 2 and has_distributor)

    return {
        "decision": "PROMOTED" if promotable else "CANDIDATE",
        "promotable_candidates": matching if promotable else [],
        "conflicts": [],
        "evidence_summary": {
            "strong_source_count": len(hosts),
            "has_primary": bool(primary),
            "has_authorized_distributor": has_distributor,
        },
    }
