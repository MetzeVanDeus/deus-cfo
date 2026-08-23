[CmdletBinding()]
param(
  [string]$Python = "python",
  [string]$Npm = "npm"
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Frontend = Join-Path $Root "frontend"
$Dist = Join-Path $Root "dist"
$ArtifactDir = Join-Path $Dist "DeusCFO"
$Stage = Join-Path ([System.IO.Path]::GetTempPath()) "deuscfo-build-$PID"
$PyInstallerVersion = "6.11.1"

function Assert-NativeSuccess([string]$Step) {
  if ($LASTEXITCODE -ne 0) { throw "$Step failed with exit code $LASTEXITCODE" }
}

Push-Location $Frontend
& $Npm ci
Assert-NativeSuccess "npm ci"
& $Npm run build
Assert-NativeSuccess "frontend build"
Pop-Location

if (Test-Path $ArtifactDir) { Remove-Item -Recurse -Force $ArtifactDir }
New-Item -ItemType Directory -Force $Stage | Out-Null
Copy-Item (Join-Path $Root "deuscfo.py") (Join-Path $Stage "deuscfo.py")
try {
  & $Python -m pip install -r (Join-Path $Root "backend/requirements.txt") "pyinstaller==$PyInstallerVersion"
  Assert-NativeSuccess "PyInstaller install"
  & $Python -m PyInstaller --noconfirm --clean --onedir --name DeusCFO `
    --distpath $Dist --workpath (Join-Path $Stage "work") --specpath $Stage `
    --paths (Join-Path $Root "backend") `
    --collect-all uvicorn `
    --hidden-import main --hidden-import collector `
    --add-data "$(Join-Path $Frontend 'dist');frontend/dist" `
    --add-data "$(Join-Path $Root 'backend/div_card_recipes.json');." `
    --add-data "$(Join-Path $Root 'backend/transformations.experimental.json');." `
    (Join-Path $Stage "deuscfo.py")
  Assert-NativeSuccess "PyInstaller build"
} finally {
  Remove-Item -Recurse -Force $Stage -ErrorAction SilentlyContinue
}

$Artifact = Join-Path $ArtifactDir "DeusCFO.exe"
if (-not (Test-Path $Artifact)) { throw "PyInstaller did not produce $Artifact" }
$Hash = (& $Python -c "import hashlib,sys; print(hashlib.sha256(open(sys.argv[1], 'rb').read()).hexdigest().upper())" $Artifact).Trim()
"$Hash  DeusCFO.exe" | Set-Content -Encoding ascii (Join-Path $ArtifactDir "SHA256SUMS.txt")
Write-Host "Built $Artifact"
Write-Host "SHA-256 $Hash"
