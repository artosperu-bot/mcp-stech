from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class MailboxConflictError(RuntimeError):
    pass


class Mailbox:
    def __init__(self, repo_path: str | Path) -> None:
        self.repo_path = Path(repo_path)
        self.root = self.repo_path / "research_bridge"
        self.requests_dir = self.root / "requests"
        self.results_dir = self.root / "results"
        self.receipts_dir = self.root / "receipts"

    def ensure_layout(self) -> None:
        for path in (self.requests_dir, self.results_dir, self.receipts_dir):
            path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _canonical(payload: BaseModel | dict[str, Any]) -> str:
        if isinstance(payload, BaseModel):
            data = payload.model_dump(mode="json")
        else:
            data = payload
        return json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n"

    @staticmethod
    def _write_create_once(path: Path, content: str) -> Path:
        if path.exists():
            existing = path.read_text(encoding="utf-8")
            if existing == content:
                return path
            raise MailboxConflictError(f"mailbox file already exists with different content: {path.name}")
        temp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
        temp.write_text(content, encoding="utf-8", newline="\n")
        try:
            temp.replace(path)
        finally:
            if temp.exists():
                temp.unlink()
        return path

    def write_request(self, request: BaseModel) -> Path:
        self.ensure_layout()
        request_id = str(getattr(request, "request_id"))
        return self._write_create_once(
            self.requests_dir / f"{request_id}.json",
            self._canonical(request),
        )

    def write_receipt(self, request_id: str, payload: dict[str, Any]) -> Path:
        self.ensure_layout()
        content = {"request_id": request_id, **payload}
        return self._write_create_once(
            self.receipts_dir / f"{request_id}.json",
            self._canonical(content),
        )

    def pending_result_paths(self) -> list[Path]:
        self.ensure_layout()
        output: list[Path] = []
        for result_path in sorted(self.results_dir.glob("*.json")):
            receipt = self.receipts_dir / result_path.name
            if not receipt.exists():
                output.append(result_path)
        return output
