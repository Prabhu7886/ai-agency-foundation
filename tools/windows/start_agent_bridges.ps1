param(
    [string]$CommercePythonPath = "C:\Users\saifi\.codex\worktrees\1d15\AI Agency Foundation\.venv\Scripts\python.exe",
    [string]$CareerPythonPath = "C:\AI_AGENCY\.venv\Scripts\python.exe",
    [string]$CommerceRoot = "C:\Users\saifi\.codex\worktrees\1d15\AI Agency Foundation",
    [string]$CareerRoot = "C:\Users\saifi\.codex\worktrees\dcb8\AI Agency Foundation"
)

$ErrorActionPreference = "Stop"

$bridges = @(
    @{ Name = "commerce"; Root = $CommerceRoot; Python = $CommercePythonPath; Port = 8511 },
    @{ Name = "career"; Root = $CareerRoot; Python = $CareerPythonPath; Port = 8512 }
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
    Start-Process -FilePath $python -ArgumentList @(
        "-m", "tools.agent_bridge_server",
        "--agent", $bridge.Name,
        "--port", [string]$bridge.Port
    ) -WorkingDirectory $root -WindowStyle Hidden
    Write-Output "Started $($bridge.Name) bridge on 127.0.0.1:$($bridge.Port)"
}
