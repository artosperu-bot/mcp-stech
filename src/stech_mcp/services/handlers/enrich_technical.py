from __future__ import annotations

from typing import Any

import httpx

from stech_mcp.services.identity_barcode_extractor import IdentityBarcodeExtractor
from stech_mcp.services.product_identity_research import ProductIdentityResearchService
from stech_mcp.services.product_work_dispatcher import RetryableWorkError


class EnrichTechnicalHandler:
    """Map technical and identity enrichment outcomes to Product Work states."""

    aliases = ("RESEARCH_IDENTITY",)

    def __init__(self, engine: Any, vtex_ean_sync_service: Any | None = None) -> None:
        self.engine = engine
        self.identity_service = None
        self.vtex_ean_sync_service = vtex_ean_sync_service
        self._vtex_ean_sync_initialized = vtex_ean_sync_service is not None

    @staticmethod
    def _input(item: dict[str, Any]) -> dict[str, Any]:
        payload = item.get("input")
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _post_actions(payload: dict[str, Any]) -> set[str]:
        raw = payload.get("post_actions")
        if not isinstance(raw, list):
            return set()
        return {str(value or "").strip().upper() for value in raw if str(value or "").strip()}

    def _get_identity_service(self) -> ProductIdentityResearchService:
        if self.identity_service is None:
            self.identity_service = ProductIdentityResearchService(
                product_repository=self.engine.product_repository,
                enrichment_repository=self.engine.promotion_service.enrichment_repository,
                candidate_repository=self.engine.candidate_repository,
                promotion_service=self.engine.promotion_service,
                search_provider=self.engine.search_provider,
                source_document_service=self.engine.source_document_service,
                fact_extractor=IdentityBarcodeExtractor(),
                audit_repository=self.engine.audit_repository,
            )
        return self.identity_service

    def _get_vtex_ean_sync_service(self) -> Any | None:
        if self.vtex_ean_sync_service is not None:
            return self.vtex_ean_sync_service
        if self._vtex_ean_sync_initialized:
            return None
        self._vtex_ean_sync_initialized = True

        # Build this capability only when an identity item explicitly asks for
        # VTEX EAN sync. That keeps the existing image/technical worker startup
        # independent from VTEX Catalog credentials.
        from stech_mcp.config import Settings
        from stech_mcp.services.vtex_ean_client import VtexEanClient
        from stech_mcp.services.vtex_ean_sync import VtexEanSyncService

        settings = Settings()
        app_key = str(settings.vtex_app_key or "").strip()
        app_token = str(settings.vtex_app_token or "").strip()
        if not app_key or not app_token:
            return None

        client = VtexEanClient(
            account_name=settings.vtex_account_name,
            environment=settings.vtex_environment,
            app_key=app_key,
            app_token=app_token,
            timeout_seconds=settings.vtex_http_timeout_seconds,
        )
        self.vtex_ean_sync_service = VtexEanSyncService(client)
        return self.vtex_ean_sync_service

    def _vtex_post_action(self, partnumber: str, payload: dict[str, Any], result: dict[str, Any]) -> str | None:
        if "VTEX_EAN_SYNC" not in self._post_actions(payload):
            return None
        service = self._get_vtex_ean_sync_service()
        if service is None:
            return "VTEX_EAN_NOT_CONFIGURED"

        sync_result = service.sync(
            partnumber,
            result.get("verified_fields") if isinstance(result.get("verified_fields"), dict) else {},
        )
        sync_state = str(sync_result.get("state") or "VTEX_EAN_ERROR").strip().upper()
        if bool(sync_result.get("retryable")):
            detail = str(sync_result.get("error") or sync_state)
            raise RetryableWorkError(sync_state, detail)
        return sync_state

    def _identity(self,item:dict[str,Any],progress:Any)->dict[str,Any]:
        partnumber=str(item.get("partnumber") or "").strip().upper()
        payload=self._input(item)
        requested=payload.get("requested_fields")
        if requested is not None and not isinstance(requested,list): requested=None
        try:
            result=self._get_identity_service().research(partnumber,requested,progress)
        except LookupError as exc:
            return {"status":"NO_DATA_FOUND","current_step":"PRODUCT_NOT_FOUND","error_code":"PRODUCT_NOT_FOUND","error_detail":str(exc)}
        except (TimeoutError,httpx.TimeoutException,httpx.TransportError) as exc:
            raise RetryableWorkError("TEMPORARY_IDENTITY_RESEARCH_ERROR",f"{type(exc).__name__}: {exc}") from exc
        state=str(result.get("state") or "").strip().upper()
        result_code=str(result.get("result_code") or "").strip().upper()
        if state=="COMPLETED":
            post_state=self._vtex_post_action(partnumber,payload,result)
            return {"status":"COMPLETED","current_step":post_state or result_code or "VERIFICADO"}
        if state=="REVIEW_REQUIRED":
            return {"status":"REVIEW_REQUIRED","current_step":result_code or "REVIEW_REQUIRED","error_code":result.get("error_code") or "IDENTITY_CONFLICT","error_detail":"barcode identity requires review"}
        if state=="PARTIAL":
            return {"status":"PARTIAL","current_step":result_code or "NO_VERIFIED_IDENTITY_FOUND","error_code":result.get("error_code"),"error_detail":"no verified exact barcode found yet"}
        return {"status":"FAILED","current_step":"INVALID_IDENTITY_RESEARCH_STATE","error_code":"INVALID_IDENTITY_RESEARCH_STATE","error_detail":f"unsupported identity research state: {state or '<empty>'}"}

    def __call__(self, item: dict[str, Any], progress: Any) -> dict[str, Any]:
        if str(item.get("work_type") or "").strip().upper()=="RESEARCH_IDENTITY":
            return self._identity(item,progress)
        partnumber = str(item.get("partnumber") or "").strip().upper()
        payload = self._input(item)
        category_code = payload.get("category_code") or item.get("category_code")
        requested_fields = payload.get("requested_fields")
        if requested_fields is not None and not isinstance(requested_fields, list):
            requested_fields = None

        try:
            result = self.engine.enrich(partnumber,category_code,requested_fields,progress)
        except LookupError as exc:
            detail = str(exc)
            if "product not found" in detail.lower():
                return {"status":"NO_DATA_FOUND","current_step":"product not found","error_code":"PRODUCT_NOT_FOUND","error_detail":detail}
            return {"status":"NO_DATA_FOUND","current_step":"technical category not found","error_code":"TECHNICAL_CATEGORY_NOT_FOUND","error_detail":detail}
        except (TimeoutError,httpx.TimeoutException,httpx.TransportError) as exc:
            raise RetryableWorkError("TEMPORARY_RESEARCH_ERROR",f"{type(exc).__name__}: {exc}") from exc

        state=str(result.get("state") or "").strip().upper();conflicts=list(result.get("conflicts") or []);error_code=result.get("error_code");remaining=list(result.get("remaining_fields") or [])
        if state=="REVIEW_REQUIRED":
            return {"status":"REVIEW_REQUIRED","current_step":"review required","error_code":error_code or "FACT_CONFLICT","error_detail":f"{len(conflicts)} technical conflict(s) require review"}
        if state=="PARTIAL":
            return {"status":"PARTIAL","current_step":"partial technical enrichment","error_code":error_code,"error_detail":f"remaining technical fields: {', '.join(remaining)}" if remaining else None}
        if state=="COMPLETED": return {"status":"COMPLETED","current_step":"technical enrichment completed"}
        if state=="NO_DATA_FOUND": return {"status":"NO_DATA_FOUND","current_step":"no technical data found","error_code":error_code or "NO_DATA_FOUND"}
        return {"status":"FAILED","current_step":"invalid enrichment result","error_code":"INVALID_ENRICHMENT_STATE","error_detail":f"unsupported enrichment state: {state or '<empty>'}"}
