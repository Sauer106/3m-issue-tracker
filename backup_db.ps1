# Nightly backup of the IssueTracker database (registered as a scheduled task by install.ps1).
# Keeps the last $KeepDays days of .bak files locally in $Dir.
#
# Off-site copy: pass -OffsiteDir "\\server\share\IssueTracker" to also copy each
# verified backup to a network share, so a dead local disk doesn't lose everything.
# The task runs as SYSTEM, so the SYSTEM/computer account (DOMAIN\KOP-3MERDP01$)
# must have write access to that share. Leave -OffsiteDir empty to skip.
param(
    [string]$Dir = "C:\SQLBackups\IssueTracker",
    [string]$OffsiteDir = "",
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

# Copy the verified backup off-site, and prune the share on the same retention.
if ($OffsiteDir) {
    try {
        New-Item -ItemType Directory -Force $OffsiteDir -ErrorAction Stop | Out-Null
        Copy-Item $file (Join-Path $OffsiteDir (Split-Path $file -Leaf)) -Force -ErrorAction Stop
        Get-ChildItem $OffsiteDir -Filter *.bak |
            Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$KeepDays) } |
            Remove-Item -Force -ErrorAction SilentlyContinue
        Write-Host "Off-site copy OK: $OffsiteDir"
    } catch {
        # Don't fail the whole job if the share is briefly unreachable; the local
        # backup already succeeded. Surface it for the task-history/Last Result.
        Write-Error "Off-site copy failed: $_"
    }
}

Get-ChildItem $Dir -Filter *.bak |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$KeepDays) } |
    Remove-Item -Force
Write-Host "Backup OK: $file"
