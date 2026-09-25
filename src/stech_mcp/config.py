from __future__ import annotations

import secrets
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, PrivateAttr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración del MCP compatible con el entorno real de scr/v8-identity.

    STECH_SQL_* tiene prioridad cuando se define. Si no existe, se reutilizan
    directamente las variables DIST_SQL_* del monitor de distribuidores.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        extra="ignore",
        populate_by_name=True,
    )

    stech_sql_driver: str = Field(
        "ODBC Driver 18 for SQL Server",
        validation_alias=AliasChoices("STECH_SQL_DRIVER", "DIST_SQL_DRIVER"),
    )
    stech_sql_server: str = Field(
        "localhost",
        validation_alias=AliasChoices("STECH_SQL_SERVER", "DIST_SQL_SERVER"),
    )
    stech_sql_database: str = Field(
        "DB_DISTRIBUIDORES",
        validation_alias=AliasChoices("STECH_SQL_DATABASE", "DIST_SQL_DATABASE"),
    )
    stech_sql_auth: Literal["sql", "windows"] = Field(
        "windows",
        validation_alias="STECH_SQL_AUTH",
    )
    stech_sql_user: str | None = Field(
        None,
        validation_alias=AliasChoices("STECH_SQL_USER", "DIST_SQL_USER"),
    )
    stech_sql_password: str | None = Field(
        None,
        validation_alias=AliasChoices("STECH_SQL_PASSWORD", "DIST_SQL_PASSWORD"),
    )
    stech_sql_trust_certificate: bool = Field(
        True,
        validation_alias="STECH_SQL_TRUST_CERTIFICATE",
    )
    stech_sql_encrypt: bool = Field(
        False,
        validation_alias=AliasChoices("STECH_SQL_ENCRYPT", "DIST_SQL_ENCRYPT"),
    )
    dist_sql_trusted_connection: bool | None = Field(
        None,
        validation_alias="DIST_SQL_TRUSTED_CONNECTION",
        exclude=True,
    )

    mcp_sql_database: str = "STECH_MCP"
    mcp_sql_user: str | None = None
    mcp_sql_password: str | None = None
    mcp_transport: Literal["stdio", "streamable-http"] = "stdio"
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8765
    mcp_public_host: str = "mcp.artos.pe"
    erp_product_view: str = "dbo.V_PRD_PRODUCTO_ACTUAL"

    # VTEX image sync. The existing V8 channel credential names are accepted as
    # aliases so PC020 can reuse the same API credential pair without renaming it.
    stech_image_root: str = r"C:\STECH_IMAGENES"
    vtex_account_name: str = "ststore227"
    vtex_environment: str = "vtexcommercestable.com.br"
    vtex_app_key: str | None = Field(
        None,
        validation_alias=AliasChoices("VTEX_APP_KEY", "CHN_CRED_VTEX_STECH_APP_KEY"),
    )
    vtex_app_token: str | None = Field(
        None,
        validation_alias=AliasChoices("VTEX_APP_TOKEN", "CHN_CRED_VTEX_STECH_APP_TOKEN"),
    )
    vtex_image_public_base: str = "https://mcp.artos.pe/vtex-images"
    vtex_image_signing_secret: str | None = None
    vtex_image_url_ttl_seconds: int = 900
    vtex_http_timeout_seconds: int = 30

    # Falabella image bridge. Originals remain untouched under STECH_IMAGE_ROOT;
    # channel-ready JPEG variants are stored separately and exposed only by
    # signed, expiring Cloudflare URLs.
    stech_channel_image_root: str = r"C:\STECH_IMAGENES_CHANNELS"
    falabella_image_public_base: str = "https://mcp.artos.pe/falabella-images"
    falabella_image_signing_secret: str | None = None
    falabella_image_signing_secret_file: str | None = None
    falabella_image_url_ttl_seconds: int = 172800
    falabella_image_canvas_px: int = 1500
    falabella_image_max_bytes: int = 150 * 1024
    falabella_image_min_source_px: int = 500
    falabella_image_margin_px: int = 30

    _generated_vtex_image_signing_secret: str | None = PrivateAttr(default=None)

    @model_validator(mode="after")
    def _derive_legacy_auth(self) -> "Settings":
        # Si stech_sql_auth fue provisto explícitamente (constructor, entorno o .env),
        # siempre gana. Solo derivamos la autenticación desde DIST_SQL_TRUSTED_CONNECTION
        # cuando stech_sql_auth conserva su valor por defecto.
        if "stech_sql_auth" not in self.model_fields_set and self.dist_sql_trusted_connection is not None:
            self.stech_sql_auth = "windows" if self.dist_sql_trusted_connection else "sql"
        if self.vtex_image_url_ttl_seconds <= 0:
            raise ValueError("VTEX_IMAGE_URL_TTL_SECONDS must be greater than zero")
        if self.vtex_http_timeout_seconds <= 0:
            raise ValueError("VTEX_HTTP_TIMEOUT_SECONDS must be greater than zero")
        if not (500 <= self.falabella_image_canvas_px <= 2000):
            raise ValueError("FALABELLA_IMAGE_CANVAS_PX must be between 500 and 2000")
        if self.falabella_image_url_ttl_seconds <= 0:
            raise ValueError("FALABELLA_IMAGE_URL_TTL_SECONDS must be greater than zero")
        if self.falabella_image_max_bytes <= 0:
            raise ValueError("FALABELLA_IMAGE_MAX_BYTES must be greater than zero")
        if self.falabella_image_min_source_px <= 0:
            raise ValueError("FALABELLA_IMAGE_MIN_SOURCE_PX must be greater than zero")
        if self.falabella_image_margin_px < 0 or self.falabella_image_margin_px * 2 >= self.falabella_image_canvas_px:
            raise ValueError("FALABELLA_IMAGE_MARGIN_PX is invalid for the configured canvas")
        return self

    def falabella_image_signing_secret_value(self) -> str:
        """Return a persistent signing secret for long-lived Falabella image URLs.

        An explicit FALABELLA_IMAGE_SIGNING_SECRET wins. If absent, the secret is
        stored outside Git under STECH_IMAGE_CHANNEL_ROOT so MCP restarts do not
        invalidate URLs that Seller Center may still be downloading.
        """

        explicit = str(self.falabella_image_signing_secret or "").strip()
        if explicit:
            return explicit

        configured = str(self.falabella_image_signing_secret_file or "").strip()
        secret_path = (
            Path(configured).expanduser()
            if configured
            else Path(self.stech_channel_image_root).expanduser() / ".falabella-image-signing-secret"
        )
        secret_path.parent.mkdir(parents=True, exist_ok=True)
        if secret_path.is_file():
            existing = secret_path.read_text(encoding="utf-8").strip()
            if existing:
                return existing

        value = secrets.token_urlsafe(48)
        secret_path.write_text(value, encoding="utf-8")
        return value

    def vtex_image_signing_secret_value(self) -> str:
        """Return explicit secret or lazily generate one for this MCP process.

        Signed image URLs live only a few minutes, so invalidating outstanding
        URLs after a process restart is safe and removes a manual setup step.
        """

        explicit = str(self.vtex_image_signing_secret or "").strip()
        if explicit:
            return explicit
        if self._generated_vtex_image_signing_secret is None:
            self._generated_vtex_image_signing_secret = secrets.token_urlsafe(48)
        return self._generated_vtex_image_signing_secret


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
            raise ValueError("SQL authentication requires STECH_SQL_USER/DIST_SQL_USER and password")
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
