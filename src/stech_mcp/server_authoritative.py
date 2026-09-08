from __future__ import annotations

"""Runtime wiring for authoritative VTEX image positions.

The existing server module remains the single registry for MCP tools and shared
repositories. This module swaps only the VTEX image sync service used by those
registered tools, the batch service, and Product Loader. No other MCP behavior
is changed.
"""

from stech_mcp import server as _server
from stech_mcp.services.vtex_image_sync_authoritative import VtexImageSyncService


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

mcp = _server.mcp
settings = _server.settings


def main() -> None:
    _server.main()


if __name__ == "__main__":
    main()
