from stech_mcp.tools.core import health_snapshot


def test_health_snapshot_can_include_authoritative_background_runtime():
    result = health_snapshot(
        lambda: True,
        lambda: {
            "authoritative_v2": True,
            "background": {
                "running": True,
                "paused": False,
                "next_scan_at": "2026-09-11T04:00:00+00:00",
                "workers_alive": 3,
                "jobs": {"RUNNING": 2, "FAILED": 1},
            },
        },
    )

    assert result["mcp_status"] == "ok"
    assert result["sql_source_status"] == "ok"
    assert result["authoritative_v2"] is True
    assert result["background"]["running"] is True
    assert result["background"]["workers_alive"] == 3


def test_health_snapshot_keeps_base_health_when_extra_snapshot_fails():
    def fail():
        raise RuntimeError("background unavailable")

    result = health_snapshot(lambda: True, fail)

    assert result["mcp_status"] == "ok"
    assert result["sql_source_status"] == "ok"
    assert "background_snapshot_error" in result
