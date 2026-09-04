from stech_mcp.config import Settings, build_source_connection_string


def test_builds_sql_auth_connection_string_without_logging_secrets():
    settings = Settings(
        stech_sql_server="PC005",
        stech_sql_database="DB_ST",
        stech_sql_auth="sql",
        stech_sql_user="stech_mcp_ro",
        stech_sql_password="super-secret",
        stech_sql_driver="ODBC Driver 18 for SQL Server",
        stech_sql_trust_certificate=True,
    )

    value = build_source_connection_string(settings)

    assert "SERVER=PC005" in value
    assert "DATABASE=DB_ST" in value
    assert "UID=stech_mcp_ro" in value
    assert "PWD=super-secret" in value
    assert "TrustServerCertificate=yes" in value


def test_builds_windows_auth_connection_string():
    settings = Settings(
        stech_sql_server="PC005",
        stech_sql_database="DB_ST",
        stech_sql_auth="windows",
        stech_sql_driver="ODBC Driver 18 for SQL Server",
    )

    value = build_source_connection_string(settings)

    assert "Trusted_Connection=yes" in value
    assert "UID=" not in value
    assert "PWD=" not in value
