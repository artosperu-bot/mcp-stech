from __future__ import annotations

from decimal import Decimal
from typing import Any

from mcp.server import MCPServer

from stech_mcp.config import Settings
from stech_mcp.db.connection import make_source_connection_factory, sql_ping
from stech_mcp.db.product_repository import ProductRepository
from stech_mcp.domain.packaging_rules import estimate_package_weight, validate_package_dimensions
from stech_mcp.tools.core import health_snapshot

settings = Settings()
source_connection_factory = make_source_connection_factory(settings)
product_repository = ProductRepository(source_connection_factory, view_name=settings.erp_product_view)

mcp = MCPServer("STECH MCP")


@mcp.tool()
def stech_health() -> dict[str, Any]:
    """Comprueba que el MCP está vivo y que SQL Server responde."""
    return health_snapshot(lambda: sql_ping(source_connection_factory))


@mcp.tool()
def product_get(partnumber: str) -> dict[str, Any]:
    """Obtiene un producto del ERP S-TECH por Part Number desde la vista segura configurada."""
    product = product_repository.get_by_partnumber(partnumber)
    return {
        "found": product is not None,
        "partnumber": partnumber.strip(),
        "product": product,
    }


@mcp.tool()
def packaging_estimate_weight(
    screen_inches: float,
    device_weight_kg: float,
    is_gaming: bool = False,
) -> dict[str, Any]:
    """Estima peso de empaque solo cuando no existe una fuente confiable real."""
    estimated = estimate_package_weight(
        screen_inches=Decimal(str(screen_inches)),
        device_weight_kg=Decimal(str(device_weight_kg)),
        is_gaming=is_gaming,
    )
    return {
        "estimated_package_weight_kg": float(estimated),
        "method": "ESTIMATED",
        "requires_source_search_first": True,
    }


@mcp.tool()
def packaging_validate_dimensions(
    device_width_cm: float,
    device_depth_cm: float,
    device_height_cm: float,
    package_width_cm: float,
    package_length_cm: float,
    package_height_cm: float,
) -> dict[str, Any]:
    """Valida que las dimensiones declaradas de una caja sean físicamente mayores al equipo."""
    valid, reasons = validate_package_dimensions(
        device_width_cm=Decimal(str(device_width_cm)),
        device_depth_cm=Decimal(str(device_depth_cm)),
        device_height_cm=Decimal(str(device_height_cm)),
        package_width_cm=Decimal(str(package_width_cm)),
        package_length_cm=Decimal(str(package_length_cm)),
        package_height_cm=Decimal(str(package_height_cm)),
    )
    return {"valid": valid, "reasons": reasons}


def main() -> None:
    if settings.mcp_transport == "stdio":
        mcp.run()
        return

    import uvicorn

    app = mcp.streamable_http_app(stateless_http=True, json_response=True)
    uvicorn.run(app, host=settings.mcp_host, port=settings.mcp_port)


if __name__ == "__main__":
    main()
