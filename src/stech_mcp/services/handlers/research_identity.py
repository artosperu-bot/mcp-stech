from __future__ import annotations

from typing import Any

import httpx

from stech_mcp.services.product_work_dispatcher import RetryableWorkError


class ResearchIdentityHandler:
    def __init__(self, service: Any) -> None:
        self.service = service

    @staticmethod
    def _input(item: dict[str, Any]) -> dict[str, Any]:
        payload=item.get("input")
        return payload if isinstance(payload,dict) else {}

    def __call__(self,item:dict[str,Any],progress:Any)->dict[str,Any]:
        pn=str(item.get("partnumber") or "").strip().upper()
        requested=self._input(item).get("requested_fields")
        if requested is not None and not isinstance(requested,list): requested=None
        try:
            result=self.service.research(pn,requested,progress)
        except LookupError as exc:
            return {"status":"NO_DATA_FOUND","current_step":"product not found","error_code":"PRODUCT_NOT_FOUND","error_detail":str(exc)}
        except (TimeoutError,httpx.TimeoutException,httpx.TransportError) as exc:
            raise RetryableWorkError("TEMPORARY_IDENTITY_RESEARCH_ERROR",f"{type(exc).__name__}: {exc}") from exc
        state=str(result.get("state") or "").strip().upper()
        if state=="COMPLETED": return {"status":"COMPLETED","current_step":"identity research completed"}
        if state=="REVIEW_REQUIRED": return {"status":"REVIEW_REQUIRED","current_step":"identity review required","error_code":result.get("error_code") or "IDENTITY_CONFLICT","error_detail":"barcode identity requires review"}
        if state=="PARTIAL": return {"status":"PARTIAL","current_step":"identity research partial","error_code":result.get("error_code"),"error_detail":"no verified exact barcode found yet"}
        return {"status":"FAILED","current_step":"invalid identity result","error_code":"INVALID_IDENTITY_RESEARCH_STATE","error_detail":f"unsupported identity research state: {state or '<empty>'}"}
