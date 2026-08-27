param(
  [switch]$Lan,
  [switch]$SkipBuild,
  [switch]$SkipAdmin,
  [string]$Organization,
  [string]$AdminEmail,
  [string]$CustomerSlug
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')

$root = Get-ProjectRoot
Set-Location $root

function Wait-Docker([int]$TimeoutSeconds = 180) {
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  do {
    docker info --format '{{.ServerVersion}}' 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { return }
    Start-Sleep -Seconds 5
  } while ((Get-Date) -lt $deadline)
  throw 'Docker Desktop did not become ready within the expected time.'
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  throw 'Docker Desktop is required. Install it, enable WSL 2, then rerun this script.'
}

docker info --format '{{.ServerVersion}}' 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
  $dockerDesktop = 'C:\Program Files\Docker\Docker\Docker Desktop.exe'
  if (-not (Test-Path -LiteralPath $dockerDesktop)) {
    throw 'Docker Desktop is installed but could not be started automatically.'
  }
  Write-Host 'Starting Docker Desktop...'
  Start-Process -FilePath $dockerDesktop -WindowStyle Hidden
  Wait-Docker
}

$prepareArgs = @{}
if ($Lan) { $prepareArgs['Lan'] = $true }
& (Join-Path $PSScriptRoot 'prepare-local-compose-env.ps1') @prepareArgs

$composeArgs = @('compose', '--env-file', '.env', 'up', '-d')
if (-not $SkipBuild) { $composeArgs += '--build' }
$composeArgs += @('--wait', '--wait-timeout', '300')
& docker @composeArgs
if ($LASTEXITCODE -ne 0) {
  docker compose --env-file .env ps -a
  throw 'The Docker stack did not become healthy.'
}

docker compose --env-file .env exec -T api python manage.py check
if ($LASTEXITCODE -ne 0) { throw 'Django system check failed.' }
docker compose --env-file .env exec -T api python manage.py migrate --check
if ($LASTEXITCODE -ne 0) { throw 'Django migrations are not up to date.' }

if (-not $SkipAdmin) {
  if (-not $Organization) { $Organization = Read-Host 'Organization name' }
  if (-not $AdminEmail) { $AdminEmail = Read-Host 'Administrator email' }
  $adminArgs = @(
    'compose', '--env-file', '.env', 'exec', '-T', 'api',
    'python', 'manage.py', 'bootstrap_local_admin',
    '--organization', $Organization,
    '--email', $AdminEmail
  )
  if ($CustomerSlug) { $adminArgs += @('--customer-slug', $CustomerSlug) }

  $checkOutput = (& docker @($adminArgs + '--check') 2>&1) -join "`n"
  if ($LASTEXITCODE -ne 0) { throw $checkOutput }
  if ($checkOutput -notmatch '(?m)^EXISTS\s*$') {
    $securePassword = Read-Host 'Administrator password' -AsSecureString
    $passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
    try {
      $plainPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPointer)
      $plainPassword | & docker @($adminArgs + '--password-stdin')
      if ($LASTEXITCODE -ne 0) { throw 'Administrator bootstrap failed.' }
    } finally {
      $plainPassword = $null
      [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
    }
  } else {
    Write-Host 'The requested local administrator already exists; password unchanged.'
  }
}

$lanAddress = if ($Lan) {
  Get-NetIPConfiguration |
    Where-Object { $_.NetAdapter.Status -eq 'Up' -and $_.IPv4DefaultGateway -ne $null } |
    Select-Object -First 1 -ExpandProperty IPv4Address |
    Select-Object -ExpandProperty IPAddress
} else { $null }

Write-Host ''
Write-Host 'InfraSentinel AI is ready.' -ForegroundColor Green
Write-Host 'Local dashboard: http://127.0.0.1:5173/login'
Write-Host 'Local API:       http://127.0.0.1:8000/api/health/'
if ($lanAddress) {
  Write-Host "LAN dashboard:   http://${lanAddress}:5173/login"
  Write-Host "LAN agent API:   http://${lanAddress}:8000"
  Write-Host 'For another device, install the Private/LocalSubnet firewall rules as Administrator.'
}
