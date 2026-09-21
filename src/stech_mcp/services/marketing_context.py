from __future__ import annotations

from typing import Any


class MarketingProductContextService:
    """Read-only product contract for HERMES marketing and creative agents.

    This service composes existing authoritative STECH MCP sources. It does not
    publish to marketplaces, write Meta campaigns, change stock, or change price.
    """

    CONTRACT_VERSION = "HERMES_MARKETING_V1"

    def __init__(
        self,
        *,
        product_repository: Any,
        workspace_service: Any,
        source_image_repository: Any,
        workspace_image_repository: Any,
    ) -> None:
        self.product_repository = product_repository
        self.workspace_service = workspace_service
        self.source_image_repository = source_image_repository
        self.workspace_image_repository = workspace_image_repository

    @staticmethod
    def _pn(partnumber: str) -> str:
        pn = str(partnumber or "").strip().upper()
        if not pn:
            raise ValueError("partnumber is required")
        return pn

    @staticmethod
    def _present(row: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
        return {
            key: row.get(key)
            for key in keys
            if key in row and row.get(key) not in (None, "")
        }

    @classmethod
    def _operational_snapshot(cls, product: dict[str, Any]) -> dict[str, Any]:
        # Keep source semantics intact. In particular, distributor/source price
        # is never relabeled as STECH customer selling price.
        keys = (
            "distribuidor_codigo",
            "distribuidor",
            "activo",
            "ultima_observacion",
            "stock_valor",
            "stock_actual_valor",
            "stock_minimo_confirmado",
            "stock_operador",
            "stock_raw",
            "stock_es_exacto",
            "stock_es_umbral",
            "precio_actual_usd",
            "precio_usd",
            "precio",
            "moneda",
            "tipo_precio",
        )
        return cls._present(product, keys)

    def get(self, partnumber: str) -> dict[str, Any]:
        pn = self._pn(partnumber)
        distributor_rows = list(self.product_repository.list_by_partnumber(pn, limit=100))
        product = distributor_rows[0] if distributor_rows else None
        if product is None:
            return {
                "contract_version": self.CONTRACT_VERSION,
                "found": False,
                "partnumber": pn,
                "safety": {
                    "read_only": True,
                    "publishes": False,
                    "changes_price": False,
                    "changes_stock": False,
                },
            }

        workspace = self.workspace_service.get(pn)
        latest_observation: dict[str, Any] | None = None
        history_error: str | None = None
        try:
            history = list(self.product_repository.history(pn, limit=1))
            latest_observation = history[0] if history else None
        except Exception as exc:  # Operational history must not break creative context.
            history_error = f"{type(exc).__name__}: {exc}"

        distributor_snapshots = []
        for row in distributor_rows:
            snapshot = self._operational_snapshot(row)
            snapshot["producto_distribuidor_id"] = row.get("producto_distribuidor_id")
            snapshot["partnumber"] = row.get("partnumber") or row.get("part_number") or pn
            distributor_snapshots.append(snapshot)

        operational = {
            "source_view": "dbo.V_PRD_PRODUCTO_ACTUAL",
            "current": self._operational_snapshot(product),
            "distributor_count": len(distributor_snapshots),
            "distributors": distributor_snapshots,
            "latest_observation": latest_observation,
            "history_error": history_error,
            "selling_price_authoritative": False,
            "note": (
                "Any distributor/source price is operational evidence only. "
                "HERMES must obtain the approved STECH selling price from the "
                "pricing/commerce authority before publishing paid media."
            ),
        }

        return {
            "contract_version": self.CONTRACT_VERSION,
            "found": True,
            "partnumber": pn,
            "product": dict(workspace.get("master") or {}),
            "technical": dict(workspace.get("technical") or {}),
            "images": dict(workspace.get("images") or {}),
            "evidence": dict(workspace.get("evidence") or {}),
            "operational": operational,
            "safety": {
                "read_only": True,
                "publishes": False,
                "changes_price": False,
                "changes_stock": False,
                "meta_write_authority": False,
            },
        }

    def readiness(self, partnumber: str) -> dict[str, Any]:
        context = self.get(partnumber)
        pn = context["partnumber"]
        if not context.get("found"):
            return {
                "contract_version": self.CONTRACT_VERSION,
                "found": False,
                "partnumber": pn,
                "state": "BLOCKED",
                "blockers": ["PRODUCT_NOT_FOUND"],
                "warnings": [],
                "creative_generation_allowed": False,
                "publication_allowed": False,
            }

        blockers: list[str] = []
        warnings: list[str] = []
        product = dict(context.get("product") or {})
        technical = dict(context.get("technical") or {})
        image_group = dict(context.get("images") or {})
        image_readiness = dict(image_group.get("readiness") or {})
        evidence = dict(context.get("evidence") or {})

        if not str(product.get("brand") or "").strip():
            blockers.append("BRAND_MISSING")
        if not str(product.get("name") or "").strip():
            blockers.append("PRODUCT_NAME_MISSING")

        missing_required = list(technical.get("missing_required") or [])
        if missing_required:
            blockers.append("TECHNICAL_REQUIRED_FIELDS_MISSING")
        technical_state = str(technical.get("state") or "").strip().upper()
        if technical_state == "NOT_CONFIGURED":
            warnings.append("TECHNICAL_SCHEMA_NOT_CONFIGURED")

        conflict_count = int(evidence.get("conflict_count") or 0)
        if conflict_count > 0:
            blockers.append("FACT_CONFLICTS_PRESENT")

        image_state = str(image_readiness.get("state") or "").strip().upper()
        media_manifest = self.media_manifest(pn)
        reference_count = int(
            dict(media_manifest.get("product_lock") or {}).get("reference_count") or 0
        )
        if reference_count <= 0:
            blockers.append("NO_EXACT_PRODUCT_REFERENCE_IMAGE")
        elif image_state in {"NO_IMAGES", "REVIEW_REQUIRED", "INCOMPLETE"}:
            # The master image library may still need housekeeping, but HERMES
            # can create a draft when an exact/approved reference exists at any
            # current distributor or in the STECH workspace.
            warnings.append("PRODUCT_IMAGE_LIBRARY_REVIEW")

        if not (product.get("ean") or product.get("upc")):
            warnings.append("GTIN_NOT_AVAILABLE")

        state = "BLOCKED" if blockers else ("REVIEW" if warnings else "READY")
        return {
            "contract_version": self.CONTRACT_VERSION,
            "found": True,
            "partnumber": pn,
            "state": state,
            "blockers": blockers,
            "warnings": warnings,
            "creative_generation_allowed": not blockers,
            # Publication remains a separate Meta/commerce-authorized action.
            "publication_allowed": False,
            "requires_approved_selling_price_before_paid_media": True,
            "product_lock_required": True,
        }

    def media_manifest(self, partnumber: str) -> dict[str, Any]:
        pn = self._pn(partnumber)
        product = self.product_repository.get_by_partnumber(pn)
        if product is None:
            return {
                "contract_version": self.CONTRACT_VERSION,
                "found": False,
                "partnumber": pn,
                "product_lock": {"enabled": False, "reference_count": 0},
                "references": [],
            }

        source_images: list[dict[str, Any]] = []
        distributor_rows = list(self.product_repository.list_by_partnumber(pn, limit=100))
        seen_source_ids: set[int] = set()
        for distributor_row in distributor_rows:
            product_id = distributor_row.get("producto_distribuidor_id")
            if product_id in (None, ""):
                continue
            product_id_int = int(product_id)
            if product_id_int in seen_source_ids:
                continue
            seen_source_ids.add(product_id_int)
            for row in self.source_image_repository.list_for_product(product_id_int):
                item = dict(row)
                snapshot = str(item.get("part_number_snapshot") or "").strip().upper()
                exact = bool(snapshot and snapshot == pn)
                deleted = item.get("fecha_eliminacion") is not None or bool(item.get("ruta_papelera"))
                source_url = str(item.get("url_origen") or "").strip()
                item.update(
                    {
                        "media_source": "DISTRIBUTOR_DB",
                        "producto_distribuidor_id": product_id_int,
                        "distributor": distributor_row.get("distribuidor") or distributor_row.get("distributor"),
                        "partnumber_match": "EXACT" if exact else ("MISMATCH" if snapshot else "UNKNOWN"),
                        "eligible_reference": bool(exact and source_url and not deleted),
                    }
                )
                source_images.append(item)

        workspace_images: list[dict[str, Any]] = []
        for row in self.workspace_image_repository.list_images(pn):
            item = dict(row)
            item.update(
                {
                    "media_source": "STECH_WORKSPACE",
                    "eligible_reference": bool(item.get("is_approved")),
                }
            )
            workspace_images.append(item)

        references = [
            row
            for row in [*source_images, *workspace_images]
            if bool(row.get("eligible_reference"))
        ]
        return {
            "contract_version": self.CONTRACT_VERSION,
            "found": True,
            "partnumber": pn,
            "product_lock": {
                "enabled": bool(references),
                "policy": "PRESERVE_PRODUCT_IDENTITY",
                "reference_count": len(references),
                "allowed_changes": ["background", "lighting", "scene", "layout", "marketing_text"],
                "forbidden_changes": [
                    "product_shape",
                    "camera_count_or_position",
                    "ports_or_buttons",
                    "brand_or_logo",
                    "model_identity",
                    "declared_color",
                ],
            },
            "source_image_count": len(source_images),
            "workspace_image_count": len(workspace_images),
            "references": references,
            "source_images": source_images,
            "workspace_images": workspace_images,
        }
