$ErrorActionPreference = "Stop"
$source = Join-Path $PSScriptRoot "write_bitlocker_attestation.ps1"
$securityRoot = Join-Path $env:ProgramData "AI_Agency\Security"
$installedScript = Join-Path $securityRoot "write_bitlocker_attestation.ps1"
$taskName = "AI Agency BitLocker Attestation"
$errorLog = Join-Path $securityRoot "installation_error.log"

New-Item -ItemType Directory -Path $securityRoot -Force | Out-Null
try {
    Copy-Item -LiteralPath $source -Destination $installedScript -Force
    & icacls.exe $securityRoot /inheritance:r /grant:r "SYSTEM:(OI)(CI)F" "BUILTIN\Administrators:(OI)(CI)F" "BUILTIN\Users:(OI)(CI)RX" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Could not secure the BitLocker attestation directory"
    }

    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy RemoteSigned -File `"$installedScript`""
    $triggers = @(
        New-ScheduledTaskTrigger -AtStartup
        New-ScheduledTaskTrigger -Daily -At "12:05 AM"
    )
    $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
        -StartWhenAvailable `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $triggers -Principal $principal -Settings $settings -Force | Out-Null
    Start-ScheduledTask -TaskName $taskName

    $attestation = Join-Path $securityRoot "bitlocker_attestation.json"
    for ($attempt = 0; $attempt -lt 20 -and -not (Test-Path -LiteralPath $attestation); $attempt++) {
        Start-Sleep -Milliseconds 500
    }
    if (-not (Test-Path -LiteralPath $attestation)) {
        throw "The BitLocker attestation task did not create its report"
    }
    Remove-Item -LiteralPath $errorLog -Force -ErrorAction SilentlyContinue
    Write-Output "BitLocker attestation installed and refreshed: $attestation"
} catch {
    ($_ | Out-String) | Set-Content -LiteralPath $errorLog -Encoding UTF8
    throw
}
