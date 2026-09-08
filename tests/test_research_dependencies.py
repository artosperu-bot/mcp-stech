from pathlib import Path


def test_research_dependencies_and_env_are_declared_without_secret_value():
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    env = Path(".env.example").read_text(encoding="utf-8")

    assert '"httpx>=0.28,<1"' in pyproject
    assert '"pypdf>=5,<7"' in pyproject
    assert "STECH_BRAVE_SEARCH_API_KEY=" in env
    assert "STECH_SEARCH_COUNTRY=PE" in env
    assert "STECH_SEARCH_LANGUAGE=es" in env
