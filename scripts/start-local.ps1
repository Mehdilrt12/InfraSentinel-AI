$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
$root = Get-ProjectRoot
Set-Location $root
if (-not (Test-Path '.venv\Scripts\python.exe')) { throw 'Exécutez scripts/setup.ps1.' }
Import-DotEnv 'backend\.env'
if (-not $env:DATABASE_ENGINE) { $env:DATABASE_ENGINE = 'sqlite' }
if ($env:DATABASE_ENGINE -eq 'sqlite' -and -not $env:CHANNEL_LAYER) { $env:CHANNEL_LAYER = 'memory' }
$occupied = @(5173, 8000 | Where-Object { Get-NetTCPConnection -LocalPort $_ -State Listen -ErrorAction SilentlyContinue })
if ($occupied.Count -gt 0) { throw "Port(s) déjà utilisé(s) : $($occupied -join ', '). Exécutez scripts/stop-local.ps1." }
$runtime = Join-Path $root 'runtime'
New-Item -ItemType Directory -Path $runtime -Force | Out-Null
& '.\.venv\Scripts\python.exe' backend\manage.py migrate --noinput
$processes = @()
$python = Join-Path $root '.venv\Scripts\python.exe'
$api = Start-Process -FilePath $python -ArgumentList '-m','daphne','-b','127.0.0.1','-p','8000','config.asgi:application' -WorkingDirectory (Join-Path $root 'backend') -WindowStyle Hidden -PassThru
$processes += @{ name='api'; id=$api.Id }
$node = (Get-Command node.exe -ErrorAction Stop).Source
$vite = Join-Path $root 'frontend\node_modules\vite\bin\vite.js'
$frontend = Start-Process -FilePath $node -ArgumentList $vite,'--host','127.0.0.1' -WorkingDirectory (Join-Path $root 'frontend') -WindowStyle Hidden -PassThru
$processes += @{ name='frontend'; id=$frontend.Id }
$redisReady = Test-NetConnection -ComputerName '127.0.0.1' -Port 6379 -InformationLevel Quiet -WarningAction SilentlyContinue
if ($redisReady) {
  $worker = Start-Process -FilePath $python -ArgumentList '-m','celery','-A','config','worker','-l','INFO','--pool=solo' -WorkingDirectory (Join-Path $root 'backend') -WindowStyle Hidden -PassThru
  $beat = Start-Process -FilePath $python -ArgumentList '-m','celery','-A','config','beat','-l','INFO' -WorkingDirectory (Join-Path $root 'backend') -WindowStyle Hidden -PassThru
  $processes += @{ name='worker'; id=$worker.Id }, @{ name='beat'; id=$beat.Id }
} else { Write-Warning 'Redis indisponible : API/dashboard démarrés, workers Celery non lancés.' }
$processes | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtime 'local-processes.json') -Encoding utf8
Start-Sleep -Seconds 2
foreach ($item in $processes) {
  if (-not (Get-Process -Id $item.id -ErrorAction SilentlyContinue)) { throw "Le service $($item.name) n'a pas démarré." }
}
Write-Host 'API       : http://127.0.0.1:8000/api/health/'
Write-Host 'Dashboard : http://127.0.0.1:5173/'
