from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from typing import Any

from stech_mcp.config import Settings
from stech_mcp.db.connection import make_source_connection_factory, sql_ping
from stech_mcp.db.product_repository import ProductRepository


def build_check_report(
    *,
    partnumber: str,
    connection_factory: Callable[[], Any],
    view_name: str,
) -> dict[str, Any]:
    sql_ok = sql_ping(connection_factory)
    repo = ProductRepository(connection_factory, view_name=view_name)
    product = repo.get_by_partnumber(partnumber) if sql_ok else None
    return {
        "sql_source_status": "ok" if sql_ok else "error",
        "partnumber": partnumber.strip(),
        "found": product is not None,
        "product": product,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Prueba conexión SQL y product_get de STECH MCP")
    parser.add_argument("partnumber", help="Part Number real a consultar, por ejemplo 82YU00XYLM")
    args = parser.parse_args()

    settings = Settings()
    factory = make_source_connection_factory(settings)
    report = build_check_report(
        partnumber=args.partnumber,
        connection_factory=factory,
        view_name=settings.erp_product_view,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
