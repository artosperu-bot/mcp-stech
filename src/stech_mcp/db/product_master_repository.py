from __future__ import annotations

import json
from typing import Any, Callable


_MASTER_COLUMNS = (
    "source_product_id",
    "distributor",
    "brand",
    "model",
    "product_name",
    "ean",
    "upc",
    "mini_codigo",
    "category_code",
    "subcategory_code",
    "source_stock_value",
    "source_stock_operator",
    "source_price_usd_sin_igv",
    "source_observed_at",
    "screen_inches",
    "package_width_cm",
    "package_length_cm",
    "package_height_cm",
    "package_weight_g",
    "package_status",
    "package_method",
    "package_source",
    "package_rule_code",
    "package_confidence_grade",
    "readiness_state",
    "identity_score",
    "technical_score",
    "image_score",
    "package_score",
    "coolbox_score",
)


def _normalize_partnumber(value: str) -> str:
    return str(value or "").strip().upper()


def _row_to_dict(cursor: Any, row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    columns = [item[0] for item in (cursor.description or [])]
    return dict(zip(columns, row))


def _value_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    return str(value)


class ProductMasterRepository:
    def __init__(self, connection_factory: Callable[[], Any]):
        self.connection_factory = connection_factory

    def upsert_master(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        partnumber = _normalize_partnumber(snapshot.get("partnumber") or snapshot.get("part_number"))
        if not partnumber:
            raise ValueError("partnumber is required")

        normalized = {**snapshot, "partnumber": partnumber}
        values = [normalized.get(column) for column in _MASTER_COLUMNS]
        set_sql = ",\n                ".join(f"{column} = ?" for column in _MASTER_COLUMNS)
        insert_columns = ", ".join(("partnumber",) + _MASTER_COLUMNS)
        insert_placeholders = ",".join("?" for _ in range(1 + len(_MASTER_COLUMNS)))

        sql = f"""
        IF EXISTS (SELECT 1 FROM dbo.product_master WHERE partnumber = ?)
        BEGIN
            UPDATE dbo.product_master
            SET {set_sql},
                updated_at = SYSUTCDATETIME()
            WHERE partnumber = ?;
        END
        ELSE
        BEGIN
            INSERT dbo.product_master ({insert_columns})
            VALUES ({insert_placeholders});
        END;
        """
        params = (partnumber, *values, partnumber, partnumber, *values)

        connection = self.connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(sql, *params)
            connection.commit()
            return normalized
        except Exception:
            if hasattr(connection, "rollback"):
                connection.rollback()
            raise
        finally:
            connection.close()

    def get(self, partnumber: str) -> dict[str, Any] | None:
        normalized = _normalize_partnumber(partnumber)
        connection = self.connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT TOP (1) *
                FROM dbo.V_PRODUCT_WORKSPACE_V1
                WHERE partnumber = ?
                """,
                normalized,
            )
            return _row_to_dict(cursor, cursor.fetchone())
        finally:
            connection.close()

    def replace_draft(
        self,
        *,
        partnumber: str,
        marketplace: str,
        template_name: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        normalized = _normalize_partnumber(partnumber)
        market = str(marketplace or "").strip().upper()
        if not normalized or not market:
            raise ValueError("partnumber and marketplace are required")

        fields = list(payload.get("fields") or [])
        field_count = len(fields)
        required_missing_count = sum(
            1 for field in fields if str(field.get("status") or "").upper() == "RESEARCH_REQUIRED"
        )
        estimated_count = sum(
            1 for field in fields if str(field.get("status") or "").upper() == "ESTIMATED"
        )
        status = "FALTAN_DATOS" if required_missing_count else "LISTO_PARA_REVISAR"
        payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)

        connection = self.connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT TOP (1)
                    channel_draft_id,
                    draft_version,
                    status,
                    field_count,
                    required_missing_count,
                    estimated_count,
                    payload_json
                FROM dbo.channel_draft
                WHERE partnumber = ? AND marketplace = ?
                ORDER BY draft_version DESC, channel_draft_id DESC
                """,
                normalized,
                market,
            )
            latest = cursor.fetchone()
            previous_version = int(latest[1]) if latest else 0

            if latest and latest[6] == payload_json:
                return {
                    "channel_draft_id": int(latest[0]),
                    "partnumber": normalized,
                    "marketplace": market,
                    "template_name": template_name,
                    "draft_version": previous_version,
                    "status": latest[2],
                    "field_count": int(latest[3]),
                    "required_missing_count": int(latest[4]),
                    "estimated_count": int(latest[5]),
                    "reused": True,
                }

            draft_version = previous_version + 1
            cursor.execute(
                """
                INSERT dbo.channel_draft (
                    partnumber, marketplace, template_name, draft_version, status,
                    field_count, required_missing_count, estimated_count, payload_json
                )
                OUTPUT INSERTED.channel_draft_id
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                normalized,
                market,
                template_name,
                draft_version,
                status,
                field_count,
                required_missing_count,
                estimated_count,
                payload_json,
            )
            inserted = cursor.fetchone()
            if not inserted:
                raise RuntimeError("channel_draft insert did not return an id")
            channel_draft_id = int(inserted[0])

            for position, field in enumerate(fields, start=1):
                cursor.execute(
                    """
                    INSERT dbo.channel_draft_field (
                        channel_draft_id, field_position, field_name, value_text,
                        status, source, method, note
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    channel_draft_id,
                    position,
                    str(field.get("field") or field.get("field_name") or "").strip(),
                    _value_text(field.get("value")),
                    field.get("status"),
                    field.get("source"),
                    field.get("method"),
                    field.get("note"),
                )

            connection.commit()
            return {
                "channel_draft_id": channel_draft_id,
                "partnumber": normalized,
                "marketplace": market,
                "template_name": template_name,
                "draft_version": draft_version,
                "status": status,
                "field_count": field_count,
                "required_missing_count": required_missing_count,
                "estimated_count": estimated_count,
                "reused": False,
            }
        except Exception:
            if hasattr(connection, "rollback"):
                connection.rollback()
            raise
        finally:
            connection.close()

    def get_latest_draft(self, partnumber: str, marketplace: str) -> dict[str, Any] | None:
        normalized = _normalize_partnumber(partnumber)
        market = str(marketplace or "").strip().upper()
        connection = self.connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT TOP (1)
                    channel_draft_id, partnumber, marketplace, template_name,
                    draft_version, status, field_count, required_missing_count,
                    estimated_count, payload_json, created_at, updated_at
                FROM dbo.channel_draft
                WHERE partnumber = ? AND marketplace = ?
                ORDER BY draft_version DESC, channel_draft_id DESC
                """,
                normalized,
                market,
            )
            row = cursor.fetchone()
            result = _row_to_dict(cursor, row)
            if result is None:
                return None
            raw_payload = result.get("payload_json")
            if raw_payload:
                try:
                    result["payload"] = json.loads(raw_payload)
                except (TypeError, json.JSONDecodeError):
                    result["payload"] = None
            return result
        finally:
            connection.close()

    def list_images(self, partnumber: str) -> list[dict[str, Any]]:
        normalized = _normalize_partnumber(partnumber)
        connection = self.connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT
                    product_image_id, partnumber, source_type, source_url, source_domain,
                    is_official, partnumber_match, storage_path, variant_type,
                    parent_image_id, sha256_hash, width_px, height_px, format,
                    background_status, is_approved, position, created_at, updated_at
                FROM dbo.product_image
                WHERE partnumber = ?
                ORDER BY is_approved DESC, position ASC, product_image_id ASC
                """,
                normalized,
            )
            columns = [item[0] for item in (cursor.description or [])]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        finally:
            connection.close()

    def add_audit_event(
        self,
        *,
        partnumber: str,
        event_type: str,
        actor_source: str,
        channel: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        normalized = _normalize_partnumber(partnumber)
        detail_json = None if detail is None else json.dumps(
            detail, ensure_ascii=False, separators=(",", ":"), default=str
        )
        connection = self.connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                INSERT dbo.product_audit_event (
                    partnumber, event_type, actor_source, channel, detail_json
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                normalized,
                str(event_type).strip().upper(),
                str(actor_source).strip(),
                str(channel).strip().upper() if channel else None,
                detail_json,
            )
            connection.commit()
        except Exception:
            if hasattr(connection, "rollback"):
                connection.rollback()
            raise
        finally:
            connection.close()
