from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from stech_mcp import server_authoritative as server


def _dump(value):
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Detect products with missing/generic STECH taxonomy and queue them "
            "for review. This command never applies category changes."
        )
    )
    parser.add_argument("--limit", type=int, default=2000)
    parser.add_argument("--distributor", default="")
    args = parser.parse_args()

    limit = max(1, min(int(args.limit), 5000))
    distributor = str(args.distributor or "").strip() or None

    health = server.stech_health()
    if health.get("sql_source_status") != "ok":
        print(_dump({"ok": False, "stage": "health", "health": health}))
        return 2

    result = server.taxonomy_review_sync(limit=limit, distributor=distributor)
    print(
        _dump(
            {
                "ok": True,
                "finished_at_utc": datetime.now(timezone.utc).isoformat(),
                "write_policy": "REVIEW_QUEUE_ONLY",
                "source_apply_performed": False,
                **result,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
