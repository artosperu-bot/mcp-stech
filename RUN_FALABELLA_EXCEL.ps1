$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$InputDir = Join-Path $Root "EXCEL\FALABELLA\ENTRADA"
$OutputDir = Join-Path $Root "EXCEL\FALABELLA\SALIDA"
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Script = Join-Path $Root "scripts\falabella_fill_excel_images.py"

New-Item -ItemType Directory -Force -Path $InputDir | Out-Null
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

if (-not (Test-Path $Python)) {
    throw "No se encontró el entorno Python: $Python"
}

Write-Host ""
Write-Host "STECH - FALABELLA EXCEL IMAGES"
Write-Host "Entrada: $InputDir"
Write-Host "Salida : $OutputDir"
Write-Host ""

& $Python $Script @args
exit $LASTEXITCODE
