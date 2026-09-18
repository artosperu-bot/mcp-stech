from pathlib import Path

from stech_mcp.config import Settings


def test_research_search_config_is_loaded_from_dotenv(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "STECH_BRAVE_SEARCH_API_KEY=test-brave-key\n"
        "STECH_SEARCH_COUNTRY=PE\n"
        "STECH_SEARCH_LANGUAGE=es\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("STECH_BRAVE_SEARCH_API_KEY", raising=False)
    monkeypatch.delenv("STECH_SEARCH_COUNTRY", raising=False)
    monkeypatch.delenv("STECH_SEARCH_LANGUAGE", raising=False)

    settings = Settings(_env_file=env_file)

    assert settings.stech_brave_search_api_key == "test-brave-key"
    assert settings.stech_search_country == "PE"
    assert settings.stech_search_language == "es"


def test_worker_uses_settings_loaded_research_configuration():
    source = Path("src/stech_mcp/worker.py").read_text(encoding="utf-8")

    assert "api_key=settings.stech_brave_search_api_key" in source
    assert "country=settings.stech_search_country" in source
    assert "search_lang=settings.stech_search_language" in source
