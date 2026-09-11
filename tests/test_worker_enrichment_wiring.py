from pathlib import Path


def test_environment_worker_registers_real_enrichment_handlers():
    source = Path("src/stech_mcp/worker.py").read_text(encoding="utf-8")
    assert "EnrichTechnicalHandler" in source
    assert 'dispatcher.register("ENRICH_TECHNICAL", enrichment_handler)' in source
    assert "ResearchIdentityHandler" in source
    assert 'dispatcher.register("RESEARCH_IDENTITY", identity_handler)' in source
    assert 'dispatcher.register("ENRICH_TECHNICAL", enrichment_handler_not_installed)' not in source
