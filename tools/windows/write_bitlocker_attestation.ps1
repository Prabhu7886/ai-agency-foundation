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
$expectedFirewallRuleNames = @(
    "AI_Agency_Block_Ollama_Server_Outbound",
    "AI_Agency_Block_Ollama_Desktop_Outbound"
)
$firewallResults = @($expectedFirewallRuleNames | ForEach-Object {
    $ruleName = $_
    $rule = Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue
    $filter = if ($rule) { $rule | Get-NetFirewallApplicationFilter } else { $null }
    $ruleVerified = [bool](
        $rule -and
        [string]$rule.Enabled -eq "True" -and
        [string]$rule.Direction -eq "Outbound" -and
        [string]$rule.Action -eq "Block" -and
        $filter -and
        [string]$filter.Program -notin @("", "Any") -and
        (Test-Path -LiteralPath ([string]$filter.Program) -PathType Leaf)
    )
    [ordered]@{
        name = $ruleName
        program = if ($filter) { [string]$filter.Program } else { "Missing" }
        verified = $ruleVerified
        enabled = if ($rule) { [string]$rule.Enabled } else { "Missing" }
        action = if ($rule) { [string]$rule.Action } else { "Missing" }
    }
})
$firewallVerified = $firewallResults.Count -eq $expectedFirewallRuleNames.Count -and @($firewallResults | Where-Object { -not $_.verified }).Count -eq 0
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
    ollama_firewall = [ordered]@{
        verified = $firewallVerified
        mode = if ($firewallVerified) { "protected" } else { "maintenance-or-unconfigured" }
        rules = $firewallResults
    }
}
$report | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $temporary -Encoding UTF8
Move-Item -LiteralPath $temporary -Destination $destination -Force
if (-not $verified) {
    exit 2
}
