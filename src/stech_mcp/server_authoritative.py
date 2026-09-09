from __future__ import annotations

"""Authoritative additive runtime wiring for STECH MCP.

The legacy server remains the single registry for existing tools and shared
repositories. V2 capabilities are registered additively here so Product Work,
technical schemas, research/audit tools and authoritative VTEX image positions
can evolve without replacing legacy Product Loader or marketplace behavior.
"""

import os

from stech_mcp import server as _server
from stech_mcp.db.fact_candidate_repository import FactCandidateRepository
from stech_mcp.db.product_schema_repository import ProductSchemaRepository
from stech_mcp.db.product_work_control_repository import ProductWorkControlRepository
from stech_mcp.db.source_document_repository import SourceDocumentRepository
from stech_mcp.services.fact_extractor import FactExtractor
from stech_mcp.services.fact_promotion import FactPromotionService
from stech_mcp.services.multichannel_readiness import MultichannelReadinessService
from stech_mcp.services.product_technical_status import ProductTechnicalStatusService
from stech_mcp.services.product_work_service import ProductWorkService
from stech_mcp.services.research.research_planner import ResearchPlanner
from stech_mcp.services.source_document_service import SourceDocumentService
from stech_mcp.services.vtex_image_sync_authoritative import VtexImageSyncService
from stech_mcp.tools.product_research import register_product_research_tools
from stech_mcp.tools.product_schema import register_product_schema_tools
from stech_mcp.tools.product_work import register_product_work_tools


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

mcp = _server.mcp
settings = _server.settings


def main() -> None:
    _server.main()


if __name__ == "__main__":
    main()
