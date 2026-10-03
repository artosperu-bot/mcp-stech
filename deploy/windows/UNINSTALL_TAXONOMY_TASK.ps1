$ErrorActionPreference = "Stop"
$TaskName = "STECH Taxonomy Gap Scan"

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -ne $task) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "$TaskName removed."
}
else {
    Write-Host "$TaskName is not installed."
}
