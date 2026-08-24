. (Join-Path $PSScriptRoot 'common.ps1')
$root = Get-ProjectRoot
$file = Join-Path $root 'runtime\local-processes.json'
if (Test-Path -LiteralPath $file) {
  @(Get-Content -LiteralPath $file -Raw | ConvertFrom-Json) | ForEach-Object { $process = Get-Process -Id $_.id -ErrorAction SilentlyContinue; [pscustomobject]@{ Service=$_.name; PID=$_.id; Status=if($process){'RUNNING'}else{'STOPPED'} } } | Format-Table -AutoSize
} else { Write-Host 'Aucun fichier de processus local.' }
try { (Invoke-RestMethod 'http://127.0.0.1:8000/api/health/' -TimeoutSec 3) | ConvertTo-Json -Compress } catch { 'API: UNREACHABLE' }

