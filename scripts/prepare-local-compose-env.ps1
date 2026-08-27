param(
  [switch]$Lan,
  [string]$LanAddress
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')

$root = Get-ProjectRoot
$templatePath = Join-Path $root '.env.example'
$targetPath = Join-Path $root '.env'
$backendPath = Join-Path $root 'backend\.env'

function Read-EnvMap([string]$Path) {
  $result = [ordered]@{}
  if (-not (Test-Path -LiteralPath $Path)) { return $result }
  foreach ($line in Get-Content -LiteralPath $Path) {
    $trimmed = $line.Trim()
    if (-not $trimmed -or $trimmed.StartsWith('#') -or -not $trimmed.Contains('=')) { continue }
    $name, $value = $trimmed.Split('=', 2)
    $result[$name.Trim()] = $value.Trim().Trim('"').Trim("'")
  }
  return $result
}

function New-LocalSecret {
  $bytes = [byte[]]::new(48)
  [Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
  return [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function Get-ActiveLanAddress {
  $candidate = Get-NetIPConfiguration |
    Where-Object {
      $_.NetAdapter.Status -eq 'Up' -and
      $_.IPv4DefaultGateway -ne $null -and
      $_.IPv4Address.IPAddress -notmatch '^(127|169\.254)\.'
    } |
    Sort-Object InterfaceIndex |
    Select-Object -First 1
  if (-not $candidate) { throw "Aucune adresse IPv4 LAN active avec passerelle n'a été détectée." }
  return $candidate.IPv4Address.IPAddress
}

function Assert-IPv4Address([string]$Address) {
  $parsed = $null
  if (-not [Net.IPAddress]::TryParse($Address, [ref]$parsed) -or
      $parsed.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork -or
      [Net.IPAddress]::IsLoopback($parsed) -or
      $Address -match '^169\.254\.') {
    throw "Adresse IPv4 LAN invalide : $Address"
  }
}

function Merge-EnvList([string]$Current, [string[]]$Required) {
  $items = [Collections.Generic.List[string]]::new()
  foreach ($value in @($Current -split ',') + $Required) {
    $trimmed = $value.Trim()
    if ($trimmed -and -not $items.Contains($trimmed)) { $items.Add($trimmed) }
  }
  return $items -join ','
}

if (-not (Test-Path -LiteralPath $templatePath)) { throw '.env.example est introuvable.' }
$existing = Read-EnvMap $targetPath
$backend = Read-EnvMap $backendPath
$required = @('DJANGO_SECRET_KEY', 'JWT_SIGNING_KEY', 'POSTGRES_PASSWORD')

foreach ($name in $required) {
  $current = $existing[$name]
  if ($current -and $current -notmatch 'change-me|replace-with|<[^>]+>') { continue }
  $candidate = $backend[$name]
  if ($candidate -and $candidate -notmatch 'change-me|replace-with|<[^>]+>') {
    $existing[$name] = $candidate
  } else {
    $existing[$name] = New-LocalSecret
  }
}

if ($Lan) {
  if (-not $LanAddress) { $LanAddress = Get-ActiveLanAddress }
  Assert-IPv4Address $LanAddress
  $apiPort = if ($existing['API_PORT']) { $existing['API_PORT'] } else { '8000' }
  $frontendPort = if ($existing['FRONTEND_PORT']) { $existing['FRONTEND_PORT'] } else { '5173' }
  $lanFrontendOrigin = "http://${LanAddress}:$frontendPort"

  $existing['API_BIND_ADDRESS'] = '0.0.0.0'
  $existing['FRONTEND_BIND_ADDRESS'] = '0.0.0.0'
  $existing['POSTGRES_BIND_ADDRESS'] = '127.0.0.1'
  $existing['REDIS_BIND_ADDRESS'] = '127.0.0.1'
  $existing['FRONTEND_URL'] = $lanFrontendOrigin
  $existing['ALLOWED_HOSTS'] = Merge-EnvList $existing['ALLOWED_HOSTS'] @('localhost', '127.0.0.1', 'api', $LanAddress)
  $existing['CORS_ALLOWED_ORIGINS'] = Merge-EnvList $existing['CORS_ALLOWED_ORIGINS'] @('http://localhost:5173', 'http://127.0.0.1:5173', $lanFrontendOrigin)
  $existing['CSRF_TRUSTED_ORIGINS'] = Merge-EnvList $existing['CSRF_TRUSTED_ORIGINS'] @('http://localhost:5173', 'http://127.0.0.1:5173', $lanFrontendOrigin)
}

$output = foreach ($line in Get-Content -LiteralPath $templatePath) {
  if ($line -match '^([A-Za-z_][A-Za-z0-9_]*)=') {
    $name = $Matches[1]
    if ($existing.Contains($name)) { "$name=$($existing[$name])" } else { $line }
  } else {
    $line
  }
}

[IO.File]::WriteAllLines($targetPath, $output, [Text.UTF8Encoding]::new($false))
Write-Host 'Configuration Docker locale préparée dans .env (valeurs sensibles masquées).'
foreach ($name in $required) { Write-Host "$name=CONFIGURED" }
if ($Lan) {
  Write-Host "Mode LAN configuré pour $LanAddress." -ForegroundColor Green
  Write-Host "Dashboard : http://${LanAddress}:$frontendPort"
  Write-Host "API agent : http://${LanAddress}:$apiPort"
  Write-Host 'PostgreSQL et Redis restent limités à 127.0.0.1.'
}
