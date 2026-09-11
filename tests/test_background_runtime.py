from stech_mcp.background import BackgroundRuntime


class Scanner:
    def __init__(self):
        self.calls = []

    def scan_once(self, limit=100, after_partnumber=""):
        self.calls.append((limit, after_partnumber))
        if not after_partnumber:
            return {
                "scanned": 2,
                "technical_jobs_created": 1,
                "image_jobs_created": 1,
                "last_partnumber": "PN2",
            }
        return {
            "scanned": 1,
            "technical_jobs_created": 0,
            "image_jobs_created": 1,
            "last_partnumber": "PN3",
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
    assert scanner.calls == []
    runtime.resume()
    result = runtime.scan_now()
    assert result["scanned"] == 2
    assert scanner.calls == [(100, "")]
    status = runtime.status()
    assert status["last_scan_result"]["image_jobs_created"] == 1


def test_scans_advance_by_partnumber_and_wrap_after_short_page():
    scanner = Scanner()
    runtime = BackgroundRuntime(
        scanner=scanner,
        scan_interval_seconds=600,
        max_jobs_per_scan=2,
    )

    runtime.scan_now()
    runtime.scan_now()
    runtime.scan_now()

    assert scanner.calls == [
        (2, ""),
        (2, "PN2"),
        (2, ""),
    ]
