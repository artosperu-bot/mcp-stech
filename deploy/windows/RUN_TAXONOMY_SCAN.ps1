param(
    [int]$Limit = 5000,
    [string]$Distributor = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Script = Join-Path $RepoRoot "scripts\run_taxonomy_scan.py"
$LogDir = Join-Path $RepoRoot "logs"
$LogFile = Join-Path $LogDir "taxonomy-scan.log"

if (-not (Test-Path $Python)) { throw "Python virtual environment not found: $Python" }
if (-not (Test-Path $Script)) { throw "Taxonomy scan script not found: $Script" }

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
Push-Location $RepoRoot
try {
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "[$stamp] START taxonomy gap scan" | Out-File -FilePath $LogFile -Append -Encoding utf8

    $argsList = @($Script, "--limit", "$Limit")
    if ($Distributor.Trim()) {
        $argsList += @("--distributor", $Distributor.Trim())
    }

    & $Python @argsList 2>&1 | Tee-Object -FilePath $LogFile -Append
    $exitCode = $LASTEXITCODE

    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "[$stamp] END taxonomy gap scan exit=$exitCode" | Out-File -FilePath $LogFile -Append -Encoding utf8
    exit $exitCode
}
finally {
    Pop-Location
}
