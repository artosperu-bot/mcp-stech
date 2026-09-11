from pathlib import Path


def test_worker_keeps_existing_mcp_entrypoint_and_adds_separate_command():
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    assert 'stech-mcp = "stech_mcp.server_authoritative:main"' in pyproject
    assert 'stech-mcp-check = "stech_mcp.check:main"' in pyproject
    assert 'stech-enrichment-worker = "stech_mcp.worker:main"' in pyproject
    assert "pywin32>=306" in pyproject
    assert "sys_platform == 'win32'" in pyproject


def test_worker_environment_contract_is_explicit_and_single_concurrency():
    env = Path(".env.example").read_text(encoding="utf-8")
    for line in (
        "STECH_WORKER_ENABLED=true",
        "STECH_WORKER_POLL_SECONDS=5",
        "STECH_WORKER_LEASE_SECONDS=300",
        "STECH_WORKER_MAX_ATTEMPTS=3",
        "STECH_WORKER_CONCURRENCY=1",
    ):
        assert line in env


def test_worker_has_reversible_windows_service_scripts():
    service = Path("src/stech_mcp/worker_windows_service.py").read_text(encoding="utf-8")
    install = Path("deploy/windows/INSTALL_ENRICHMENT_WORKER.ps1").read_text(encoding="utf-8")
    uninstall = Path("deploy/windows/UNINSTALL_ENRICHMENT_WORKER.ps1").read_text(encoding="utf-8")

    assert 'STECHEnrichmentWorker' in service
    assert 'win32serviceutil.ServiceFramework' in service
    assert 'STECHEnrichmentWorker' in install
    assert ' install --startup auto' in install
    assert ' update --startup auto' in install
    assert ' start' in install
    assert 'STECHEnrichmentWorker' in uninstall
    assert ' stop' in uninstall
    assert ' remove' in uninstall


def test_worker_deployment_does_not_install_or_replace_mcp_server_service():
    install = Path("deploy/windows/INSTALL_ENRICHMENT_WORKER.ps1").read_text(encoding="utf-8")
    assert "stech_mcp.worker_windows_service" in install
    assert "server_authoritative" not in install
    assert "stech-mcp" not in install.lower()
