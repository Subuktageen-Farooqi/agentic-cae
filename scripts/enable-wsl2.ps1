#Requires -RunAsAdministrator
# Run from an Administrator PowerShell. This script never restarts the PC.
$ErrorActionPreference = 'Stop'
$features = @('Microsoft-Windows-Subsystem-Linux', 'VirtualMachinePlatform')
$restartNeeded = $false
foreach ($feature in $features) {
    $state = Get-WindowsOptionalFeature -Online -FeatureName $feature
    if ($state.State -ne 'Enabled') {
        $result = Enable-WindowsOptionalFeature -Online -FeatureName $feature -All -NoRestart
        $restartNeeded = $restartNeeded -or $result.RestartNeeded
    }
}
if ($restartNeeded) {
    Write-Host 'Windows features enabled. Save your work and restart Windows manually, then run this script again.'
    exit 0
}
& wsl.exe --install --no-distribution --web-download
if ($LASTEXITCODE -ne 0) { throw 'WSL installation did not complete. Inspect the Windows message above and restart manually if requested.' }
& wsl.exe --update --web-download
if ($LASTEXITCODE -ne 0) { throw 'WSL update failed. Inspect the Windows message above; do not initialize Podman yet.' }
& wsl.exe --set-default-version 2
if ($LASTEXITCODE -ne 0) { throw 'WSL2 is not ready. Restart Windows if required and inspect wsl --status.' }
& wsl.exe --status
if ($LASTEXITCODE -ne 0) { throw 'WSL status failed; container verification remains blocked.' }
Write-Host 'WSL prerequisite configured. Return to the project for Podman machine/image verification.'
