from stech_mcp.db.connection import sql_ping


class FakeCursor:
    def __init__(self):
        self.executed = []

    def execute(self, sql):
        self.executed.append(sql)
        return self

    def fetchone(self):
        return (1,)


class FakeConnection:
    def __init__(self):
        self.cursor_obj = FakeCursor()
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def close(self):
        self.closed = True


def test_sql_ping_executes_select_one_and_closes_connection():
    conn = FakeConnection()

    assert sql_ping(lambda: conn) is True
    assert conn.cursor_obj.executed == ["SELECT 1"]
    assert conn.closed is True
