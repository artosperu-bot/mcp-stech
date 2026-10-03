from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from stech_mcp import server_authoritative as server
from stech_mcp.worker import build_worker_from_environment


def _dump(value):
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one bounded STECH Product Autofill cycle for Task Scheduler/HERMES."
    )
    parser.add_argument("--max-pages", type=int, default=100)
    parser.add_argument("--max-items", type=int, default=100)
    parser.add_argument("--scan-only", action="store_true")
    args = parser.parse_args()

    max_pages = max(1, min(int(args.max_pages), 1000))
    max_items = max(0, min(int(args.max_items), 1000))

    health = server.stech_health()
    if health.get("sql_source_status") != "ok":
        print(_dump({"ok": False, "stage": "health", "health": health}))
        return 2

    pages = 0
    scanned_rows = 0
    unique_products = 0
    technical_candidates = 0
    image_candidates = 0
    queued_technical = 0
    queued_images = 0
    job_ids = []
    scan_errors = []

    while pages < max_pages:
        result = server.background_runtime.scan_now()
        pages += 1
        scanned_rows += int(result.get("scanned") or 0)
        unique_products += int(result.get("unique_products_scanned") or 0)
        technical_candidates += int(result.get("technical_candidates") or 0)
        image_candidates += int(result.get("image_candidates") or 0)
        queued_technical += int(result.get("technical_jobs_created") or 0)
        queued_images += int(result.get("image_jobs_created") or 0)
        job_ids.extend(int(value) for value in (result.get("job_ids") or []))
        scan_errors.extend(list(result.get("errors") or []))

        status = server.background_runtime.status()
        if not status.get("after_partnumber"):
            break

    processed_items = 0
    if not args.scan_only and max_items > 0:
        worker = build_worker_from_environment(worker_suffix="autofill-cron")
        while processed_items < max_items:
            if not worker.run_once():
                break
            processed_items += 1

    output = {
        "ok": True,
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "pages": pages,
        "scanned_rows": scanned_rows,
        "unique_products_scanned": unique_products,
        "technical_candidates": technical_candidates,
        "image_candidates": image_candidates,
        "queued_technical_items": queued_technical,
        "queued_image_items": queued_images,
        "job_ids": job_ids,
        "processed_items": processed_items,
        "scan_errors": scan_errors,
        "queue_summary": server.background_jobs_summary(limit=100),
    }
    print(_dump(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
