from stech_mcp.config import Settings


def test_vtex_image_config_accepts_existing_channel_credential_aliases(monkeypatch):
    monkeypatch.setenv("CHN_CRED_VTEX_STECH_APP_KEY", "key-from-channel")
    monkeypatch.setenv("CHN_CRED_VTEX_STECH_APP_TOKEN", "token-from-channel")
    monkeypatch.delenv("VTEX_APP_KEY", raising=False)
    monkeypatch.delenv("VTEX_APP_TOKEN", raising=False)

    settings = Settings(_env_file=None)

    assert settings.vtex_app_key == "key-from-channel"
    assert settings.vtex_app_token == "token-from-channel"
    assert settings.stech_image_root == r"C:\STECH_IMAGENES"
    assert settings.vtex_account_name == "ststore227"
    assert settings.vtex_image_public_base == "https://mcp.artos.pe/vtex-images"


def test_vtex_image_signing_secret_is_automatic_and_stable_per_settings_instance(monkeypatch):
    monkeypatch.delenv("VTEX_IMAGE_SIGNING_SECRET", raising=False)
    settings = Settings(_env_file=None)

    first = settings.vtex_image_signing_secret_value()
    second = settings.vtex_image_signing_secret_value()

    assert first == second
    assert len(first) >= 32


def test_explicit_vtex_image_signing_secret_wins(monkeypatch):
    monkeypatch.setenv("VTEX_IMAGE_SIGNING_SECRET", "explicit-secret-value-that-is-long-enough")
    settings = Settings(_env_file=None)

    assert settings.vtex_image_signing_secret_value() == "explicit-secret-value-that-is-long-enough"



def test_falabella_image_secret_persists_across_settings_instances(tmp_path, monkeypatch):
    monkeypatch.delenv("FALABELLA_IMAGE_SIGNING_SECRET", raising=False)
    channel_root = tmp_path / "channels"

    first_settings = Settings(
        _env_file=None,
        stech_channel_image_root=str(channel_root),
    )
    first = first_settings.falabella_image_signing_secret_value()

    second_settings = Settings(
        _env_file=None,
        stech_channel_image_root=str(channel_root),
    )
    second = second_settings.falabella_image_signing_secret_value()

    assert first == second
    assert len(first) >= 32
    assert (channel_root / ".falabella-image-signing-secret").is_file()


def test_explicit_falabella_image_signing_secret_wins(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "FALABELLA_IMAGE_SIGNING_SECRET",
        "explicit-falabella-secret-value",
    )
    settings = Settings(
        _env_file=None,
        stech_channel_image_root=str(tmp_path / "channels"),
    )

    assert settings.falabella_image_signing_secret_value() == "explicit-falabella-secret-value"
    assert settings.falabella_image_public_base == "https://mcp.artos.pe/falabella-images"
    assert settings.falabella_image_url_ttl_seconds == 172800
    assert settings.falabella_image_canvas_px == 1500
    assert settings.falabella_image_max_bytes == 150 * 1024
