from __future__ import annotations

from collections import Counter
from typing import Any

from stech_mcp.domain.gtin import (
    barcode_type,
    ean13_from_upc,
    normalize_gtin,
    upc_from_ean13,
)


class ProductIdentityDerivationService:
    """Fill only deterministic UPC-A / zero-padded GTIN-13 equivalents.

    This service performs no web research. It only derives the mathematically
    equivalent representation of an already-present, checksum-valid operational
    identifier and never overwrites a non-empty conflicting value.
    """

    def __init__(self, *, identity_repository: Any, audit_repository: Any) -> None:
        self.identity_repository = identity_repository
        self.audit_repository = audit_repository

    def derive_for_partnumber(self, partnumber: str, *, actor: str = "STECH_MCP") -> dict[str, Any]:
        pn = str(partnumber or "").strip().upper()
        if not pn:
            raise ValueError("partnumber is required")

        rows = list(self.identity_repository.list_by_partnumber(pn) or [])
        if not rows:
            return {"found": False, "partnumber": pn, "status": "OPERATIONAL_PRODUCT_NOT_FOUND", "derived": {}}

        brands = {str(row.get("marca") or "").strip().upper() for row in rows if str(row.get("marca") or "").strip()}
        if len(brands) > 1:
            return {
                "found": True,
                "partnumber": pn,
                "status": "IDENTITY_CONFLICT",
                "reason": "PARTNUMBER_USED_BY_MULTIPLE_BRANDS",
                "brands": sorted(brands),
                "derived": {},
            }

        eans: set[str] = set()
        upcs: set[str] = set()
        invalid_existing: list[dict[str, Any]] = []
        for row in rows:
            raw_ean = str(row.get("ean") or "").strip()
            raw_upc = str(row.get("upc") or "").strip()
            if raw_ean:
                normalized = normalize_gtin(raw_ean)
                if normalized is None or barcode_type(normalized) not in {"EAN_8", "EAN_13"}:
                    invalid_existing.append({"field": "ean", "value": raw_ean, "producto_distribuidor_id": row.get("producto_distribuidor_id")})
                else:
                    eans.add(normalized)
            if raw_upc:
                normalized = normalize_gtin(raw_upc)
                if normalized is None or barcode_type(normalized) != "UPC_A":
                    invalid_existing.append({"field": "upc", "value": raw_upc, "producto_distribuidor_id": row.get("producto_distribuidor_id")})
                else:
                    upcs.add(normalized)

        if invalid_existing:
            return {
                "found": True,
                "partnumber": pn,
                "status": "INVALID_EXISTING_IDENTIFIER",
                "invalid": invalid_existing,
                "derived": {},
            }

        candidate_eans = {value for value in (ean13_from_upc(upc) for upc in upcs) if value}
        candidate_upcs = {value for value in (upc_from_ean13(ean) for ean in eans) if value}
        if len(candidate_eans) > 1 or len(candidate_upcs) > 1:
            return {
                "found": True,
                "partnumber": pn,
                "status": "IDENTITY_CONFLICT",
                "reason": "MULTIPLE_EQUIVALENT_CANDIDATES",
                "candidate_eans": sorted(candidate_eans),
                "candidate_upcs": sorted(candidate_upcs),
                "derived": {},
            }

        candidate_ean = next(iter(candidate_eans), None)
        candidate_upc = next(iter(candidate_upcs), None)
        if candidate_ean and eans and eans != {candidate_ean}:
            return {
                "found": True,
                "partnumber": pn,
                "status": "IDENTITY_CONFLICT",
                "reason": "EXISTING_EAN_DIFFERS_FROM_UPC_EQUIVALENT",
                "existing_eans": sorted(eans),
                "candidate_ean": candidate_ean,
                "derived": {},
            }
        if candidate_upc and upcs and upcs != {candidate_upc}:
            return {
                "found": True,
                "partnumber": pn,
                "status": "IDENTITY_CONFLICT",
                "reason": "EXISTING_UPC_DIFFERS_FROM_EAN_EQUIVALENT",
                "existing_upcs": sorted(upcs),
                "candidate_upc": candidate_upc,
                "derived": {},
            }

        derived: dict[str, str] = {}
        updated_count = 0
        if candidate_ean and any(not str(row.get("ean") or "").strip() for row in rows):
            changed = self.identity_repository.promote_missing_identifier(
                partnumber=pn,
                target_field="ean",
                value=candidate_ean,
                confidence=70,
                source="STECH_MCP_DERIVED_GTIN_EQUIVALENCE:UPC_TO_EAN",
            )
            if changed:
                updated_count += int(changed)
                derived["ean"] = candidate_ean

        if candidate_upc and any(not str(row.get("upc") or "").strip() for row in rows):
            changed = self.identity_repository.promote_missing_identifier(
                partnumber=pn,
                target_field="upc",
                value=candidate_upc,
                confidence=70,
                source="STECH_MCP_DERIVED_GTIN_EQUIVALENCE:EAN_TO_UPC",
            )
            if changed:
                updated_count += int(changed)
                derived["upc"] = candidate_upc

        if not derived:
            return {
                "found": True,
                "partnumber": pn,
                "status": "NO_DERIVATION",
                "derived": {},
                "existing_eans": sorted(eans),
                "existing_upcs": sorted(upcs),
            }

        self.audit_repository.add_audit_event(
            partnumber=pn,
            event_type="IDENTIFIER_EQUIVALENT_DERIVED",
            actor_source=str(actor or "STECH_MCP"),
            detail={
                "derived": derived,
                "updated_count": updated_count,
                "method": "GTIN_ZERO_PAD_EQUIVALENCE",
                "confidence": 70,
            },
        )
        return {
            "found": True,
            "partnumber": pn,
            "status": "DERIVED",
            "derived": derived,
            "updated_count": updated_count,
            "method": "GTIN_ZERO_PAD_EQUIVALENCE",
        }

    def derive_batch(
        self,
        *,
        after_id: int = 0,
        limit: int = 500,
        distributor: str | None = None,
        actor: str = "STECH_MCP",
    ) -> dict[str, Any]:
        page = self.identity_repository.list_missing_identifiers(
            after_id=after_id,
            limit=max(1, min(int(limit or 500), 500)),
            distributor=distributor,
        )
        products = list(page.get("products") or [])
        seen: set[str] = set()
        results: list[dict[str, Any]] = []
        for product in products:
            pn = str(product.get("part_number") or "").strip().upper()
            if not pn or pn in seen:
                continue
            seen.add(pn)
            has_ean = bool(str(product.get("ean") or "").strip())
            has_upc = bool(str(product.get("upc") or "").strip())
            if has_ean == has_upc:
                continue
            results.append(self.derive_for_partnumber(pn, actor=actor))

        counter = Counter(str(row.get("status") or "UNKNOWN") for row in results)
        return {
            "after_id": max(0, int(after_id or 0)),
            "scanned_count": len(products),
            "processed_partnumber_count": len(results),
            "by_status": dict(counter),
            "results": results,
            "next_after_id": page.get("next_after_id", after_id),
            "has_more": bool(page.get("has_more")),
        }
