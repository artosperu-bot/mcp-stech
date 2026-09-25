param(
    [int]$IntervalMinutes = 240,
    [int]$Limit = 2000,
    [string]$Distributor = ""
)

$ErrorActionPreference = "Stop"
$TaskName = "STECH Taxonomy Gap Scan"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Runner = Join-Path $RepoRoot "deploy\windows\RUN_TAXONOMY_SCAN.ps1"

if ($IntervalMinutes -lt 30) { throw "IntervalMinutes must be at least 30." }
if (-not (Test-Path $Runner)) { throw "Runner not found: $Runner" }

$arguments = '-NoProfile -ExecutionPolicy Bypass -File "{0}" -Limit {1}' -f $Runner, $Limit
if ($Distributor.Trim()) {
    $arguments += (' -Distributor "{0}"' -f $Distributor.Trim())
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments -WorkingDirectory $RepoRoot
$logonTrigger = New-ScheduledTaskTrigger -AtLogOn
$repeatTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($logonTrigger, $repeatTrigger) -Settings $settings -Principal $principal -Description "Detects products missing STECH category/subcategory and queues them for review. Never auto-applies taxonomy." -Force | Out-Null

Start-ScheduledTask -TaskName $TaskName
Write-Host "$TaskName installed and started."
Write-Host "Interval: every $IntervalMinutes minutes + at logon."
Write-Host "Log: $RepoRoot\logs\taxonomy-scan.log"
