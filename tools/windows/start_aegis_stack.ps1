param(
    [string]$AegisRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$AegisPythonPath = "C:\AI_AGENCY\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path -LiteralPath $AegisRoot).Path
$python = (Resolve-Path -LiteralPath $AegisPythonPath).Path
$bridgeScript = Join-Path $root "tools\windows\start_agent_bridges.ps1"

if (-not (Test-Path -LiteralPath $bridgeScript -PathType Leaf)) {
    throw "Agent Bridge startup script is missing: $bridgeScript"
}

& $bridgeScript

$existing = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    Write-Output "Aegis is already listening on http://127.0.0.1:8000"
    exit 0
}

$launcher = Join-Path $root "tools\desktop_runtime_launcher.py"
if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
    throw "Aegis desktop launcher is missing: $launcher"
}

Start-Process -FilePath $python -ArgumentList @($launcher) -WorkingDirectory $root -WindowStyle Hidden
Write-Output "Started Aegis and its supervised independent-agent bridges."
Write-Output "Ollama was not started automatically; controlled-maintenance policy remains unchanged."
