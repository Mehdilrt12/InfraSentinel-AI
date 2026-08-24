$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
$root = Get-ProjectRoot
Set-Location $root
if (-not (Test-Path '.venv\Scripts\python.exe')) { python -m venv .venv }
& '.\.venv\Scripts\python.exe' -m pip install --upgrade pip
& '.\.venv\Scripts\python.exe' -m pip install -r backend\requirements-dev.txt -r agent\requirements.txt
Push-Location frontend
npm install
Pop-Location
if (-not (Test-Path 'backend\.env')) {
  throw 'Configuration absente : copiez backend/.env.example vers backend/.env et renseignez les valeurs.'
}
Import-DotEnv 'backend\.env'
& '.\.venv\Scripts\python.exe' backend\manage.py migrate
Write-Host 'InfraSentinel AI prêt.' -ForegroundColor Green
