from __future__ import annotations

"""Authoritative additive runtime wiring for STECH MCP.

The legacy server remains the registry for existing tools and shared repositories.
V2 capabilities are registered additively here so Product Work, technical schemas,
research/audit, image research and the background scanner evolve without replacing
legacy Product Loader or marketplace behavior.
"""

import os

from stech_mcp import server as _server
from stech_mcp.background import BackgroundRuntime
from stech_mcp.background_config import BackgroundConfig
from stech_mcp.db.fact_candidate_repository import FactCandidateRepository
from stech_mcp.db.product_image_candidate_repository import ProductImageCandidateRepository
from stech_mcp.db.product_schema_repository import ProductSchemaRepository
from stech_mcp.db.product_work_control_repository import ProductWorkControlRepository
from stech_mcp.db.source_document_repository import SourceDocumentRepository
from stech_mcp.services.fact_extractor import FactExtractor
from stech_mcp.services.fact_promotion import FactPromotionService
from stech_mcp.services.multichannel_readiness import MultichannelReadinessService
from stech_mcp.services.product_image_readiness import ProductImageReadinessService
from stech_mcp.services.product_image_research import ProductImageResearchService
from stech_mcp.services.product_scanner import ProductScanner
from stech_mcp.services.product_technical_status import ProductTechnicalStatusService
from stech_mcp.services.product_work_service import ProductWorkService
from stech_mcp.services.research.brave_image_search_provider import BraveImageSearchProvider
from stech_mcp.services.research.research_planner import ResearchPlanner
from stech_mcp.services.source_document_service import SourceDocumentService
from stech_mcp.services.vtex_image_sync_authoritative import VtexImageSyncService
from stech_mcp.tools.product_research import register_product_research_tools
from stech_mcp.tools.product_schema import register_product_schema_tools
from stech_mcp.tools.product_work import register_product_work_tools
from stech_mcp.tools.product_workspace_v2 import register_product_workspace_v2_tools
from stech_mcp.worker import build_worker_from_environment


vtex_image_sync_service = VtexImageSyncService(
    local_service=_server.local_image_sync_service,
    vtex_client=_server.vtex_image_client,
    publication_repository=_server.image_publication_repository,
    signer=_server.image_signer,
    audit_repository=_server.product_master_repository,
)

# Existing MCP tool functions resolve these module globals at call time. Only
# authoritative VTEX image behavior is swapped; no other legacy tool is replaced.
_server.vtex_image_sync_service = vtex_image_sync_service
_server.vtex_image_batch_service.sync_service = vtex_image_sync_service
_server.product_loader_orchestrator.vtex_image_sync_service = vtex_image_sync_service

# Product Work V2 is additive and uses its own tables/repository. It does not
# replace product_loader_job or any existing VTEX service.
product_work_repository = ProductWorkControlRepository(_server.mcp_connection_factory)
product_work_service = ProductWorkService(
    product_work_repository,
    max_attempts=int(os.getenv("STECH_WORKER_MAX_ATTEMPTS", "3")),
)
product_work_tools = register_product_work_tools(
    _server.mcp,
    product_work_service,
    namespace=_server,
)

# Canonical technical schemas are additive. They reuse the existing V8 product
# repository and approved enrichment repository without changing them.
product_schema_repository = ProductSchemaRepository(_server.mcp_connection_factory)
product_technical_status_service = ProductTechnicalStatusService(
    product_repository=_server.product_repository,
    enrichment_repository=_server.enrichment_repository,
    schema_repository=product_schema_repository,
)
product_schema_tools = register_product_schema_tools(
    _server.mcp,
    schema_repository=product_schema_repository,
    technical_status_service=product_technical_status_service,
    namespace=_server,
)

# Research/audit V2 uses candidate/evidence tables and the existing verified
# enrichment write path. Promotion never writes directly to product_enrichment.
fact_candidate_repository = FactCandidateRepository(_server.mcp_connection_factory)
source_document_repository = SourceDocumentRepository(_server.mcp_connection_factory)
source_document_service = SourceDocumentService(
    document_repository=source_document_repository,
)
fact_promotion_service = FactPromotionService(
    verification_service=_server.product_field_verification_service,
    enrichment_repository=_server.enrichment_repository,
    candidate_repository=fact_candidate_repository,
)
multichannel_readiness_service = MultichannelReadinessService(
    product_repository=_server.product_repository,
    enrichment_repository=_server.enrichment_repository,
    technical_status_service=product_technical_status_service,
)
product_research_tools = register_product_research_tools(
    _server.mcp,
    product_repository=_server.product_repository,
    technical_status_service=product_technical_status_service,
    research_planner=ResearchPlanner(),
    source_document_service=source_document_service,
    fact_extractor=FactExtractor(),
    candidate_repository=fact_candidate_repository,
    promotion_service=fact_promotion_service,
    multichannel_readiness_service=multichannel_readiness_service,
    namespace=_server,
)

# First-class image readiness/research. Web results stay as candidates; the
# research path never publishes to VTEX or silently approves an ambiguous image.
product_image_candidate_repository = ProductImageCandidateRepository(
    _server.mcp_connection_factory
)
product_image_readiness_service = ProductImageReadinessService(
    product_repository=_server.product_repository,
    source_image_repository=_server.deltron_image_repository,
    workspace_image_repository=_server.product_image_repository,
    policy_repository=product_image_candidate_repository,
)
product_image_search_provider = BraveImageSearchProvider(
    api_key=os.getenv("STECH_BRAVE_SEARCH_API_KEY", ""),
    country=os.getenv("STECH_SEARCH_COUNTRY", "PE"),
    search_lang=os.getenv("STECH_SEARCH_LANG", "es"),
)
product_image_research_service = ProductImageResearchService(
    product_repository=_server.product_repository,
    local_image_sync_service=_server.local_image_sync_service,
    readiness_service=product_image_readiness_service,
    candidate_repository=product_image_candidate_repository,
    search_provider=product_image_search_provider,
)

background_config = BackgroundConfig.from_env()
product_scanner = ProductScanner(
    product_repository=_server.product_repository,
    technical_status_service=product_technical_status_service,
    image_readiness_service=product_image_readiness_service,
    work_service=product_work_service,
)
background_runtime = BackgroundRuntime(
    scanner=product_scanner,
    scan_interval_seconds=background_config.scan_interval_minutes * 60,
    max_jobs_per_scan=background_config.max_jobs_per_scan,
    worker_factory=(
        (lambda index: build_worker_from_environment(worker_suffix=f"bg{index}"))
        if background_config.background_enabled
        else None
    ),
    max_workers=(background_config.max_workers if background_config.background_enabled else 0),
)
product_workspace_v2_tools = register_product_workspace_v2_tools(
    _server.mcp,
    runtime=background_runtime,
    work_service=product_work_service,
    image_readiness_service=product_image_readiness_service,
    image_research_service=product_image_research_service,
    candidate_repository=product_image_candidate_repository,
    namespace=_server,
)

mcp = _server.mcp
settings = _server.settings


def main() -> None:
    # Threads are started only from the executable entry point, never at import
    # time. This keeps tests/imports deterministic while production can run 24/7.
    if background_config.background_enabled and background_config.scanner_enabled:
        background_runtime.start()
    _server.main()


if __name__ == "__main__":
    main()
