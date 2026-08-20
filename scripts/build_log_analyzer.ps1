# Build a double-clickable Windows exe for the session log viewer.
# Uses python.org Python (not the Microsoft Store runtime), which PyInstaller
# can bundle. Recreate the build venv if missing:
#   py -3.14 -m venv build\logviewer-venv
#   .\build\logviewer-venv\Scripts\python.exe -m pip install PyQt6 pyinstaller pyyaml

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$py = Join-Path $root "build\logviewer-venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    throw "Missing $py. Create it with python.org Python 3.14 as described in this script."
}

& $py -m PyInstaller --noconfirm --clean --distpath dist --workpath build\pyinstaller `
    packaging\log_analyzer.spec

$exe = Join-Path $root "dist\SpineCoolingLogViewer.exe"
if (-not (Test-Path $exe)) {
    throw "Build finished but $exe was not created."
}
Write-Host "Built $exe"
