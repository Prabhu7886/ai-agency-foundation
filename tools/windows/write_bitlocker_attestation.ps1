$ErrorActionPreference = "Stop"
$securityRoot = $PSScriptRoot
$destination = Join-Path $securityRoot "bitlocker_attestation.json"
$temporary = Join-Path $securityRoot "bitlocker_attestation.tmp"
$drive = "C:"
$volume = Get-BitLockerVolume -MountPoint $drive
$verified = (
    [string]$volume.VolumeStatus -eq "FullyEncrypted" -and
    [string]$volume.ProtectionStatus -eq "On" -and
    [double]$volume.EncryptionPercentage -ge 100
)
$report = [ordered]@{
    checked_at = [DateTime]::UtcNow.ToString("o")
    drive = $drive
    verified = $verified
    volume_status = [string]$volume.VolumeStatus
    protection_status = [string]$volume.ProtectionStatus
    percentage = [double]$volume.EncryptionPercentage
    encryption_method = [string]$volume.EncryptionMethod
    recovery_protector_present = [bool]($volume.KeyProtector | Where-Object KeyProtectorType -eq "RecoveryPassword")
    tpm_protector_present = [bool]($volume.KeyProtector | Where-Object KeyProtectorType -eq "Tpm")
}
$report | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $temporary -Encoding UTF8
Move-Item -LiteralPath $temporary -Destination $destination -Force
if (-not $verified) {
    exit 2
}
