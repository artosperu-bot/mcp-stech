from stech_mcp.background import BackgroundRuntime


class Scanner:
    def __init__(self):
        self.calls = 0

    def scan_once(self, limit=100, after_partnumber=""):
        self.calls += 1
        return {
            "scanned": 2,
            "technical_jobs_created": 1,
            "image_jobs_created": 1,
        }


def test_pause_resume_and_manual_scan_status():
    scanner = Scanner()
    runtime = BackgroundRuntime(
        scanner=scanner,
        scan_interval_seconds=600,
        max_jobs_per_scan=100,
    )
    assert runtime.status()["paused"] is False
    runtime.pause()
    assert runtime.status()["paused"] is True
    skipped = runtime.scan_now()
    assert skipped["skipped"] == "PAUSED"
    assert scanner.calls == 0
    runtime.resume()
    result = runtime.scan_now()
    assert result["scanned"] == 2
    assert scanner.calls == 1
    status = runtime.status()
    assert status["last_scan_result"]["image_jobs_created"] == 1