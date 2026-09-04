from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    stech_sql_driver: str = "ODBC Driver 18 for SQL Server"
    stech_sql_server: str = "localhost"
    stech_sql_database: str = "DB_ST"
    stech_sql_auth: Literal["sql", "windows"] = "windows"
    stech_sql_user: str | None = None
    stech_sql_password: str | None = None
    stech_sql_trust_certificate: bool = True
    stech_sql_encrypt: bool = True

    mcp_sql_database: str = "STECH_MCP"
    mcp_sql_user: str | None = None
    mcp_sql_password: str | None = None
    mcp_transport: Literal["stdio", "streamable-http"] = "stdio"
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8765
    erp_product_view: str = "dbo.V_MCP_PRODUCTO"


def _base_connection_parts(settings: Settings, database: str) -> list[str]:
    return [
        f"DRIVER={{{settings.stech_sql_driver}}}",
        f"SERVER={settings.stech_sql_server}",
        f"DATABASE={database}",
        f"Encrypt={'yes' if settings.stech_sql_encrypt else 'no'}",
        f"TrustServerCertificate={'yes' if settings.stech_sql_trust_certificate else 'no'}",
    ]


def build_source_connection_string(settings: Settings) -> str:
    parts = _base_connection_parts(settings, settings.stech_sql_database)
    if settings.stech_sql_auth == "windows":
        parts.append("Trusted_Connection=yes")
    else:
        if not settings.stech_sql_user or not settings.stech_sql_password:
            raise ValueError("SQL authentication requires STECH_SQL_USER and STECH_SQL_PASSWORD")
        parts.extend([f"UID={settings.stech_sql_user}", f"PWD={settings.stech_sql_password}"])
    return ";".join(parts) + ";"


def build_mcp_connection_string(settings: Settings) -> str:
    parts = _base_connection_parts(settings, settings.mcp_sql_database)
    if settings.mcp_sql_user and settings.mcp_sql_password:
        parts.extend([f"UID={settings.mcp_sql_user}", f"PWD={settings.mcp_sql_password}"])
    elif settings.stech_sql_auth == "windows":
        parts.append("Trusted_Connection=yes")
    else:
        raise ValueError("MCP SQL credentials are required when Windows authentication is not used")
    return ";".join(parts) + ";"
