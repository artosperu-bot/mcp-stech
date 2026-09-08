from pathlib import Path

import stech_mcp.server_authoritative as runtime


server = runtime._server


def test_product_work_tools_are_registered_as_server_callables():
    for name in (
        "product_work_job_create",
        "product_work_job_get",
        "product_work_job_list",
        "product_work_item_retry",
        "product_work_item_cancel",
    ):
        assert callable(getattr(server, name, None)), name


def test_authoritative_runtime_entrypoint_and_vtex_swap_are_not_reverted():
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    source = Path("src/stech_mcp/server_authoritative.py").read_text(encoding="utf-8")
    assert 'stech-mcp = "stech_mcp.server_authoritative:main"' in pyproject
    assert "_server.vtex_image_sync_service = vtex_image_sync_service" in source
    assert "_server.vtex_image_batch_service.sync_service = vtex_image_sync_service" in source
    assert "_server.product_loader_orchestrator.vtex_image_sync_service = vtex_image_sync_service" in source
