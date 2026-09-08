from __future__ import annotations

import inspect

from stech_mcp.db.product_loader_repository import ProductLoaderRepository


def test_repository_exposes_atomic_job_transition_operations():
    required = {
        "claim_item",
        "update_item",
        "append_event",
        "reset_item_for_retry",
        "list_resumable_items",
        "set_job_status",
        "refresh_job_summary",
        "get_item",
    }
    missing = sorted(name for name in required if not hasattr(ProductLoaderRepository, name))
    assert missing == []


def test_repository_transition_sql_is_parameterized_and_never_clears_confirmed_vtex_ids():
    source = inspect.getsource(ProductLoaderRepository)
    assert "WITH (UPDLOCK, HOLDLOCK)" in source
    assert "WHERE product_loader_job_item_id = ?" in source
    assert "product_id_vtex = COALESCE(?, product_id_vtex)" in source
    assert "sku_id_vtex = COALESCE(?, sku_id_vtex)" in source
    assert "retry_count = retry_count + 1" in source
    assert "product_id_vtex = NULL" not in source
    assert "sku_id_vtex = NULL" not in source
