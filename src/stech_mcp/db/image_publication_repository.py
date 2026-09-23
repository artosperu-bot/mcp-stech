from __future__ import annotations

from typing import Any, Callable


def _normalize_partnumber(value: str) -> str:
    return str(value or "").strip().upper()


def _row_to_dict(cursor: Any, row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    columns = [item[0] for item in (cursor.description or [])]
    return dict(zip(columns, row))


class ImagePublicationRepository:
    def __init__(self, connection_factory: Callable[[], Any]):
        self.connection_factory = connection_factory

    def get_publications(
        self,
        *,
        partnumber: str,
        account_code: str,
        remote_sku_id: int,
    ) -> list[dict[str, Any]]:
        normalized = _normalize_partnumber(partnumber)
        account = str(account_code or "").strip().upper()
        connection = self.connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT
                    product_image_publication_id, product_image_id, partnumber,
                    channel, account_code, remote_product_id, remote_sku_id,
                    remote_file_id, remote_archive_id, remote_url, position,
                    is_main, status, last_error, uploaded_at, last_verified_at,
                    created_at, updated_at
                FROM dbo.product_image_publication
                WHERE partnumber = ? AND channel = N'VTEX'
                  AND account_code = ? AND remote_sku_id = ?
                ORDER BY position ASC, product_image_publication_id ASC
                """,
                normalized,
                account,
                int(remote_sku_id),
            )
            columns = [item[0] for item in (cursor.description or [])]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        finally:
            connection.close()

    def upsert_publication(
        self,
        *,
        product_image_id: int,
        partnumber: str,
        account_code: str,
        remote_sku_id: int,
        position: int,
        is_main: bool,
        status: str,
        channel: str = "VTEX",
        remote_product_id: int | None = None,
        remote_file_id: int | None = None,
        remote_archive_id: int | None = None,
        remote_url: str | None = None,
        last_error: str | None = None,
    ) -> dict[str, Any]:
        normalized = _normalize_partnumber(partnumber)
        account = str(account_code or "").strip().upper()
        channel_name = str(channel or "VTEX").strip().upper()
        state = str(status or "").strip().upper()
        if state not in {"PENDING", "UPLOADED", "VERIFIED", "ERROR"}:
            raise ValueError(f"unsupported image publication status: {state}")

        connection = self.connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT TOP (1) product_image_publication_id
                FROM dbo.product_image_publication WITH (UPDLOCK, HOLDLOCK)
                WHERE channel = ? AND account_code = ?
                  AND remote_sku_id = ? AND product_image_id = ?
                """,
                channel_name,
                account,
                int(remote_sku_id),
                int(product_image_id),
            )
            existing = cursor.fetchone()
            uploaded_sql = "SYSUTCDATETIME()" if state in {"UPLOADED", "VERIFIED"} else "uploaded_at"
            verified_sql = "SYSUTCDATETIME()" if state == "VERIFIED" else "last_verified_at"
            if existing is None:
                cursor.execute(
                    f"""
                    INSERT dbo.product_image_publication (
                        product_image_id, partnumber, channel, account_code,
                        remote_product_id, remote_sku_id, remote_file_id,
                        remote_archive_id, remote_url, position, is_main,
                        status, last_error, uploaded_at, last_verified_at,
                        created_at, updated_at
                    )
                    OUTPUT INSERTED.product_image_publication_id
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                            {('SYSUTCDATETIME()' if state in {'UPLOADED', 'VERIFIED'} else 'NULL')},
                            {('SYSUTCDATETIME()' if state == 'VERIFIED' else 'NULL')},
                            SYSUTCDATETIME(), SYSUTCDATETIME())
                    """,
                    int(product_image_id),
                    normalized,
                    channel_name,
                    account,
                    remote_product_id,
                    int(remote_sku_id),
                    remote_file_id,
                    remote_archive_id,
                    remote_url,
                    int(position),
                    1 if is_main else 0,
                    state,
                    last_error,
                )
                inserted = cursor.fetchone()
                if not inserted:
                    raise RuntimeError("product_image_publication insert did not return an id")
                publication_id = int(inserted[0])
            else:
                publication_id = int(existing[0])
                cursor.execute(
                    f"""
                    UPDATE dbo.product_image_publication
                    SET partnumber = ?, remote_product_id = ?, remote_file_id = ?,
                        remote_archive_id = ?, remote_url = ?, position = ?,
                        is_main = ?, status = ?, last_error = ?,
                        uploaded_at = {uploaded_sql},
                        last_verified_at = {verified_sql},
                        updated_at = SYSUTCDATETIME()
                    WHERE product_image_publication_id = ?
                    """,
                    normalized,
                    remote_product_id,
                    remote_file_id,
                    remote_archive_id,
                    remote_url,
                    int(position),
                    1 if is_main else 0,
                    state,
                    last_error,
                    publication_id,
                )
            connection.commit()
            cursor.execute(
                """
                SELECT
                    product_image_publication_id, product_image_id, partnumber,
                    channel, account_code, remote_product_id, remote_sku_id,
                    remote_file_id, remote_archive_id, remote_url, position,
                    is_main, status, last_error, uploaded_at, last_verified_at,
                    created_at, updated_at
                FROM dbo.product_image_publication
                WHERE product_image_publication_id = ?
                """,
                publication_id,
            )
            row = _row_to_dict(cursor, cursor.fetchone())
            if row is None:
                raise RuntimeError("persisted image publication could not be read back")
            return row
        except Exception:
            if hasattr(connection, "rollback"):
                connection.rollback()
            raise
        finally:
            connection.close()

    def mark_verified(self, **row: Any) -> dict[str, Any]:
        clean = dict(row)
        clean.pop("status", None)
        clean["status"] = "VERIFIED"
        clean["last_error"] = None
        return self.upsert_publication(**clean)
