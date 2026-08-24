param([Parameter(Mandatory=$true)][string]$SqlitePath)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
$root=Get-ProjectRoot
$python=Join-Path $root '.venv\Scripts\python.exe'
if(-not (Test-Path -LiteralPath $SqlitePath)){throw 'Base SQLite introuvable.'}
$absolute=(Resolve-Path -LiteralPath $SqlitePath).Path
$dump=Join-Path $env:TEMP ("infrasentinel-data-{0}.json" -f [Guid]::NewGuid())
$env:DATABASE_ENGINE='sqlite';$env:SQLITE_DB_PATH=$absolute
& $python (Join-Path $root 'backend\manage.py') dumpdata --natural-foreign --natural-primary --exclude contenttypes --exclude auth.permission --indent 2 --output $dump
if(-not $env:POSTGRES_DB -or -not $env:POSTGRES_USER -or -not $env:POSTGRES_HOST){throw 'Variables PostgreSQL incomplètes; le dump temporaire est conservé.'}
$env:DATABASE_ENGINE='postgresql'
& $python (Join-Path $root 'backend\manage.py') migrate --noinput
& $python (Join-Path $root 'backend\manage.py') loaddata $dump
Write-Host "Import terminé. SQLite conservé : $absolute"
Write-Host "Dump temporaire : $dump"

