param(
    [string]$AegisRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$AegisPythonPath = "C:\AI_AGENCY\.venv\Scripts\python.exe",
    [string]$CommerceRoot = "C:\Users\saifi\.codex\worktrees\1d15\AI Agency Foundation",
    [string]$CareerRoot = "C:\Users\saifi\.codex\worktrees\dcb8\AI Agency Foundation",
    [string]$CareerPythonPath = "C:\AI_AGENCY\.venv\Scripts\python.exe",
    [string]$CareerSpeechModelPath = "C:\AI_AGENCY\models\faster-whisper-small.en"
)

$ErrorActionPreference = "Stop"

function Assert-Healthy {
    param([string]$Name, [string]$Url)

    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                Write-Output "$Name is healthy: $Url"
                return
            }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    throw "$Name did not become healthy: $Url"
}

$aegisLauncher = Join-Path $AegisRoot "tools\windows\start_aegis_stack.ps1"
& $aegisLauncher -AegisPythonPath $AegisPythonPath

$commerceLauncher = Join-Path $CommerceRoot "tools\windows\aegis_dashboard.ps1"
if (-not (Test-Path -LiteralPath $commerceLauncher -PathType Leaf)) {
    throw "Commerce dashboard launcher is missing: $commerceLauncher"
}
& $commerceLauncher -Action Start

$careerPython = (Resolve-Path -LiteralPath $CareerPythonPath).Path
$careerApp = Join-Path $CareerRoot "dashboard\app.py"
if (-not (Test-Path -LiteralPath $careerApp -PathType Leaf)) {
    throw "Career Studio dashboard is missing: $careerApp"
}
$careerListener = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8502 -State Listen -ErrorAction SilentlyContinue
if (-not $careerListener) {
    # The Commerce launcher intentionally sets AI_AGENCY_HOME for its own
    # encrypted runtime. Override that inherited value before starting Career
    # Studio so the independent agents never share databases or private files.
    $previousAgencyHome = [Environment]::GetEnvironmentVariable("AI_AGENCY_HOME", "Process")
    $previousSpeechModel = [Environment]::GetEnvironmentVariable("CAREER_SPEECH_MODEL_PATH", "Process")
    try {
        $env:AI_AGENCY_HOME = Join-Path $CareerRoot "runtime\aegis-career-dashboard"
        $env:CAREER_SPEECH_MODEL_PATH = $CareerSpeechModelPath
        Start-Process -FilePath $careerPython -ArgumentList @(
            "-m", "streamlit", "run", "dashboard\app.py",
            "--global.developmentMode", "false",
            "--server.address", "127.0.0.1",
            "--server.port", "8502",
            "--server.headless", "true",
            "--browser.gatherUsageStats", "false"
        ) -WorkingDirectory $CareerRoot -WindowStyle Hidden
    } finally {
        [Environment]::SetEnvironmentVariable("AI_AGENCY_HOME", $previousAgencyHome, "Process")
        [Environment]::SetEnvironmentVariable("CAREER_SPEECH_MODEL_PATH", $previousSpeechModel, "Process")
    }
}

Assert-Healthy "Aegis" "http://127.0.0.1:8000/api/health"
Assert-Healthy "Commerce Agent" "http://127.0.0.1:8501/_stcore/health"
Assert-Healthy "Career Studio" "http://127.0.0.1:8502/_stcore/health"

Write-Output "All dashboards are ready. Open the Desktop shortcuts to use them."
