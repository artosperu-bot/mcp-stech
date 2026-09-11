from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Callable


class BackgroundRuntime:
    """Own the ProductScanner loop and optional Product Work worker threads."""

    def __init__(
        self,
        *,
        scanner: Any,
        scan_interval_seconds: int = 600,
        max_jobs_per_scan: int = 100,
        worker_factory: Callable[[int], Any] | None = None,
        max_workers: int = 0,
    ) -> None:
        self.scanner = scanner
        self.scan_interval_seconds = max(int(scan_interval_seconds), 30)
        self.max_jobs_per_scan = max(1, min(int(max_jobs_per_scan), 500))
        self.worker_factory = worker_factory
        self.max_workers = max(0, min(int(max_workers), 16))
        self._paused = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._worker_threads: list[threading.Thread] = []
        self._last_scan_at: datetime | None = None
        self._last_scan_result: dict[str, Any] | None = None
        self._next_scan_at: datetime | None = None

    def pause(self) -> dict[str, Any]:
        self._paused = True
        return self.status()

    def resume(self) -> dict[str, Any]:
        self._paused = False
        return self.status()

    def scan_now(self) -> dict[str, Any]:
        if self._paused:
            return {"skipped": "PAUSED"}
        result = self.scanner.scan_once(
            limit=self.max_jobs_per_scan,
            after_partnumber="",
        )
        now = datetime.now(timezone.utc)
        self._last_scan_at = now
        self._next_scan_at = now + timedelta(seconds=self.scan_interval_seconds)
        self._last_scan_result = result
        return result

    def status(self) -> dict[str, Any]:
        return {
            "running": bool(self._thread and self._thread.is_alive()),
            "paused": self._paused,
            "scan_interval_seconds": self.scan_interval_seconds,
            "max_jobs_per_scan": self.max_jobs_per_scan,
            "max_workers": self.max_workers,
            "last_scan_at": self._last_scan_at.isoformat() if self._last_scan_at else None,
            "next_scan_at": self._next_scan_at.isoformat() if self._next_scan_at else None,
            "last_scan_result": self._last_scan_result,
        }

    def config_get(self) -> dict[str, Any]:
        return {
            "scan_interval_seconds": self.scan_interval_seconds,
            "max_jobs_per_scan": self.max_jobs_per_scan,
            "max_workers": self.max_workers,
        }

    def _scan_loop(self) -> None:
        while not self._stop.is_set():
            if not self._paused:
                try:
                    self.scan_now()
                except Exception as exc:
                    self._last_scan_result = {"error": f"{type(exc).__name__}: {exc}"}
            self._stop.wait(self.scan_interval_seconds)

    def start(self) -> dict[str, Any]:
        if self._thread and self._thread.is_alive():
            return self.status()
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._scan_loop,
            name="stech-product-scanner",
            daemon=True,
        )
        self._thread.start()
        if self.worker_factory:
            for index in range(self.max_workers):
                worker = self.worker_factory(index + 1)
                thread = threading.Thread(
                    target=worker.run_forever,
                    args=(self._stop,),
                    name=f"stech-product-worker-{index + 1}",
                    daemon=True,
                )
                thread.start()
                self._worker_threads.append(thread)
        return self.status()

    def stop(self) -> dict[str, Any]:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        for thread in self._worker_threads:
            thread.join(timeout=2)
        self._worker_threads = []
        return self.status()