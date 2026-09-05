from __future__ import annotations

from typing import Any

from stech_mcp.domain.gtin import barcode_type, normalize_gtin, validate_gtin


_CONFIDENCE_SCORE = {"A1": 100, "A2": 90, "B": 80}


class ProductIdentityPromotionService:
    """Promote only already VERIFIED barcode enrichments into operational identity."""

    def __init__(
        self,
        *,
        enrichment_repository: Any,
        identity_repository: Any,
        audit_repository: Any,
    ) -> None:
        self.enrichment_repository = enrichment_repository
        self.identity_repository = identity_repository
        self.audit_repository = audit_repository

    @staticmethod
    def _target_field(identifier_type: str, value: str) -> str | None:
        requested = identifier_type.lower()
        kind = barcode_type(value)
        if requested == "ean":
            if kind not in {"EAN_8", "EAN_13"}:
                raise ValueError("EAN enrichment must contain a valid EAN-8 or EAN-13")
            return "ean"
        if requested == "upc":
            if kind != "UPC_A":
                raise ValueError("UPC enrichment must contain a valid UPC-A")
            return "upc"
        if requested == "gtin":
            if kind == "UPC_A":
                return "upc"
            if kind in {"EAN_8", "EAN_13"}:
                return "ean"
            if kind == "GTIN_14":
                return None
        raise ValueError("identifier_type must be EAN, UPC or GTIN")

    def promote(
        self,
        partnumber: str,
        identifier_type: str,
        *,
        approved_by: str = "CHATGPT",
    ) -> dict[str, Any]:
        pn = str(partnumber or "").strip().upper()
        field_code = str(identifier_type or "").strip().lower()
        actor = str(approved_by or "").strip() or "CHATGPT"
        if not pn:
            raise ValueError("partnumber is required")
        if field_code not in {"ean", "upc", "gtin"}:
            raise ValueError("identifier_type must be EAN, UPC or GTIN")

        enrichments = self.enrichment_repository.get_approved(pn, [field_code])
        if not enrichments:
            return {
                "found": False,
                "promoted": False,
                "partnumber": pn,
                "identifier_type": field_code.upper(),
                "status": "VERIFIED_ENRICHMENT_NOT_FOUND",
            }

        enrichment = enrichments[0]
        method = str(enrichment.get("method") or "").strip().upper()
        grade = str(enrichment.get("confidence_grade") or "").strip().upper()
        if method != "VERIFIED" or grade not in _CONFIDENCE_SCORE:
            raise ValueError("identifier promotion requires approved VERIFIED enrichment with confidence A1, A2 or B")

        if enrichment.get("value_text") is None:
            raise ValueError("identifier promotion requires value_text to preserve leading zeroes")
        value = normalize_gtin(str(enrichment.get("value_text")))
        if value is None or not validate_gtin(value):
            raise ValueError("verified identifier is not a valid GTIN checksum")

        target_field = self._target_field(field_code, value)
        if target_field is None:
            return {
                "found": True,
                "promoted": False,
                "partnumber": pn,
                "identifier_type": field_code.upper(),
                "value": value,
                "barcode_type": barcode_type(value),
                "target_field": None,
                "status": "UNSUPPORTED_OPERATIONAL_GTIN",
                "reason": "DB_DISTRIBUIDORES stores ean/upc but has no gtin14 identity column",
            }

        operational_rows = self.identity_repository.list_by_partnumber(pn)
        if not operational_rows:
            return {
                "found": False,
                "promoted": False,
                "partnumber": pn,
                "identifier_type": field_code.upper(),
                "value": value,
                "target_field": target_field,
                "status": "OPERATIONAL_PRODUCT_NOT_FOUND",
            }

        conflicts = []
        for row in operational_rows:
            current = normalize_gtin(str(row.get(target_field))) if row.get(target_field) is not None else None
            if current and current != value:
                conflicts.append({
                    "producto_distribuidor_id": row.get("producto_distribuidor_id"),
                    "distribuidor_codigo": row.get("distribuidor_codigo"),
                    "current_value": current,
                })

        if conflicts:
            self.audit_repository.add_audit_event(
                partnumber=pn,
                event_type="IDENTIFIER_PROMOTION_BLOCKED",
                actor_source=actor,
                detail={
                    "identifier_type": field_code.upper(),
                    "target_field": target_field,
                    "value": value,
                    "enrichment_id": enrichment.get("enrichment_id"),
                    "confidence_grade": grade,
                    "reason": "OPERATIONAL_CONFLICT",
                    "conflicts": conflicts,
                },
            )
            return {
                "found": True,
                "promoted": False,
                "partnumber": pn,
                "identifier_type": field_code.upper(),
                "value": value,
                "target_field": target_field,
                "status": "OPERATIONAL_CONFLICT",
                "conflicts": conflicts,
            }

        blanks_before = sum(1 for row in operational_rows if not str(row.get(target_field) or "").strip())
        if blanks_before == 0:
            return {
                "found": True,
                "promoted": True,
                "partnumber": pn,
                "identifier_type": field_code.upper(),
                "value": value,
                "target_field": target_field,
                "status": "ALREADY_PRESENT",
                "updated_count": 0,
                "operational_row_count": len(operational_rows),
            }

        self.audit_repository.add_audit_event(
            partnumber=pn,
            event_type="IDENTIFIER_PROMOTION_REQUESTED",
            actor_source=actor,
            detail={
                "identifier_type": field_code.upper(),
                "target_field": target_field,
                "value": value,
                "enrichment_id": enrichment.get("enrichment_id"),
                "confidence_grade": grade,
                "blank_rows": blanks_before,
            },
        )

        source = f"STECH_MCP_VERIFIED:{field_code.upper()}:{enrichment.get('enrichment_id')}"
        updated_count = self.identity_repository.promote_missing_identifier(
            partnumber=pn,
            target_field=target_field,
            value=value,
            confidence=_CONFIDENCE_SCORE[grade],
            source=source,
        )

        refreshed = self.identity_repository.list_by_partnumber(pn)
        unresolved = [
            row for row in refreshed
            if normalize_gtin(str(row.get(target_field))) != value
        ]
        if unresolved:
            raise RuntimeError("operational identifier verification failed after promotion")

        self.audit_repository.add_audit_event(
            partnumber=pn,
            event_type="IDENTIFIER_PROMOTED",
            actor_source=actor,
            detail={
                "identifier_type": field_code.upper(),
                "target_field": target_field,
                "value": value,
                "barcode_type": barcode_type(value),
                "enrichment_id": enrichment.get("enrichment_id"),
                "confidence_grade": grade,
                "updated_count": updated_count,
                "operational_row_count": len(refreshed),
                "identity_source": source,
            },
        )
        return {
            "found": True,
            "promoted": True,
            "partnumber": pn,
            "identifier_type": field_code.upper(),
            "value": value,
            "barcode_type": barcode_type(value),
            "target_field": target_field,
            "status": "PROMOTED",
            "updated_count": updated_count,
            "operational_row_count": len(refreshed),
            "confidence_grade": grade,
            "identity_source": source,
        }
