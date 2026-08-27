[CmdletBinding()]
param(
    [string]$Stages = '1,10,25,50,100',
    [double]$DurationSeconds = 30,
    [double]$IntervalSeconds = 1,
    [double]$HeartbeatIntervalSeconds = 60,
    [double]$CooldownSeconds = 5,
    [int]$Port = 8010,
    [string]$AgentRequestRate = '100000/min'
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
$projectRoot = Get-ProjectRoot
$backendRoot = Join-Path $projectRoot 'backend'
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$resultsDirectory = Join-Path $projectRoot 'runtime\performance'
$runId = 'P24' + (Get-Date -Format 'yyyyMMddHHmmss')
$resultPath = Join-Path $resultsDirectory "$runId.json"
$stdoutPath = Join-Path $resultsDirectory "$runId-api.stdout.log"
$stderrPath = Join-Path $resultsDirectory "$runId-api.stderr.log"

if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    throw "Le port $Port est déjà utilisé."
}
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Environnement .venv introuvable; exécutez scripts/setup.ps1.'
}

Set-Location $projectRoot
Import-DotEnv 'backend\.env'
if ($env:DATABASE_ENGINE -ne 'postgresql') {
    throw 'Le test de performance exige DATABASE_ENGINE=postgresql.'
}
$env:DJANGO_DEBUG = 'false'
$env:AGENT_REQUEST_RATE = $AgentRequestRate
$env:CHANNEL_LAYER = 'redis'
New-Item -ItemType Directory -Path $resultsDirectory -Force | Out-Null

$api = Start-Process -FilePath $python `
    -ArgumentList '-m','daphne','-b','127.0.0.1','-p',"$Port",'config.asgi:application' `
    -WorkingDirectory $backendRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutPath `
    -RedirectStandardError $stderrPath `
    -PassThru

try {
    $deadline = (Get-Date).AddSeconds(30)
    do {
        Start-Sleep -Milliseconds 250
        $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        if ($listener) { break }
        if ($api.HasExited) {
            throw "Le backend de performance s’est arrêté. Consultez $stderrPath"
        }
    } while ((Get-Date) -lt $deadline)
    if (-not $listener) { throw "Le backend n’écoute pas sur le port $Port." }

    $healthUrl = "http://127.0.0.1:$Port/api/health/"
    do {
        try {
            $health = Invoke-WebRequest -UseBasicParsing -Uri $healthUrl -TimeoutSec 10
        }
        catch {
            $health = $null
            Start-Sleep -Milliseconds 500
        }
    } while ((-not $health -or $health.StatusCode -ne 200) -and (Get-Date) -lt $deadline)
    if (-not $health -or $health.StatusCode -ne 200) {
        throw "Le healthcheck du backend de performance a échoué."
    }

    $backendPid = $listener.OwningProcess
    & $python (Join-Path $PSScriptRoot 'performance\load_test.py') `
        --base-url "http://127.0.0.1:$Port" `
        --backend-pid $backendPid `
        --stages $Stages `
        --duration $DurationSeconds `
        --interval $IntervalSeconds `
        --heartbeat-interval $HeartbeatIntervalSeconds `
        --cooldown $CooldownSeconds `
        --run-id $runId `
        --output $resultPath
    if ($LASTEXITCODE -ne 0) { throw 'Le banc de charge a échoué.' }
}
finally {
    Stop-ProcessTree -ProcessId $api.Id
}

[pscustomobject]@{
    RunId = $runId
    Result = $resultPath
    ApiStdout = $stdoutPath
    ApiStderr = $stderrPath
}
