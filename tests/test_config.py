from stech_mcp.config import Settings, build_source_connection_string


def test_builds_sql_auth_connection_string_without_logging_secrets():
    settings = Settings(
        stech_sql_server="PC005",
        stech_sql_database="DB_DISTRIBUIDORES",
        stech_sql_auth="sql",
        stech_sql_user="stech_mcp_ro",
        stech_sql_password="super-secret",
        stech_sql_driver="ODBC Driver 18 for SQL Server",
        stech_sql_trust_certificate=True,
    )

    value = build_source_connection_string(settings)

    assert "SERVER=PC005" in value
    assert "DATABASE=DB_DISTRIBUIDORES" in value
    assert "UID=stech_mcp_ro" in value
    assert "PWD=super-secret" in value
    assert "TrustServerCertificate=yes" in value


def test_builds_windows_auth_connection_string():
    settings = Settings(
        stech_sql_server="PC005",
        stech_sql_database="DB_DISTRIBUIDORES",
        stech_sql_auth="windows",
        stech_sql_driver="ODBC Driver 18 for SQL Server",
    )

    value = build_source_connection_string(settings)

    assert "Trusted_Connection=yes" in value
    assert "UID=" not in value
    assert "PWD=" not in value


def test_settings_accept_scr_v8_dist_environment(monkeypatch):
    monkeypatch.setenv("DIST_SQL_SERVER", "PC020")
    monkeypatch.setenv("DIST_SQL_DATABASE", "DB_DISTRIBUIDORES")
    monkeypatch.setenv("DIST_SQL_DRIVER", "ODBC Driver 18 for SQL Server")
    monkeypatch.setenv("DIST_SQL_TRUSTED_CONNECTION", "yes")
    monkeypatch.setenv("DIST_SQL_ENCRYPT", "no")

    settings = Settings(_env_file=None)

    assert settings.stech_sql_server == "PC020"
    assert settings.stech_sql_database == "DB_DISTRIBUIDORES"
    assert settings.stech_sql_auth == "windows"
    assert settings.stech_sql_encrypt is False
    assert settings.erp_product_view == "dbo.V_PRD_PRODUCTO_ACTUAL"
