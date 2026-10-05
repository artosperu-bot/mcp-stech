from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any


class SourceDocumentRepository:
    def __init__(self, connection_factory: Callable[[], Any]):
        self._connection_factory = connection_factory

    @staticmethod
    def _row_to_dict(cursor: Any, row: Any) -> dict[str, Any] | None:
        if row is None:
            return None
        columns = [str(column[0]) for column in cursor.description]
        result = dict(zip(columns, row, strict=False))
        raw_pages = result.get("page_text_json")
        if isinstance(raw_pages, str) and raw_pages:
            try:
                result["pages"] = json.loads(raw_pages)
            except json.JSONDecodeError:
                result["pages"] = []
        return result

    def upsert_by_hash(
        self,
        *,
        sha256: str,
        url: str,
        document_type: str,
        title: str | None = None,
        content_type: str | None = None,
        content_length: int | None = None,
        extracted_text: str | None = None,
        pages: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        normalized_sha = str(sha256 or "").strip().lower()
        normalized_url = str(url or "").strip()
        normalized_type = str(document_type or "").strip().upper()
        if not normalized_sha:
            raise ValueError("sha256 is required")
        if not normalized_url:
            raise ValueError("url is required")
        if not normalized_type:
            raise ValueError("document_type is required")

        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
SELECT source_document_id, sha256, url, document_type, title, content_type,
       content_length, extracted_text, page_text_json, downloaded_at
FROM dbo.source_document
WHERE sha256 = ?;
""",
                normalized_sha,
            )
            existing = self._row_to_dict(cursor, cursor.fetchone())
            if existing is not None:
                return existing

            page_text_json = (
                json.dumps(pages, ensure_ascii=False, separators=(",", ":"))
                if pages is not None
                else None
            )
            cursor.execute(
                """
INSERT INTO dbo.source_document(
    sha256, url, document_type, title, content_type, content_length,
    extracted_text, page_text_json
)
OUTPUT INSERTED.source_document_id
VALUES (?, ?, ?, ?, ?, ?, ?, ?);
""",
                normalized_sha,
                normalized_url,
                normalized_type,
                title,
                content_type,
                int(content_length) if content_length is not None else None,
                extracted_text,
                page_text_json,
            )
            inserted = cursor.fetchone()
            if inserted is None:
                raise RuntimeError("source document insert did not return id")
            connection.commit()
            return {
                "source_document_id": int(inserted[0]),
                "sha256": normalized_sha,
                "url": normalized_url,
                "document_type": normalized_type,
                "title": title,
                "content_type": content_type,
                "content_length": int(content_length) if content_length is not None else None,
                "extracted_text": extracted_text,
                "page_text_json": page_text_json,
                "pages": pages or [],
                "downloaded_at": None,
            }
        except Exception:
            rollback = getattr(connection, "rollback", None)
            if callable(rollback):
                rollback()
            raise
        finally:
            close = getattr(connection, "close", None)
            if callable(close):
                close()

    def add_match(
        self,
        document_id: int,
        *,
        partnumber: str,
        match_type: str,
        pages: list[int] | None,
        confidence: str,
    ) -> None:
        pn = str(partnumber or "").strip().upper()
        match = str(match_type or "").strip().upper()
        grade = str(confidence or "").strip().upper()
        if not pn:
            raise ValueError("partnumber is required")
        if not match:
            raise ValueError("match_type is required")
        if not grade:
            raise ValueError("confidence is required")
        pages_json = json.dumps(pages or [], separators=(",", ":"))

        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
MERGE dbo.source_document_match AS target
USING (
    SELECT ? AS source_document_id, ? AS partnumber, ? AS match_type,
           ? AS matched_pages_json, ? AS confidence_rank
) AS source
ON target.source_document_id = source.source_document_id
AND target.partnumber = source.partnumber
WHEN MATCHED THEN UPDATE SET
    match_type = source.match_type,
    matched_pages_json = source.matched_pages_json,
    confidence_rank = source.confidence_rank,
    updated_at = SYSUTCDATETIME()
WHEN NOT MATCHED THEN INSERT(
    source_document_id, partnumber, match_type, matched_pages_json, confidence_rank
) VALUES (
    source.source_document_id, source.partnumber, source.match_type,
    source.matched_pages_json, source.confidence_rank
);
""",
                int(document_id), pn, match, pages_json, grade,
            )
            connection.commit()
        except Exception:
            rollback = getattr(connection, "rollback", None)
            if callable(rollback):
                rollback()
            raise
        finally:
            close = getattr(connection, "close", None)
            if callable(close):
                close()
