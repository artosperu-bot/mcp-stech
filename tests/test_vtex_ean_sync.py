from __future__ import annotations

from stech_mcp.services.vtex_ean_sync import VtexEanSyncService
from stech_mcp.services.vtex_image_client import VtexImageApiError


class FakeVtex:
    def __init__(self, *, remote_sequences=None, product_ref="82YU00XYLM", resolve_error=None):
        self.remote_sequences = list(remote_sequences or [[]])
        self.product_ref = product_ref
        self.resolve_error = resolve_error
        self.resolve_calls = []
        self.context_calls = []
        self.create_calls = []

    def resolve_sku_id(self, ref_id):
        self.resolve_calls.append(ref_id)
        if self.resolve_error:
            raise self.resolve_error
        return 251

    def get_sku_context(self, sku_id):
        self.context_calls.append(sku_id)
        return {"Id": sku_id, "ProductRefId": self.product_ref, "RefId": f"{self.product_ref}-S"}

    def get_sku_eans(self, sku_id):
        if len(self.remote_sequences) > 1:
            return self.remote_sequences.pop(0)
        return list(self.remote_sequences[0])

    def create_sku_ean(self, sku_id, ean):
        self.create_calls.append((sku_id, ean))
        return {}


def test_same_remote_ean_is_idempotent():
    client = FakeVtex(remote_sequences=[["0197528523880"]])
    result = VtexEanSyncService(client).sync(
        "82YU00XYLM", {"ean": "0197528523880"}
    )

    assert result["state"] == "VTEX_EAN_ALREADY_PRESENT"
    assert result["sku_id"] == 251
    assert client.resolve_calls == ["82YU00XYLM-S"]
    assert client.create_calls == []


def test_equivalent_canonical_remote_gtin_is_already_present():
    client = FakeVtex(remote_sequences=[["00740617352214"]])
    result = VtexEanSyncService(client).sync(
        "82YU00XYLM", {"upc": "740617352214"}
    )

    assert result["state"] == "VTEX_EAN_ALREADY_PRESENT"
    assert client.create_calls == []


def test_different_remote_ean_blocks_write():
    client = FakeVtex(remote_sequences=[["0197528523880"]])
    result = VtexEanSyncService(client).sync(
        "82YU00XYLM", {"upc": "740617352214"}
    )

    assert result["state"] == "VTEX_EAN_CONFLICT"
    assert result["remote_eans"] == ["0197528523880"]
    assert client.create_calls == []


def test_empty_remote_ean_is_created_once_and_reverified():
    client = FakeVtex(remote_sequences=[[], ["740617352214"]])
    result = VtexEanSyncService(client).sync(
        "82YU00XYLM", {"upc": "740617352214"}
    )

    assert result["state"] == "VTEX_EAN_SYNCED"
    assert result["sku_id"] == 251
    assert result["ean"] == "740617352214"
    assert client.create_calls == [(251, "740617352214")]


def test_invalid_local_value_never_reaches_vtex():
    client = FakeVtex()
    result = VtexEanSyncService(client).sync(
        "82YU00XYLM", {"upc": "740617352215"}
    )

    assert result["state"] == "VTEX_EAN_INVALID_LOCAL_VALUE"
    assert client.resolve_calls == []
    assert client.create_calls == []


def test_wrong_vtex_product_ref_blocks_write():
    client = FakeVtex(product_ref="OTHER-PN")
    result = VtexEanSyncService(client).sync(
        "82YU00XYLM", {"ean": "0197528523880"}
    )

    assert result["state"] == "VTEX_SKU_MISMATCH"
    assert client.create_calls == []


def test_forbidden_is_classified_without_writing():
    client = FakeVtex(
        resolve_error=VtexImageApiError(
            operation="resolve_sku_id",
            status=403,
            body="forbidden",
            url="https://example.test",
        )
    )
    result = VtexEanSyncService(client).sync(
        "82YU00XYLM", {"ean": "0197528523880"}
    )

    assert result["state"] == "VTEX_EAN_FORBIDDEN"
    assert result["retryable"] is False
    assert client.create_calls == []


def test_server_error_is_retryable():
    client = FakeVtex(
        resolve_error=VtexImageApiError(
            operation="resolve_sku_id",
            status=503,
            body="temporarily unavailable",
            url="https://example.test",
        )
    )
    result = VtexEanSyncService(client).sync(
        "82YU00XYLM", {"ean": "0197528523880"}
    )

    assert result["state"] == "VTEX_EAN_TEMPORARY_ERROR"
    assert result["retryable"] is True
