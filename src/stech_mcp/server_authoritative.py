from __future__ import annotations

"""Runtime wiring for authoritative VTEX image positions.

The existing server module remains the single registry for MCP tools and shared
repositories. This module swaps only the VTEX image sync service used by those
registered tools, the batch service, and Product Loader. Product Work V2 tools
are registered additively after that swap; no existing tool is replaced.
"""

import os

from stech_mcp import server as _server
from stech_mcp.db.product_work_control_repository import ProductWorkControlRepository
from stech_mcp.services.product_work_service import ProductWorkService
from stech_mcp.services.vtex_image_sync_authoritative import VtexImageSyncService
from stech_mcp.tools.product_work import register_product_work_tools


vtex_image_sync_service = VtexImageSyncService(
    local_service=_server.local_image_sync_service,
    vtex_client=_server.vtex_image_client,
    publication_repository=_server.image_publication_repository,
    signer=_server.image_signer,
    audit_repository=_server.product_master_repository,
)

# MCP tool functions registered in stech_mcp.server resolve this module-global
# service at call time, so replacing it here switches only image behavior.
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

mcp = _server.mcp
settings = _server.settings


def main() -> None:
    _server.main()


if __name__ == "__main__":
    main()
