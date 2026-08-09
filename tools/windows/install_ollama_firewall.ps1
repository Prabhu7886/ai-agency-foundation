$ErrorActionPreference = "Stop"
$ollamaRoot = Join-Path $env:LOCALAPPDATA "Programs\Ollama"
$rules = @(
    [ordered]@{
        name = "AI_Agency_Block_Ollama_Server_Outbound"
        display = "AI Agency - Block Ollama Server Outbound"
        program = Join-Path $ollamaRoot "ollama.exe"
    },
    [ordered]@{
        name = "AI_Agency_Block_Ollama_Desktop_Outbound"
        display = "AI Agency - Block Ollama Desktop Outbound"
        program = Join-Path $ollamaRoot "ollama app.exe"
    }
)

foreach ($definition in $rules) {
    if (-not (Test-Path -LiteralPath $definition.program -PathType Leaf)) {
        throw "Ollama executable not found: $($definition.program)"
    }
    Get-NetFirewallRule -Name $definition.name -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    New-NetFirewallRule `
        -Name $definition.name `
        -DisplayName $definition.display `
        -Description "Controlled-maintenance policy: block Ollama internet access during normal Aegis operation." `
        -Direction Outbound `
        -Action Block `
        -Program $definition.program `
        -Profile Any `
        -Enabled True | Out-Null
}

$securityRoot = Join-Path $env:ProgramData "AI_Agency\Security"
$attestationSource = Join-Path $PSScriptRoot "write_bitlocker_attestation.ps1"
$attestationTarget = Join-Path $securityRoot "write_bitlocker_attestation.ps1"
Copy-Item -LiteralPath $attestationSource -Destination $attestationTarget -Force
& $attestationTarget
Write-Output "Ollama controlled-maintenance firewall policy installed."
