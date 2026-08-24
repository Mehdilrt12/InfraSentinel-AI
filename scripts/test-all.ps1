param(
  [ValidateSet('postgresql', 'sqlite')]
  [string]$Database = 'postgresql'
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
$root = Get-ProjectRoot
Set-Location $root
Import-DotEnv 'backend\.env'
$env:DATABASE_ENGINE=$Database
if ($Database -eq 'sqlite') { $env:SQLITE_DB_PATH=(Join-Path $env:TEMP 'infrasentinel-tests.sqlite3') }
$env:CHANNEL_LAYER='memory'
$env:CELERY_TASK_ALWAYS_EAGER='true'
& '.\.venv\Scripts\python.exe' backend\manage.py check
& '.\.venv\Scripts\python.exe' backend\manage.py makemigrations --check --dry-run
Push-Location backend
& '..\.venv\Scripts\coverage.exe' run manage.py test
Pop-Location
& '.\.venv\Scripts\coverage.exe' report
$env:PYTHONPATH=(Join-Path $root 'agent')
& '.\.venv\Scripts\python.exe' -m unittest discover agent\tests
Push-Location frontend
npm run test
npm run lint
npm run build
npm audit
Pop-Location
