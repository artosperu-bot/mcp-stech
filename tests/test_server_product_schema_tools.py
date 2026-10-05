from pathlib import Path

import stech_mcp.server_authoritative as runtime


server = runtime._server


def test_schema_tools_are_registered_as_server_callables():
    for name in ("product_schema_get", "product_technical_status"):
        assert callable(getattr(server, name, None)), name


def test_schema_registration_remains_additive_to_authoritative_runtime():
    source = Path("src/stech_mcp/server_authoritative.py").read_text(encoding="utf-8")
    assert "_server.vtex_image_sync_service = vtex_image_sync_service" in source
    assert "register_product_work_tools" in source
    assert "register_product_schema_tools" in source
