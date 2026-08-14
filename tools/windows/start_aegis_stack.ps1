param(
    [string]$AegisRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$AegisPythonPath = "C:\AI_AGENCY\.venv\Scripts\python.exe",
    [int]$StartupTimeoutSeconds = 30
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path -LiteralPath $AegisRoot).Path
$python = (Resolve-Path -LiteralPath $AegisPythonPath).Path
$pythonwCandidate = Join-Path (Split-Path -Parent $python) "pythonw.exe"
$aegisPython = if (Test-Path -LiteralPath $pythonwCandidate -PathType Leaf) {
    (Resolve-Path -LiteralPath $pythonwCandidate).Path
} else {
    $python
}
$bridgeScript = Join-Path $root "tools\windows\start_agent_bridges.ps1"
$runtimeRoot = Join-Path $root "runtime\aegis-control\launcher"
$pidFile = Join-Path $runtimeRoot "aegis.pid"
$stdoutLog = Join-Path $runtimeRoot "aegis.stdout.log"
$stderrLog = Join-Path $runtimeRoot "aegis.stderr.log"
$healthUrl = "http://127.0.0.1:8000/api/health"

if (-not (Test-Path -LiteralPath $bridgeScript -PathType Leaf)) {
    throw "Agent Bridge startup script is missing: $bridgeScript"
}

& $bridgeScript

$existing = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    try {
        $health = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 3
        if ($health.status -eq "ok") {
            Write-Output "Aegis is already healthy on http://127.0.0.1:8000"
            exit 0
        }
    } catch {
        # The explicit error below identifies the unexpected port owner.
    }
    throw "Port 8000 is already owned by PID $($existing.OwningProcess), but Aegis health is unavailable."
}

$launcher = Join-Path $root "tools\desktop_runtime_launcher.py"
if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
    throw "Aegis desktop launcher is missing: $launcher"
}

New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
Remove-Item -LiteralPath $stdoutLog, $stderrLog -Force -ErrorAction SilentlyContinue

# Start-Process joins ArgumentList values into one command line. Quote the launcher
# because the project path contains spaces.
$process = Start-Process -FilePath $aegisPython -ArgumentList @("`"$launcher`"") `
    -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog -PassThru
Set-Content -LiteralPath $pidFile -Value $process.Id -Encoding ascii

$deadline = [DateTime]::UtcNow.AddSeconds($StartupTimeoutSeconds)
while ([DateTime]::UtcNow -lt $deadline) {
    $process.Refresh()
    if ($process.HasExited) {
        $details = if (Test-Path -LiteralPath $stderrLog) {
            (Get-Content -LiteralPath $stderrLog -Tail 30) -join [Environment]::NewLine
        } else {
            "No error log was created."
        }
        Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
        throw "Aegis exited during startup.$([Environment]::NewLine)$details"
    }
    try {
        $health = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 2
        if ($health.status -eq "ok") {
            Write-Output "Aegis is healthy (PID $($process.Id)): http://127.0.0.1:8000"
            Write-Output "Started Aegis and its supervised independent-agent bridges."
            Write-Output "Ollama was not started automatically; controlled-maintenance policy remains unchanged."
            exit 0
        }
    } catch {
        Start-Sleep -Milliseconds 500
    }
}

Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
throw "Aegis did not become healthy within $StartupTimeoutSeconds seconds. See $stderrLog"
