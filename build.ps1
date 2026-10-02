param([string]$TesseractHome = "")

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
if ($TesseractHome) { $env:TESSERACT_HOME = $TesseractHome }
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Create .venv and install requirements-build.txt before building."
}
& $python -m PyInstaller --noconfirm document-register.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }
$appName = & $python -c "from src.config import APP_NAME; print(APP_NAME)"
Write-Output "Built: $PSScriptRoot\dist\$appName\$appName.exe"
