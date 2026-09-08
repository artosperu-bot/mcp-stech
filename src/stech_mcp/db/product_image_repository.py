from __future__ import annotations

from string import hexdigits
from typing import Any, Callable


def _normalize_partnumber(value: str) -> str:
    return str(value or "").strip().upper()


def _row_to_dict(cursor: Any, row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    columns = [item[0] for item in (cursor.description or [])]
    return dict(zip(columns, row))


class ProductImageRepository:
    """Persistence for local image metadata already owned by STECH_MCP."""

    def __init__(self, connection_factory: Callable[[], Any]):
        self.connection_factory = connection_factory

    def upsert_local_image(
        self,
        *,
        partnumber: str,
        source_type: str,
        storage_path: str,
        sha256_hash: str,
        width_px: int,
        height_px: int,
        format: str,
        position: int,
        is_approved: bool,
        partnumber_match: str = "EXACT",
        variant_type: str = "ORIGINAL",
        source_url: str | None = None,
        source_domain: str | None = None,
        background_status: str | None = None,
    ) -> dict[str, Any]:
        normalized = _normalize_partnumber(partnumber)
        if not normalized:
            raise ValueError("partnumber is required")
        if not sha256_hash or len(sha256_hash) != 64:
            raise ValueError("sha256_hash must contain 64 hexadecimal characters")
        if position <= 0:
            raise ValueError("position must be greater than zero")

        connection = self.connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT TOP (1) product_image_id
                FROM dbo.product_image WITH (UPDLOCK, HOLDLOCK)
                WHERE partnumber = ? AND sha256_hash = ? AND variant_type = ? AND position = ?
                """,
                normalized,
                sha256_hash,
                variant_type,
                position,
            )
            existing = cursor.fetchone()
            if existing is None:
                cursor.execute(
                    """
                    INSERT dbo.product_image (
                        partnumber, source_type, source_url, source_domain,
                        is_official, partnumber_match, storage_path, variant_type,
                        sha256_hash, width_px, height_px, format, background_status,
                        is_approved, position, created_at, updated_at
                    )
                    OUTPUT INSERTED.product_image_id
                    VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, SYSUTCDATETIME(), SYSUTCDATETIME())
                    """,
                    normalized,
                    source_type,
                    source_url,
                    source_domain,
                    partnumber_match,
                    storage_path,
                    variant_type,
                    sha256_hash,
                    width_px,
                    height_px,
                    format,
                    background_status,
                    1 if is_approved else 0,
                    position,
                )
                inserted = cursor.fetchone()
                if not inserted:
                    raise RuntimeError("product_image insert did not return an id")
                product_image_id = int(inserted[0])
            else:
                product_image_id = int(existing[0])
                cursor.execute(
                    """
                    UPDATE dbo.product_image
                    SET source_type = ?, source_url = ?, source_domain = ?,
                        partnumber_match = ?, storage_path = ?, width_px = ?,
                        height_px = ?, format = ?, background_status = ?,
                        is_approved = ?, position = ?, updated_at = SYSUTCDATETIME()
                    WHERE product_image_id = ?
                    """,
                    source_type,
                    source_url,
                    source_domain,
                    partnumber_match,
                    storage_path,
                    width_px,
                    height_px,
                    format,
                    background_status,
                    1 if is_approved else 0,
                    position,
                    product_image_id,
                )

            connection.commit()
            row = self._get_with_cursor(cursor, product_image_id)
            if row is None:
                raise RuntimeError("persisted product_image could not be read back")
            return row
        except Exception:
            if hasattr(connection, "rollback"):
                connection.rollback()
            raise
        finally:
            connection.close()

    def _get_with_cursor(self, cursor: Any, product_image_id: int) -> dict[str, Any] | None:
        cursor.execute(
            """
            SELECT
                product_image_id, partnumber, source_type, source_url, source_domain,
                is_official, partnumber_match, storage_path, variant_type,
                parent_image_id, sha256_hash, width_px, height_px, format,
                background_status, is_approved, position, created_at, updated_at
            FROM dbo.product_image
            WHERE product_image_id = ?
            """,
            int(product_image_id),
        )
        return _row_to_dict(cursor, cursor.fetchone())

    def _list_with_cursor(self, cursor: Any, partnumber: str) -> list[dict[str, Any]]:
        cursor.execute(
            """
            SELECT
                product_image_id, partnumber, source_type, source_url, source_domain,
                is_official, partnumber_match, storage_path, variant_type,
                parent_image_id, sha256_hash, width_px, height_px, format,
                background_status, is_approved, position, created_at, updated_at
            FROM dbo.product_image
            WHERE partnumber = ?
            ORDER BY position ASC, product_image_id ASC
            """,
            partnumber,
        )
        columns = [item[0] for item in (cursor.description or [])]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_by_id(self, product_image_id: int) -> dict[str, Any] | None:
        connection = self.connection_factory()
        try:
            cursor = connection.cursor()
            return self._get_with_cursor(cursor, int(product_image_id))
        finally:
            connection.close()

    def list_images(self, partnumber: str) -> list[dict[str, Any]]:
        normalized = _normalize_partnumber(partnumber)
        connection = self.connection_factory()
        try:
            cursor = connection.cursor()
            return self._list_with_cursor(cursor, normalized)
        finally:
            connection.close()

    def set_approval(self, product_image_id: int, approved: bool) -> dict[str, Any]:
        image_id = int(product_image_id)
        connection = self.connection_factory()
        try:
            cursor = connection.cursor()
            current = self._get_with_cursor(cursor, image_id)
            if current is None:
                raise ValueError("product image not found")
            cursor.execute(
                """
                UPDATE dbo.product_image
                SET is_approved = ?, updated_at = SYSUTCDATETIME()
                WHERE product_image_id = ?
                """,
                1 if approved else 0,
                image_id,
            )
            connection.commit()
            row = self._get_with_cursor(cursor, image_id)
            if row is None:
                raise RuntimeError("updated product image could not be read back")
            return row
        except Exception:
            if hasattr(connection, "rollback"):
                connection.rollback()
            raise
        finally:
            connection.close()

    def reorder(self, partnumber: str, ordered_ids: list[int]) -> list[dict[str, Any]]:
        normalized = _normalize_partnumber(partnumber)
        if not normalized:
            raise ValueError("partnumber is required")
        ids = [int(value) for value in ordered_ids]
        if not ids or len(ids) != len(set(ids)):
            raise ValueError("ordered_ids must contain unique image ids")

        connection = self.connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT product_image_id
                FROM dbo.product_image WITH (UPDLOCK, HOLDLOCK)
                WHERE partnumber = ?
                ORDER BY product_image_id
                """,
                normalized,
            )
            current_ids = [int(row[0]) for row in cursor.fetchall()]
            if set(current_ids) != set(ids) or len(current_ids) != len(ids):
                raise ValueError("ordered_ids must contain exactly all images for the Part Number")
            for position, image_id in enumerate(ids, start=1):
                cursor.execute(
                    """
                    UPDATE dbo.product_image
                    SET position = ?, updated_at = SYSUTCDATETIME()
                    WHERE product_image_id = ? AND partnumber = ?
                    """,
                    position,
                    image_id,
                    normalized,
                )
            connection.commit()
            return self._list_with_cursor(cursor, normalized)
        except Exception:
            if hasattr(connection, "rollback"):
                connection.rollback()
            raise
        finally:
            connection.close()

    def insert_variant(
        self,
        *,
        parent_image_id: int,
        storage_path: str,
        sha256_hash: str,
        width_px: int,
        height_px: int,
        format: str,
        variant_type: str = "EDITED_STECH",
    ) -> dict[str, Any]:
        parent_id = int(parent_image_id)
        variant = str(variant_type or "").strip().upper()
        digest = str(sha256_hash or "").strip().lower()
        if not storage_path:
            raise ValueError("storage_path is required")
        if variant == "ORIGINAL" or not variant:
            raise ValueError("variant_type must be a non-ORIGINAL child variant")
        if len(digest) != 64 or any(char not in hexdigits for char in digest):
            raise ValueError("sha256_hash must contain 64 hexadecimal characters")
        if int(width_px) <= 0 or int(height_px) <= 0:
            raise ValueError("image dimensions must be positive")

        connection = self.connection_factory()
        try:
            cursor = connection.cursor()
            parent = self._get_with_cursor(cursor, parent_id)
            if parent is None:
                raise ValueError("parent image not found")
            partnumber = _normalize_partnumber(parent.get("partnumber"))
            cursor.execute(
                """
                SELECT TOP (1) product_image_id
                FROM dbo.product_image WITH (UPDLOCK, HOLDLOCK)
                WHERE partnumber = ? AND sha256_hash = ? AND variant_type = ?
                """,
                partnumber,
                digest,
                variant,
            )
            existing = cursor.fetchone()
            if existing is not None:
                row = self._get_with_cursor(cursor, int(existing[0]))
                if row is None:
                    raise RuntimeError("existing image variant could not be read back")
                return row

            cursor.execute(
                """
                INSERT dbo.product_image (
                    partnumber, source_type, source_url, source_domain,
                    is_official, partnumber_match, storage_path, variant_type,
                    parent_image_id, sha256_hash, width_px, height_px, format,
                    background_status, is_approved, position, created_at, updated_at
                )
                OUTPUT INSERTED.product_image_id
                VALUES (?, N'STECH_EDIT', NULL, NULL, 0, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 0, ?, SYSUTCDATETIME(), SYSUTCDATETIME())
                """,
                partnumber,
                str(parent.get("partnumber_match") or "EXACT"),
                storage_path,
                variant,
                parent_id,
                digest,
                int(width_px),
                int(height_px),
                str(format or "").strip().upper(),
                int(parent.get("position") or 1),
            )
            inserted = cursor.fetchone()
            if not inserted:
                raise RuntimeError("product image variant insert did not return an id")
            image_id = int(inserted[0])
            connection.commit()
            row = self._get_with_cursor(cursor, image_id)
            if row is None:
                raise RuntimeError("created product image variant could not be read back")
            return row
        except Exception:
            if hasattr(connection, "rollback"):
                connection.rollback()
            raise
        finally:
            connection.close()
