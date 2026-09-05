from stech_mcp.tools.core import health_snapshot


def test_health_reports_sql_ok():
    result = health_snapshot(lambda: True)
    assert result["mcp_status"] == "ok"
    assert result["sql_source_status"] == "ok"


def test_health_reports_sql_error_without_crashing():
    def boom():
        raise RuntimeError("offline")

    result = health_snapshot(boom)
    assert result["mcp_status"] == "ok"
    assert result["sql_source_status"] == "error"
    assert "offline" in result["detail"]
