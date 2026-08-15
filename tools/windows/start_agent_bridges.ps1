param(
    [string]$CommercePythonPath = "C:\Users\saifi\.codex\worktrees\1d15\AI Agency Foundation\.venv\Scripts\python.exe",
    [string]$CareerPythonPath = "C:\AI_AGENCY\.venv\Scripts\python.exe",
    [string]$CommerceRoot = "C:\Users\saifi\.codex\worktrees\1d15\AI Agency Foundation",
    [string]$CareerRoot = "C:\Users\saifi\.codex\worktrees\dcb8\AI Agency Foundation",
    [string]$CareerSpeechModelPath = "C:\AI_AGENCY\models\faster-whisper-small.en",
    [string]$SupervisorEnvironmentPath = "C:\AI_AGENCY\.env"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $SupervisorEnvironmentPath -PathType Leaf)) {
    throw "Aegis supervision environment is missing: $SupervisorEnvironmentPath"
}

$bridges = @(
    @{ Name = "commerce"; Root = $CommerceRoot; Python = $CommercePythonPath; Port = 8511; Runtime = "runtime\aegis-dashboard" },
    @{ Name = "career"; Root = $CareerRoot; Python = $CareerPythonPath; Port = 8512; Runtime = "runtime\aegis-career-dashboard" }
)

foreach ($bridge in $bridges) {
    $root = (Resolve-Path -LiteralPath $bridge.Root).Path
    $python = (Resolve-Path -LiteralPath $bridge.Python).Path
    $server = Join-Path $root "tools\agent_bridge_server.py"
    if (-not (Test-Path -LiteralPath $server -PathType Leaf)) {
        throw "Agent Bridge server is missing for $($bridge.Name): $server"
    }
    $existing = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort $bridge.Port -State Listen -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Output "$($bridge.Name) bridge is already listening on 127.0.0.1:$($bridge.Port)"
        continue
    }
    $previousAgencyHome = [Environment]::GetEnvironmentVariable("AI_AGENCY_HOME", "Process")
    $previousSpeechModel = [Environment]::GetEnvironmentVariable("CAREER_SPEECH_MODEL_PATH", "Process")
    $previousBridgeAuth = [Environment]::GetEnvironmentVariable("AEGIS_BRIDGE_AUTH_ENV_PATH", "Process")
    try {
        $env:AI_AGENCY_HOME = Join-Path $root $bridge.Runtime
        $env:AEGIS_BRIDGE_AUTH_ENV_PATH = $SupervisorEnvironmentPath
        if ($bridge.Name -eq "career") {
            $env:CAREER_SPEECH_MODEL_PATH = $CareerSpeechModelPath
        } else {
            [Environment]::SetEnvironmentVariable("CAREER_SPEECH_MODEL_PATH", $null, "Process")
        }
        Start-Process -FilePath $python -ArgumentList @(
            "-m", "tools.agent_bridge_server",
            "--agent", $bridge.Name,
            "--port", [string]$bridge.Port
        ) -WorkingDirectory $root -WindowStyle Hidden
    } finally {
        [Environment]::SetEnvironmentVariable("AI_AGENCY_HOME", $previousAgencyHome, "Process")
        [Environment]::SetEnvironmentVariable("CAREER_SPEECH_MODEL_PATH", $previousSpeechModel, "Process")
        [Environment]::SetEnvironmentVariable("AEGIS_BRIDGE_AUTH_ENV_PATH", $previousBridgeAuth, "Process")
    }
    Write-Output "Started $($bridge.Name) bridge on 127.0.0.1:$($bridge.Port)"
}
