param(
  [Parameter(Mandatory=$true)][string]$CustomerId,
  [ValidateRange(1,3650)][int]$Days=30
)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
$root=Get-ProjectRoot
Import-DotEnv (Join-Path $root 'backend\.env')
& (Join-Path $root '.venv\Scripts\python.exe') (Join-Path $root 'backend\manage.py') evaluate_ml $CustomerId --days $Days
