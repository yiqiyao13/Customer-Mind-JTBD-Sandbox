# Build one-click launcher exe
# Usage: .\build_launcher.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "Installing PyInstaller..."
python -m pip install -q pyinstaller

$outName = "MindSim"
Write-Host "Building $outName.exe ..."

python -m PyInstaller --noconfirm --clean --onefile --console --name $outName --distpath . --workpath .\build_launcher --specpath .\build_launcher .\launcher.py

if ($LASTEXITCODE -ne 0) {
    Write-Host "Build failed" -ForegroundColor Red
    exit 1
}

Remove-Item -Recurse -Force .\build_launcher -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Done: $PSScriptRoot\$outName.exe" -ForegroundColor Green
Write-Host "Double-click the exe (keep it next to backend/frontend/data)."
