from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any


_TERMINAL = {"APPLIED", "REJECTED", "RESOLVED_EXTERNALLY"}


def _row_to_dict(cursor: Any, row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    columns = [item[0] for item in (cursor.description or [])]
    return dict(zip(columns, row, strict=False))


def _rows_to_dicts(cursor: Any, rows: list[Any]) -> list[dict[str, Any]]:
    columns = [item[0] for item in (cursor.description or [])]
    return [dict(zip(columns, row, strict=False)) for row in rows]


def _clean(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


class TaxonomyRepository:
    """Review-first bridge between DB_DISTRIBUIDORES and STECH_MCP.

    Detection/proposals are stored only in STECH_MCP. DB_DISTRIBUIDORES is
    modified exclusively by apply_review() after explicit approval.
    """

    def __init__(
        self,
        source_connection_factory: Callable[[], Any],
        mcp_connection_factory: Callable[[], Any],
    ) -> None:
        self._source_connection_factory = source_connection_factory
        self._mcp_connection_factory = mcp_connection_factory

    def list_missing(
        self,
        *,
        limit: int = 100,
        distributor: str | None = None,
    ) -> list[dict[str, Any]]:
        bounded = max(1, min(int(limit), 5000))
        code = _clean(distributor)
        connection = self._source_connection_factory()
        try:
            cursor = connection.cursor()
            sql = f"""SELECT TOP ({bounded})
    p.producto_distribuidor_id,
    d.codigo AS distributor_code,
    p.part_number,
    p.marca,
    p.nombre,
    p.categoria,
    p.subcategoria,
    p.ultima_observacion,
    p.updated_at
FROM dbo.PRD_PRODUCTO_DISTRIBUIDOR AS p
INNER JOIN dbo.DST_DISTRIBUIDOR AS d
    ON d.distribuidor_id = p.distribuidor_id
WHERE p.activo = 1
  AND (
      NULLIF(LTRIM(RTRIM(p.categoria)), '') IS NULL
      OR NULLIF(LTRIM(RTRIM(p.subcategoria)), '') IS NULL
  )
"""
            params: list[Any] = []
            if code:
                sql += "  AND UPPER(d.codigo) = UPPER(?)\n"
                params.append(code)
            sql += "ORDER BY p.updated_at ASC, p.producto_distribuidor_id ASC"
            cursor.execute(sql, *params)
            return _rows_to_dicts(cursor, list(cursor.fetchall()))
        finally:
            close = getattr(connection, "close", None)
            if callable(close):
                close()

    def taxonomy_catalog(self, *, limit: int = 1000) -> list[dict[str, Any]]:
        bounded = max(1, min(int(limit), 5000))
        connection = self._source_connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                f"""SELECT TOP ({bounded})
    LTRIM(RTRIM(categoria)) AS category,
    LTRIM(RTRIM(subcategoria)) AS subcategory,
    COUNT_BIG(*) AS product_count
FROM dbo.PRD_PRODUCTO_DISTRIBUIDOR
WHERE NULLIF(LTRIM(RTRIM(categoria)), '') IS NOT NULL
  AND NULLIF(LTRIM(RTRIM(subcategoria)), '') IS NOT NULL
GROUP BY LTRIM(RTRIM(categoria)), LTRIM(RTRIM(subcategoria))
ORDER BY COUNT_BIG(*) DESC, category, subcategory"""
            )
            return _rows_to_dicts(cursor, list(cursor.fetchall()))
        finally:
            close = getattr(connection, "close", None)
            if callable(close):
                close()

    def sync_missing(
        self,
        *,
        limit: int = 1000,
        distributor: str | None = None,
    ) -> dict[str, Any]:
        rows = self.list_missing(limit=limit, distributor=distributor)
        inserted = 0
        refreshed = 0
        connection = self._mcp_connection_factory()
        try:
            cursor = connection.cursor()
            for row in rows:
                source_id = int(row["producto_distribuidor_id"])
                cursor.execute(
                    """SELECT TOP (1) taxonomy_review_id, status
FROM dbo.taxonomy_review WITH (UPDLOCK, HOLDLOCK)
WHERE producto_distribuidor_id = ?""",
                    source_id,
                )
                existing = cursor.fetchone()
                observed = row.get("ultima_observacion")
                if existing is None:
                    cursor.execute(
                        """INSERT dbo.taxonomy_review (
    producto_distribuidor_id, distributor_code, partnumber, brand, product_name,
    current_category, current_subcategory, source_observed_at, status,
    detected_at, last_detected_at, updated_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING',
        SYSUTCDATETIME(), SYSUTCDATETIME(), SYSUTCDATETIME())""",
                        source_id,
                        row.get("distributor_code"),
                        row.get("part_number"),
                        row.get("marca"),
                        row.get("nombre"),
                        row.get("categoria"),
                        row.get("subcategoria"),
                        observed,
                    )
                    inserted += 1
                    continue

                status = str(existing[1] or "").upper()
                next_status = "PENDING" if status in {"ERROR", "RESOLVED_EXTERNALLY"} else status
                cursor.execute(
                    """UPDATE dbo.taxonomy_review
SET distributor_code = ?,
    partnumber = ?,
    brand = ?,
    product_name = ?,
    current_category = ?,
    current_subcategory = ?,
    source_observed_at = ?,
    status = ?,
    last_detected_at = SYSUTCDATETIME(),
    updated_at = SYSUTCDATETIME()
WHERE producto_distribuidor_id = ?""",
                    row.get("distributor_code"),
                    row.get("part_number"),
                    row.get("marca"),
                    row.get("nombre"),
                    row.get("categoria"),
                    row.get("subcategoria"),
                    observed,
                    next_status,
                    source_id,
                )
                refreshed += 1
            connection.commit()
        except Exception:
            if hasattr(connection, "rollback"):
                connection.rollback()
            raise
        finally:
            close = getattr(connection, "close", None)
            if callable(close):
                close()
        return {
            "detected": len(rows),
            "inserted": inserted,
            "refreshed": refreshed,
            "distributor": _clean(distributor),
        }

    def list_reviews(
        self,
        *,
        status: str | None = "PENDING",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        bounded = max(1, min(int(limit), 1000))
        state = _clean(status)
        connection = self._mcp_connection_factory()
        try:
            cursor = connection.cursor()
            if state:
                cursor.execute(
                    f"""SELECT TOP ({bounded}) *
FROM dbo.taxonomy_review
WHERE status = ?
ORDER BY updated_at ASC, taxonomy_review_id ASC""",
                    state.upper(),
                )
            else:
                cursor.execute(
                    f"""SELECT TOP ({bounded}) *
FROM dbo.taxonomy_review
ORDER BY updated_at DESC, taxonomy_review_id DESC"""
                )
            return _rows_to_dicts(cursor, list(cursor.fetchall()))
        finally:
            close = getattr(connection, "close", None)
            if callable(close):
                close()

    def get_review(self, review_id: int) -> dict[str, Any] | None:
        connection = self._mcp_connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT TOP (1) * FROM dbo.taxonomy_review WHERE taxonomy_review_id = ?",
                int(review_id),
            )
            return _row_to_dict(cursor, cursor.fetchone())
        finally:
            close = getattr(connection, "close", None)
            if callable(close):
                close()

    def _pair_kind(self, category: str, subcategory: str) -> str:
        target_cat = category.strip().casefold()
        target_sub = subcategory.strip().casefold()
        category_exists = False
        for row in self.taxonomy_catalog(limit=5000):
            cat = str(row.get("category") or "").strip().casefold()
            sub = str(row.get("subcategory") or "").strip().casefold()
            if cat == target_cat:
                category_exists = True
                if sub == target_sub:
                    return "EXISTING_PAIR"
        return "NEW_SUBCATEGORY" if category_exists else "NEW_CATEGORY"

    def propose(
        self,
        review_id: int,
        *,
        category: str,
        subcategory: str,
        confidence: str,
        reason: str,
        evidence: list[str] | None = None,
        proposed_by: str = "CHATGPT",
    ) -> dict[str, Any]:
        cat = _clean(category)
        sub = _clean(subcategory)
        actor = _clean(proposed_by) or "CHATGPT"
        conf = str(confidence or "").strip().upper()
        if not cat or not sub:
            raise ValueError("category and subcategory are required")
        if conf not in {"ALTA", "MEDIA", "BAJA"}:
            raise ValueError("confidence must be ALTA, MEDIA or BAJA")
        current = self.get_review(int(review_id))
        if current is None:
            raise LookupError("taxonomy review not found")
        if str(current.get("status") or "").upper() in _TERMINAL:
            raise ValueError("terminal taxonomy review cannot be proposed again")

        kind = self._pair_kind(cat, sub)
        payload = json.dumps(list(evidence or []), ensure_ascii=False, separators=(",", ":"))
        connection = self._mcp_connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """UPDATE dbo.taxonomy_review
SET proposed_category = ?,
    proposed_subcategory = ?,
    proposal_kind = ?,
    confidence = ?,
    reason = ?,
    evidence_json = ?,
    proposed_by = ?,
    status = 'PROPOSED',
    proposed_at = SYSUTCDATETIME(),
    approved_by = NULL,
    approved_at = NULL,
    applied_by = NULL,
    applied_at = NULL,
    last_error = NULL,
    updated_at = SYSUTCDATETIME()
WHERE taxonomy_review_id = ?""",
                cat,
                sub,
                kind,
                conf,
                _clean(reason),
                payload,
                actor,
                int(review_id),
            )
            connection.commit()
        except Exception:
            if hasattr(connection, "rollback"):
                connection.rollback()
            raise
        finally:
            close = getattr(connection, "close", None)
            if callable(close):
                close()
        result = self.get_review(int(review_id)) or {}
        result["requires_explicit_approval"] = kind != "EXISTING_PAIR" or conf != "ALTA"
        return result

    def approve(self, review_id: int, *, approved_by: str) -> dict[str, Any]:
        actor = _clean(approved_by)
        if not actor:
            raise ValueError("approved_by is required")
        current = self.get_review(int(review_id))
        if current is None:
            raise LookupError("taxonomy review not found")
        if str(current.get("status") or "").upper() != "PROPOSED":
            raise ValueError("only PROPOSED reviews can be approved")
        connection = self._mcp_connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """UPDATE dbo.taxonomy_review
SET status = 'APPROVED',
    approved_by = ?,
    approved_at = SYSUTCDATETIME(),
    last_error = NULL,
    updated_at = SYSUTCDATETIME()
WHERE taxonomy_review_id = ?""",
                actor,
                int(review_id),
            )
            connection.commit()
        except Exception:
            if hasattr(connection, "rollback"):
                connection.rollback()
            raise
        finally:
            close = getattr(connection, "close", None)
            if callable(close):
                close()
        return self.get_review(int(review_id)) or {}

    def reject(self, review_id: int, *, rejected_by: str, reason: str | None = None) -> dict[str, Any]:
        actor = _clean(rejected_by)
        if not actor:
            raise ValueError("rejected_by is required")
        current = self.get_review(int(review_id))
        if current is None:
            raise LookupError("taxonomy review not found")
        if str(current.get("status") or "").upper() == "APPLIED":
            raise ValueError("applied taxonomy review cannot be rejected")
        connection = self._mcp_connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """UPDATE dbo.taxonomy_review
SET status = 'REJECTED',
    approved_by = ?,
    reason = COALESCE(?, reason),
    updated_at = SYSUTCDATETIME()
WHERE taxonomy_review_id = ?""",
                actor,
                _clean(reason),
                int(review_id),
            )
            connection.commit()
        except Exception:
            if hasattr(connection, "rollback"):
                connection.rollback()
            raise
        finally:
            close = getattr(connection, "close", None)
            if callable(close):
                close()
        return self.get_review(int(review_id)) or {}

    def sql_preview(self, review_id: int) -> dict[str, Any]:
        review = self.get_review(int(review_id))
        if review is None:
            raise LookupError("taxonomy review not found")
        return {
            "taxonomy_review_id": int(review_id),
            "producto_distribuidor_id": review.get("producto_distribuidor_id"),
            "category": review.get("proposed_category"),
            "subcategory": review.get("proposed_subcategory"),
            "status": review.get("status"),
            "sql": (
                "UPDATE dbo.PRD_PRODUCTO_DISTRIBUIDOR SET "
                "categoria = CASE WHEN NULLIF(LTRIM(RTRIM(categoria)), '') IS NULL THEN ? ELSE categoria END, "
                "subcategoria = CASE WHEN NULLIF(LTRIM(RTRIM(subcategoria)), '') IS NULL THEN ? ELSE subcategoria END, "
                "updated_at = SYSDATETIME() WHERE producto_distribuidor_id = ?;"
            ),
            "params": [
                review.get("proposed_category"),
                review.get("proposed_subcategory"),
                review.get("producto_distribuidor_id"),
            ],
            "guard": "ONLY_MISSING_FIELDS_AND_APPROVED_REVIEW",
        }

    def apply_review(self, review_id: int, *, applied_by: str) -> dict[str, Any]:
        actor = _clean(applied_by) or "CHATGPT"
        review = self.get_review(int(review_id))
        if review is None:
            raise LookupError("taxonomy review not found")
        if str(review.get("status") or "").upper() != "APPROVED":
            raise ValueError("taxonomy review must be APPROVED before apply")

        category = _clean(review.get("proposed_category"))
        subcategory = _clean(review.get("proposed_subcategory"))
        if not category or not subcategory:
            raise ValueError("approved review has no category/subcategory proposal")

        source_id = int(review["producto_distribuidor_id"])
        source = self._source_connection_factory()
        try:
            cursor = source.cursor()
            cursor.execute(
                """SELECT TOP (1) categoria, subcategoria, atributos_json
FROM dbo.PRD_PRODUCTO_DISTRIBUIDOR WITH (UPDLOCK, HOLDLOCK)
WHERE producto_distribuidor_id = ?""",
                source_id,
            )
            row = cursor.fetchone()
            if row is None:
                raise LookupError("source product not found")

            current_category = _clean(row[0])
            current_subcategory = _clean(row[1])
            if current_category and current_category.casefold() != category.casefold():
                raise ValueError("source category changed after proposal")
            if current_subcategory and current_subcategory.casefold() != subcategory.casefold():
                raise ValueError("source subcategory changed after proposal")

            evidence_json = review.get("evidence_json") or "[]"
            cursor.execute(
                """UPDATE dbo.PRD_PRODUCTO_DISTRIBUIDOR
SET categoria = CASE
        WHEN NULLIF(LTRIM(RTRIM(categoria)), '') IS NULL THEN ?
        ELSE categoria
    END,
    subcategoria = CASE
        WHEN NULLIF(LTRIM(RTRIM(subcategoria)), '') IS NULL THEN ?
        ELSE subcategoria
    END,
    atributos_json = JSON_MODIFY(
        JSON_MODIFY(
        JSON_MODIFY(
        JSON_MODIFY(
        JSON_MODIFY(
        JSON_MODIFY(
            CASE WHEN ISJSON(atributos_json) = 1 THEN atributos_json ELSE N'{}' END,
            '$.categoria', ?
        ),
            '$.subcategoria', ?
        ),
            '$.clasificacion_version', 'CAT_V2'
        ),
            '$.clasificacion_fuente', 'MCP_REVISION_APROBADA'
        ),
            '$.clasificacion_confianza', ?
        ),
            '$.clasificacion_evidencia_mcp', JSON_QUERY(?)
        ),
    updated_at = SYSDATETIME()
WHERE producto_distribuidor_id = ?""",
                category,
                subcategory,
                category,
                subcategory,
                review.get("confidence"),
                evidence_json,
                source_id,
            )
            source.commit()
        except Exception as exc:
            if hasattr(source, "rollback"):
                source.rollback()
            self._mark_error(int(review_id), f"{type(exc).__name__}: {exc}")
            raise
        finally:
            close = getattr(source, "close", None)
            if callable(close):
                close()

        mcp = self._mcp_connection_factory()
        try:
            cursor = mcp.cursor()
            cursor.execute(
                """UPDATE dbo.taxonomy_review
SET status = 'APPLIED',
    current_category = ?,
    current_subcategory = ?,
    applied_by = ?,
    applied_at = SYSUTCDATETIME(),
    last_error = NULL,
    updated_at = SYSUTCDATETIME()
WHERE taxonomy_review_id = ?""",
                category,
                subcategory,
                actor,
                int(review_id),
            )
            mcp.commit()
        except Exception:
            if hasattr(mcp, "rollback"):
                mcp.rollback()
            raise
        finally:
            close = getattr(mcp, "close", None)
            if callable(close):
                close()

        return self.get_review(int(review_id)) or {}

    def _mark_error(self, review_id: int, error: str) -> None:
        connection = self._mcp_connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """UPDATE dbo.taxonomy_review
SET status = 'ERROR',
    last_error = ?,
    updated_at = SYSUTCDATETIME()
WHERE taxonomy_review_id = ?""",
                str(error or "")[:1900],
                int(review_id),
            )
            connection.commit()
        finally:
            close = getattr(connection, "close", None)
            if callable(close):
                close()
