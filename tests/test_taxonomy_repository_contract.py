import inspect

from stech_mcp.db.taxonomy_repository import TaxonomyRepository


def test_repository_detects_missing_and_generic_taxonomy():
    source = inspect.getsource(TaxonomyRepository.list_missing).upper()

    assert "PRD_PRODUCTO_DISTRIBUIDOR" in source
    assert "DST_DISTRIBUIDOR" in source
    assert "SUBCATEGORIA" in source
    assert "'COMPONENTE','PRODUCTO','OTROS'" in source
    assert "'COMPONENTE','COMPONENTES','PRODUCTO','OTROS'" not in source


def test_apply_is_guarded_by_approval_and_source_product_id():
    source = inspect.getsource(TaxonomyRepository.apply_review).upper()

    assert '!= "APPROVED"' in source
    assert "PRODUCTO_DISTRIBUIDOR_ID = ?" in source
    assert "PART_NUMBER = ?" not in source
    assert "MCP_REVISION_APROBADA" in source
    assert "CAT_V2" in source


def test_sql_preview_is_parameterized():
    source = inspect.getsource(TaxonomyRepository.sql_preview).upper()

    assert "WHERE PRODUCTO_DISTRIBUIDOR_ID = ?" in source
    assert '"PARAMS"' in source


def test_reconcile_closes_reviews_already_classified_in_live_source():
    source = inspect.getsource(TaxonomyRepository.reconcile_resolved_reviews).upper()

    assert "RESOLVED_EXTERNALLY" in source
    assert "PRD_PRODUCTO_DISTRIBUIDOR" in source
    assert "CURRENT_CATEGORY" in source or "CATEGORIA" in source
    assert "_GENERIC_CATEGORIES" in source
