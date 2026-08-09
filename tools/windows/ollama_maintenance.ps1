param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Enter", "Exit", "Status")]
    [string]$Mode
)

$ErrorActionPreference = "Stop"
$ruleNames = @(
    "AI_Agency_Block_Ollama_Server_Outbound",
    "AI_Agency_Block_Ollama_Desktop_Outbound"
)
$securityRoot = Join-Path $env:ProgramData "AI_Agency\Security"
$auditLog = Join-Path $securityRoot "ollama_maintenance.jsonl"
$attestationScript = Join-Path $securityRoot "write_bitlocker_attestation.ps1"

function Write-MaintenanceEvent {
    param([string]$EventName, [string]$Result)
    [ordered]@{
        timestamp = [DateTime]::UtcNow.ToString("o")
        event = $EventName
        result = $Result
        user = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    } | ConvertTo-Json -Compress | Add-Content -LiteralPath $auditLog -Encoding UTF8
}

function Get-ProtectedAgencyProcesses {
    @(Get-CimInstance Win32_Process | Where-Object {
        $command = [string]$_.CommandLine
        $command -match "C:\\AI_AGENCY\\.venv\\Scripts\\python.exe" -or
        $command -match "run_agency\.py" -or
        $command -match "dashboard\\app\.py"
    } | Select-Object ProcessId, Name, CommandLine)
}

if ($Mode -eq "Enter") {
    $protectedProcesses = Get-ProtectedAgencyProcesses
    if ($protectedProcesses.Count -gt 0) {
        Write-MaintenanceEvent "enter-denied" "Protected Aegis or dashboard processes are still running"
        throw "Stop Aegis and the dashboard before entering Ollama maintenance mode."
    }
    Set-NetFirewallRule -Name $ruleNames -Enabled False
    Write-MaintenanceEvent "enter" "Ollama outbound block temporarily disabled"
    & $attestationScript
    Write-Output "MAINTENANCE MODE: Ollama internet access is temporarily allowed. Do not process sensitive data."
    return
}

if ($Mode -eq "Exit") {
    Set-NetFirewallRule -Name $ruleNames -Enabled True
    Start-Sleep -Seconds 2
    Write-MaintenanceEvent "exit" "Ollama outbound block restored"
    & $attestationScript
    Write-Output "PROTECTED MODE: Ollama outbound internet access is blocked."
    return
}

$rules = @(Get-NetFirewallRule -Name $ruleNames)
$filters = @($rules | Get-NetFirewallApplicationFilter)
$connections = @(Get-NetTCPConnection -State Established -ErrorAction SilentlyContinue | Where-Object {
    $process = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue
    $process -and $process.ProcessName -like "ollama*" -and $_.RemoteAddress -notin @("127.0.0.1", "::1")
} | Select-Object OwningProcess, LocalAddress, LocalPort, RemoteAddress, RemotePort)
[ordered]@{
    mode = if (@($rules | Where-Object Enabled -ne "True").Count -eq 0) { "protected" } else { "maintenance" }
    rules = @($rules | Select-Object Name, Enabled, Direction, Action)
    programs = @($filters | Select-Object Program)
    external_connections = $connections
} | ConvertTo-Json -Depth 5
