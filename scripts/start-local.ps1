$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
$root = Get-ProjectRoot
Set-Location $root
if (-not (Test-Path '.venv\Scripts\python.exe')) { throw 'Exécutez scripts/setup.ps1.' }
Import-DotEnv 'backend\.env'
if (-not $env:DATABASE_ENGINE) { $env:DATABASE_ENGINE = 'sqlite' }
if ($env:DATABASE_ENGINE -eq 'sqlite' -and -not $env:CHANNEL_LAYER) { $env:CHANNEL_LAYER = 'memory' }
$apiBind = if ($env:API_BIND_ADDRESS) { $env:API_BIND_ADDRESS } else { '127.0.0.1' }
$frontendBind = if ($env:FRONTEND_BIND_ADDRESS) { $env:FRONTEND_BIND_ADDRESS } else { '127.0.0.1' }
$apiPort = if ($env:API_PORT) { [int]$env:API_PORT } else { 8000 }
$frontendPort = if ($env:FRONTEND_PORT) { [int]$env:FRONTEND_PORT } else { 5173 }
$occupied = @($frontendPort, $apiPort | Where-Object { Get-NetTCPConnection -LocalPort $_ -State Listen -ErrorAction SilentlyContinue })
if ($occupied.Count -gt 0) { throw "Port(s) déjà utilisé(s) : $($occupied -join ', '). Exécutez scripts/stop-local.ps1." }
$runtime = Join-Path $root 'runtime'
New-Item -ItemType Directory -Path $runtime -Force | Out-Null
& '.\.venv\Scripts\python.exe' backend\manage.py migrate --noinput
& '.\.venv\Scripts\python.exe' backend\manage.py collectstatic --noinput
$processes = @()
$python = Join-Path $root '.venv\Scripts\python.exe'
$api = Start-Process -FilePath $python -ArgumentList '-m','daphne','-b',$apiBind,'-p',$apiPort,'config.asgi:application' -WorkingDirectory (Join-Path $root 'backend') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtime 'api.stdout.log') -RedirectStandardError (Join-Path $runtime 'api.stderr.log') -PassThru
$processes += @{ name='api'; id=$api.Id }
$node = (Get-Command node.exe -ErrorAction Stop).Source
$vite = Join-Path $root 'frontend\node_modules\vite\bin\vite.js'
$frontend = Start-Process -FilePath $node -ArgumentList $vite,'--host',$frontendBind,'--port',$frontendPort -WorkingDirectory (Join-Path $root 'frontend') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtime 'frontend.stdout.log') -RedirectStandardError (Join-Path $runtime 'frontend.stderr.log') -PassThru
$processes += @{ name='frontend'; id=$frontend.Id }
$redisReady = Test-NetConnection -ComputerName '127.0.0.1' -Port 6379 -InformationLevel Quiet -WarningAction SilentlyContinue
if ($redisReady) {
  $worker = Start-Process -FilePath $python -ArgumentList '-m','celery','-A','config','worker','-l','INFO','--pool=solo','-Q','celery,hyperv' -WorkingDirectory (Join-Path $root 'backend') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtime 'worker.stdout.log') -RedirectStandardError (Join-Path $runtime 'worker.stderr.log') -PassThru
  $beat = Start-Process -FilePath $python -ArgumentList '-m','celery','-A','config','beat','-l','INFO' -WorkingDirectory (Join-Path $root 'backend') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtime 'beat.stdout.log') -RedirectStandardError (Join-Path $runtime 'beat.stderr.log') -PassThru
  $processes += @{ name='worker'; id=$worker.Id }, @{ name='beat'; id=$beat.Id }
} else { Write-Warning 'Redis indisponible : API/dashboard démarrés, workers Celery non lancés.' }
$processes | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtime 'local-processes.json') -Encoding utf8
try {
  $deadline = (Get-Date).AddSeconds(45)
  do {
    $apiReady = $false
    $frontendReady = $false
    try { $apiReady = (Invoke-RestMethod "http://127.0.0.1:$apiPort/api/health/" -TimeoutSec 2).status -eq 'ok' } catch {}
    try { $frontendReady = (Invoke-WebRequest "http://127.0.0.1:$frontendPort/" -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 } catch {}
    if ($apiReady -and $frontendReady) { break }
    foreach ($item in $processes) {
      if (-not (Get-Process -Id $item.id -ErrorAction SilentlyContinue)) { throw "Le service $($item.name) s'est arrêté pendant le démarrage. Consultez runtime/$($item.name).stderr.log." }
    }
    Start-Sleep -Seconds 1
  } while ((Get-Date) -lt $deadline)
  if (-not ($apiReady -and $frontendReady)) { throw 'Le délai de disponibilité API/frontend est dépassé. Consultez runtime/*.stderr.log.' }
} catch {
  foreach ($item in $processes) { Stop-ProcessTree -ProcessId $item.id }
  Remove-Item -LiteralPath (Join-Path $runtime 'local-processes.json') -Force -ErrorAction SilentlyContinue
  throw
}
Write-Host "API       : http://127.0.0.1:$apiPort/api/health/ (bind $apiBind)"
Write-Host "Dashboard : http://127.0.0.1:$frontendPort/ (bind $frontendBind)"
