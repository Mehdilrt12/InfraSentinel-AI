param(
  [ValidateSet('postgresql', 'sqlite')]
  [string]$Database = 'postgresql',
  [switch]$RedisIntegration
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
$env:COVERAGE_FILE=(Join-Path $root '.coverage')
if ($RedisIntegration) { $env:INFRASENTINEL_RUN_REDIS_INTEGRATION='1' }
& '.\.venv\Scripts\python.exe' backend\manage.py check
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& '.\.venv\Scripts\python.exe' backend\manage.py makemigrations --check --dry-run
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Push-Location backend
& '..\.venv\Scripts\coverage.exe' run --rcfile '.coveragerc' manage.py test
$backendExit=$LASTEXITCODE
Pop-Location
if ($backendExit -ne 0) { exit $backendExit }
& '.\.venv\Scripts\coverage.exe' report --rcfile 'backend\.coveragerc'
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$env:PYTHONPATH=(Join-Path $root 'agent')
& '.\.venv\Scripts\python.exe' -m unittest discover agent\tests
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Push-Location frontend
npm run test
if ($LASTEXITCODE -ne 0) { Pop-Location; exit $LASTEXITCODE }
npm run lint
if ($LASTEXITCODE -ne 0) { Pop-Location; exit $LASTEXITCODE }
npm run build
if ($LASTEXITCODE -ne 0) { Pop-Location; exit $LASTEXITCODE }
npm audit
$frontendExit=$LASTEXITCODE
Pop-Location
exit $frontendExit
