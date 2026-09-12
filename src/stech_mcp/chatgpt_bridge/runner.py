from __future__ import annotations

import argparse
import threading
import time
from typing import Any

from stech_mcp.chatgpt_bridge.config import BridgeConfig
from stech_mcp.chatgpt_bridge.contracts import ResearchRequestV1, ResearchResultV1
from stech_mcp.chatgpt_bridge.exporter import ResearchRequestExporter
from stech_mcp.chatgpt_bridge.git_transport import GitTransport
from stech_mcp.chatgpt_bridge.importer import BridgeResultImporter
from stech_mcp.chatgpt_bridge.mailbox import Mailbox
from stech_mcp.config import Settings
from stech_mcp.db.connection import make_mcp_connection_factory, make_source_connection_factory
from stech_mcp.db.fact_candidate_repository import FactCandidateRepository
from stech_mcp.db.product_image_candidate_repository import ProductImageCandidateRepository
from stech_mcp.db.product_repository import ProductRepository
from stech_mcp.db.product_schema_repository import ProductSchemaRepository
from stech_mcp.db.product_work_execution_repository import ProductWorkExecutionRepository
from stech_mcp.db.product_work_query_repository import ProductWorkQueryRepository


class BridgeRunner:
    def __init__(
        self,
        *,
        mailbox: Mailbox,
        transport: Any,
        exporter: Any,
        importer: Any,
        max_export_per_cycle: int,
        max_import_per_cycle: int,
        poll_seconds: int = 60,
        sleep_fn: Any = time.sleep,
    ) -> None:
        self.mailbox = mailbox
        self.transport = transport
        self.exporter = exporter
        self.importer = importer
        self.max_export_per_cycle = max(int(max_export_per_cycle), 1)
        self.max_import_per_cycle = max(int(max_import_per_cycle), 1)
        self.poll_seconds = max(int(poll_seconds), 1)
        self.sleep_fn = sleep_fn

    def _load_request(self, request_id: str) -> ResearchRequestV1:
        path = self.mailbox.requests_dir / f"{request_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"research request not found: {request_id}")
        return ResearchRequestV1.model_validate_json(path.read_text(encoding="utf-8"))

    def run_once(self) -> dict[str, Any]:
        self.transport.pull()
        imported = 0
        for result_path in self.mailbox.pending_result_paths()[: self.max_import_per_cycle]:
            result = ResearchResultV1.model_validate_json(result_path.read_text(encoding="utf-8"))
            request = self._load_request(result.request_id)
            outcome = self.importer.import_result(request, result)
            self.mailbox.write_receipt(
                result.request_id,
                {
                    "status": "IMPORTED",
                    "outcome": outcome,
                    "imported_at": result.researched_at.isoformat(),
                },
            )
            imported += 1

        exported_rows = self.exporter.export_waiting(limit=self.max_export_per_cycle)
        pushed = bool(self.transport.commit_and_push())
        return {
            "imported": imported,
            "exported": len(exported_rows),
            "pushed": pushed,
        }

    def run_forever(self) -> None:
        while True:
            self.run_once()
            self.sleep_fn(self.poll_seconds)


def start_bridge_thread(
    config: BridgeConfig,
    runner: BridgeRunner,
    *,
    thread_factory: Any = threading.Thread,
) -> Any | None:
    """Run the local Git mailbox bridge inside the main STECH-MCP process.

    The scheduled ChatGPT task remains hourly and cloud-side; this daemon only
    exports WAITING_EXTERNAL_RESEARCH requests and imports finished result files.
    """
    if not config.enabled:
        return None
    thread = thread_factory(
        target=runner.run_forever,
        name="stech-chatgpt-bridge",
        daemon=True,
    )
    thread.start()
    return thread


def build_runner_from_environment() -> tuple[BridgeConfig, BridgeRunner]:
    settings = Settings()
    config = BridgeConfig.from_settings(settings)
    mailbox = Mailbox(config.repo_path)
    transport = GitTransport(config.repo_path, config.branch)

    mcp_connection_factory = make_mcp_connection_factory(settings)
    source_connection_factory = make_source_connection_factory(settings)
    work_query_repository = ProductWorkQueryRepository(mcp_connection_factory)
    work_execution_repository = ProductWorkExecutionRepository(mcp_connection_factory)
    product_repository = ProductRepository(
        source_connection_factory,
        view_name=settings.erp_product_view,
    )
    image_candidate_repository = ProductImageCandidateRepository(mcp_connection_factory)
    fact_candidate_repository = FactCandidateRepository(mcp_connection_factory)
    schema_repository = ProductSchemaRepository(mcp_connection_factory)

    exporter = ResearchRequestExporter(
        work_query_repository,
        product_repository,
        mailbox,
    )
    importer = BridgeResultImporter(
        image_candidate_repository=image_candidate_repository,
        fact_candidate_repository=fact_candidate_repository,
        work_repository=work_execution_repository,
        schema_repository=schema_repository,
    )
    runner = BridgeRunner(
        mailbox=mailbox,
        transport=transport,
        exporter=exporter,
        importer=importer,
        max_export_per_cycle=config.max_export_per_cycle,
        max_import_per_cycle=config.max_import_per_cycle,
        poll_seconds=config.poll_seconds,
    )
    return config, runner


def main() -> None:
    parser = argparse.ArgumentParser(description="STECH scheduled ChatGPT research bridge")
    parser.add_argument("--once", action="store_true", help="Run one pull/import/export/push cycle and exit")
    args = parser.parse_args()

    config, runner = build_runner_from_environment()
    if not config.enabled:
        print("STECH ChatGPT Research Bridge is disabled (STECH_CHATGPT_BRIDGE_ENABLED=false).")
        return
    if args.once:
        print(runner.run_once())
        return
    runner.run_forever()


if __name__ == "__main__":
    main()
