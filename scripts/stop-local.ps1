$ErrorActionPreference = 'SilentlyContinue'
. (Join-Path $PSScriptRoot 'common.ps1')
$root = Get-ProjectRoot
$file = Join-Path $root 'runtime\local-processes.json'
if (Test-Path -LiteralPath $file) {
  $items = @(Get-Content -LiteralPath $file -Raw | ConvertFrom-Json)
  foreach ($item in $items) { Stop-ProcessTree -ProcessId $item.id }
  Remove-Item -LiteralPath $file -Force
}
Write-Host 'Processus locaux InfraSentinel arrêtés.'
