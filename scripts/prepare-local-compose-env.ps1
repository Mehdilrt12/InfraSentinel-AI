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
