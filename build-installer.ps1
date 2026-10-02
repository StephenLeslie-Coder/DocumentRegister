param([string]$CompilerPath = "")

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { throw "The development Python environment is missing." }
$metadata = & $python -c "from src.config import APP_NAME, APP_VERSION; print(APP_NAME); print(APP_VERSION)"
if ($LASTEXITCODE -ne 0 -or $metadata.Count -ne 2) { throw "Could not read application metadata." }
$env:DOCUMENT_REGISTER_NAME = $metadata[0]
$env:DOCUMENT_REGISTER_VERSION = $metadata[1]
$portable = Join-Path $PSScriptRoot "dist\$($metadata[0])\$($metadata[0]).exe"
if (-not (Test-Path -LiteralPath $portable)) { throw "Build the portable application with build.ps1 first." }

if (-not $CompilerPath) {
    $candidatePaths = @(
        (Join-Path $PSScriptRoot ".tools\Inno\ISCC.exe"),
        (Join-Path $PSScriptRoot ".tools\Inno Setup 6\ISCC.exe"),
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe"
    )
    foreach ($candidate in $candidatePaths) {
        if (Test-Path -LiteralPath $candidate) { $CompilerPath = $candidate; break }
    }
}
if (-not $CompilerPath) {
    $command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($command) { $CompilerPath = $command.Source }
}
if (-not $CompilerPath -or -not (Test-Path -LiteralPath $CompilerPath)) {
    throw "Inno Setup 6 compiler (ISCC.exe) was not found. Install Inno Setup or pass -CompilerPath."
}
& $CompilerPath /Q installer.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup build failed." }
Write-Output "Built: $PSScriptRoot\dist\installer\DocumentRegisterSetup.exe"
