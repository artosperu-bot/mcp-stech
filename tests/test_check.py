from stech_mcp.check import build_check_report


class FakeCursor:
    description = [("partnumber",), ("marca",)]

    def execute(self, sql, *params):
        self.sql = sql
        self.params = params
        return self

    def fetchone(self):
        if self.sql == "SELECT 1":
            return (1,)
        return ("82YU00XYLM", "LENOVO")


class FakeConnection:
    def __init__(self):
        self.cursor_obj = FakeCursor()
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def close(self):
        self.closed = True


def test_build_check_report_returns_sql_health_and_product():
    connections = []

    def factory():
        conn = FakeConnection()
        connections.append(conn)
        return conn

    report = build_check_report(
        partnumber="82YU00XYLM",
        connection_factory=factory,
        view_name="dbo.V_MCP_PRODUCTO",
    )

    assert report["sql_source_status"] == "ok"
    assert report["found"] is True
    assert report["product"]["marca"] == "LENOVO"
    assert all(conn.closed for conn in connections)
