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
