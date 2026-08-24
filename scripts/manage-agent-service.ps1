param([ValidateSet('install','start','stop','restart','remove','status')][string]$Action='status')
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
$root=Get-ProjectRoot
$python=Join-Path $root '.venv\Scripts\python.exe'
$service=Join-Path $root 'agent\windows_service.py'
switch($Action){
  'install' { & $python $service --startup auto install }
  'start' { & $python $service start }
  'stop' { & $python $service stop }
  'restart' { & $python $service restart }
  'remove' { & $python $service remove }
  'status' { Get-Service -Name 'InfraSentinelAgent' -ErrorAction SilentlyContinue | Format-List Name,Status,StartType }
}

