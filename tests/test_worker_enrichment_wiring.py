from pathlib import Path

from stech_mcp.services.handlers.enrich_technical import EnrichTechnicalHandler


def test_environment_worker_registers_real_enrichment_handler_with_identity_alias():
    source = Path("src/stech_mcp/worker.py").read_text(encoding="utf-8")
    assert "EnrichTechnicalHandler" in source
    assert 'dispatcher.register("ENRICH_TECHNICAL", enrichment_handler)' in source
    assert 'dispatcher.register("ENRICH_TECHNICAL", enrichment_handler_not_installed)' not in source
    assert "RESEARCH_IDENTITY" in EnrichTechnicalHandler.aliases
