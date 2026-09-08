from __future__ import annotations

import os
import threading

import servicemanager
import win32event
import win32service
import win32serviceutil

from stech_mcp.worker import build_worker_from_environment


class STECHEnrichmentWorkerService(win32serviceutil.ServiceFramework):
    _svc_name_ = "STECHEnrichmentWorker"
    _svc_display_name_ = "S-TECH Product Enrichment Worker"
    _svc_description_ = "Procesa la cola persistente Product Work V2 sin ejecutar dentro del servidor MCP."

    def __init__(self, args):
        super().__init__(args)
        self.stop_event = threading.Event()
        self.stop_handle = win32event.CreateEvent(None, 0, 0, None)

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self.stop_event.set()
        win32event.SetEvent(self.stop_handle)

    def SvcDoRun(self):
        enabled = os.getenv("STECH_WORKER_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
        if not enabled:
            servicemanager.LogInfoMsg("STECHEnrichmentWorker disabled by STECH_WORKER_ENABLED")
            return

        servicemanager.LogInfoMsg("STECHEnrichmentWorker starting")
        worker = build_worker_from_environment()
        try:
            worker.run_forever(self.stop_event)
        finally:
            servicemanager.LogInfoMsg("STECHEnrichmentWorker stopped")


if __name__ == "__main__":
    win32serviceutil.HandleCommandLine(STECHEnrichmentWorkerService)
