$ErrorActionPreference = "Stop"

$ServiceName = "STECHEnrichmentWorker"
$PythonExe = if ($env:STECH_PYTHON) { $env:STECH_PYTHON } else { "python" }

$service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($null -eq $service) {
    Write-Host "$ServiceName is not installed. Nothing to remove."
    exit 0
}

if ($service.Status -ne "Stopped") {
    & $PythonExe -m stech_mcp.worker_windows_service stop
    if ($LASTEXITCODE -ne 0) { throw "Failed to stop $ServiceName" }
}

& $PythonExe -m stech_mcp.worker_windows_service remove
if ($LASTEXITCODE -ne 0) { throw "Failed to remove $ServiceName" }

Write-Host "$ServiceName removed."
