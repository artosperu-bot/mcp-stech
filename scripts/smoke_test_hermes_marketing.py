from __future__ import annotations

import argparse
import json

from stech_mcp import server_authoritative as server


def _json(value):
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smoke test HERMES marketing context against the real STECH MCP databases."
    )
    parser.add_argument("partnumber", help="Exact Part Number to test")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Print the complete marketing context and media manifest",
    )
    args = parser.parse_args()

    pn = args.partnumber.strip().upper()
    print("=" * 78)
    print("STECH MCP -> HERMES MARKETING SMOKE TEST")
    print(f"Part Number: {pn}")
    print("=" * 78)

    health = server.stech_health()
    print(f"MCP SQL source: {health.get('sql_source_status')}")
    if health.get("sql_source_status") != "ok":
        print(_json(health))
        return 2

    context = server.marketing_product_context(pn)
    if not context.get("found"):
        print("PRODUCTO: NO ENCONTRADO")
        print(_json(context))
        return 3

    operational = dict(context.get("operational") or {})
    distributors = list(operational.get("distributors") or [])
    print(f"Distribuidores actuales encontrados: {operational.get('distributor_count', len(distributors))}")
    for index, row in enumerate(distributors, 1):
        print(
            f"  {index:02d}. "
            f"{row.get('distribuidor') or row.get('distribuidor_codigo') or 'SIN_NOMBRE'} | "
            f"stock={row.get('stock_valor', row.get('stock_actual_valor'))} | "
            f"precio_source={row.get('precio_actual_usd', row.get('precio_usd', row.get('precio')))} | "
            f"ultima_observacion={row.get('ultima_observacion')}"
        )

    readiness = server.marketing_readiness(pn)
    print("-" * 78)
    print(f"Marketing readiness: {readiness.get('state')}")
    print(f"Creative generation allowed: {readiness.get('creative_generation_allowed')}")
    print(f"Publication allowed by STECH_CORE: {readiness.get('publication_allowed')}")
    if readiness.get("blockers"):
        print("Blockers:")
        for item in readiness["blockers"]:
            print(f"  - {item}")
    if readiness.get("warnings"):
        print("Warnings:")
        for item in readiness["warnings"]:
            print(f"  - {item}")

    manifest = server.marketing_media_manifest(pn)
    lock = dict(manifest.get("product_lock") or {})
    print("-" * 78)
    print(f"PRODUCT_LOCK: {lock.get('enabled')}")
    print(f"Referencias utilizables: {lock.get('reference_count', 0)}")
    if manifest.get("source_images"):
        by_distributor = {}
        for row in manifest["source_images"]:
            distributor = row.get("distributor") or "SIN_NOMBRE"
            by_distributor[distributor] = by_distributor.get(distributor, 0) + int(
                bool(row.get("eligible_reference"))
            )
        print("Referencias exactas/aprobadas por distribuidor:")
        for distributor, count in sorted(by_distributor.items()):
            print(f"  - {distributor}: {count}")

    if args.full:
        print("\n=== CONTEXTO COMPLETO ===")
        print(_json(context))
        print("\n=== MEDIA MANIFEST COMPLETO ===")
        print(_json(manifest))

    print("=" * 78)
    print("OK: smoke test completado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
