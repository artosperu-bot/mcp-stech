$ErrorActionPreference = "Stop"

$ServiceName = "STECHEnrichmentWorker"
$PythonExe = if ($env:STECH_PYTHON) { $env:STECH_PYTHON } else { "python" }

$existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue

if ($null -eq $existing) {
    Write-Host "Installing $ServiceName..."
    & $PythonExe -m stech_mcp.worker_windows_service install --startup auto
    if ($LASTEXITCODE -ne 0) { throw "Failed to install $ServiceName" }
} else {
    Write-Host "$ServiceName already exists; updating service definition..."
    & $PythonExe -m stech_mcp.worker_windows_service update --startup auto
    if ($LASTEXITCODE -ne 0) { throw "Failed to update $ServiceName" }
}

$service = Get-Service -Name $ServiceName -ErrorAction Stop
if ($service.Status -ne "Running") {
    & $PythonExe -m stech_mcp.worker_windows_service start
    if ($LASTEXITCODE -ne 0) { throw "Failed to start $ServiceName" }
}

Write-Host "$ServiceName is installed and running."
