# Nightly backup of the IssueTracker database (registered as a scheduled task by install.ps1).
# Keeps the last $KeepDays days of .bak files in $Dir.
param(
    [string]$Dir = "C:\SQLBackups\IssueTracker",
    [int]$KeepDays = 14
)
New-Item -ItemType Directory -Force $Dir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$file = Join-Path $Dir "IssueTracker_$stamp.bak"
sqlcmd -S localhost -E -Q "BACKUP DATABASE IssueTracker TO DISK = N'$file' WITH INIT, CHECKSUM"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Backup failed."
    exit 1
}
sqlcmd -S localhost -E -Q "RESTORE VERIFYONLY FROM DISK = N'$file'"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Backup verification failed."
    exit 1
}
Get-ChildItem $Dir -Filter *.bak |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$KeepDays) } |
    Remove-Item -Force
Write-Host "Backup OK: $file"
