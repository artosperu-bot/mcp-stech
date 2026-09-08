from __future__ import annotations

from pathlib import Path


def test_server_registers_product_workbench_loader_vtex_and_image_tools():
    source = Path("src/stech_mcp/server.py").read_text(encoding="utf-8")
    required_tools = (
        "product_loader_preview",
        "product_loader_start",
        "product_loader_job_get",
        "product_loader_retry_item",
        "vtex_product_ensure",
        "product_image_approve",
        "product_image_reorder",
        "product_image_variant_register",
    )
    for name in required_tools:
        assert f"def {name}(" in source

    # Existing validated image pipeline remains registered and reused.
    for name in (
        "product_images_sync_local",
        "product_images_validate",
        "vtex_images_status",
        "vtex_images_sync",
    ):
        assert f"def {name}(" in source


def test_product_loader_start_validates_preview_before_starting_job():
    source = Path("src/stech_mcp/server.py").read_text(encoding="utf-8")
    marker = source.index("def product_loader_start(")
    body = source[marker: marker + 2400]
    assert "preview_product_rows" in body
    assert "has_blocking_errors" in body
    assert "product_loader_orchestrator.start" in body


def test_server_startup_resume_isolated_from_health_import():
    source = Path("src/stech_mcp/server.py").read_text(encoding="utf-8")
    assert "def _resume_product_loader_jobs" in source
    marker = source.index("def _resume_product_loader_jobs")
    body = source[marker: marker + 900]
    assert "try:" in body
    assert "except Exception" in body
    assert "resume_pending" in body
