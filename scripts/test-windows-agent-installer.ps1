[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$SetupPath,
    [Parameter(Mandatory)]
    [string]$ServerUrl,
    [Parameter(Mandatory)]
    [string]$EnrollmentFile,
    [string]$MachineName = "$env:COMPUTERNAME-installer-test",
    [switch]$AllowHttpLocalhost
)

$ErrorActionPreference = 'Stop'
$serviceName = 'InfraSentinelAgent'
$dataDirectory = Join-Path $env:ProgramData 'InfraSentinel'
$installDirectory = Join-Path $env:ProgramFiles 'InfraSentinel Agent'
$agentExecutable = Join-Path $installDirectory 'InfraSentinelAgent.exe'
$invalidTokenFile = Join-Path $env:TEMP ("infrasentinel-invalid-{0}.txt" -f [guid]::NewGuid())
$unavailableTokenFile = Join-Path $env:TEMP ("infrasentinel-unavailable-{0}.txt" -f [guid]::NewGuid())
$isAdministrator = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)

if (-not $isAdministrator) {
    throw 'Exécutez ce script depuis PowerShell en tant qu’administrateur.'
}
if (-not (Test-Path -LiteralPath $SetupPath)) { throw 'SetupPath est introuvable.' }
if (-not (Test-Path -LiteralPath $EnrollmentFile)) { throw 'EnrollmentFile est introuvable.' }
if (Get-Service -Name $serviceName -ErrorAction SilentlyContinue) {
    throw 'Le test exige une machine sans service InfraSentinelAgent installé.'
}

function Invoke-Setup {
    param(
        [string]$Url,
        [string]$TokenFile,
        [switch]$ExpectFailure
    )
    $arguments = @(
        '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART',
        "/SERVERURL=$Url", "/MACHINENAME=$MachineName"
    )
    if ($TokenFile) { $arguments += "/ENROLLMENTFILE=$TokenFile" }
    if ($AllowHttpLocalhost) { $arguments += '/ALLOWHTTPLOCALHOST=1' }
    $process = Start-Process -FilePath $SetupPath -ArgumentList $arguments -Wait -PassThru
    if ($ExpectFailure -and $process.ExitCode -eq 0) {
        throw "L’installation devait échouer mais a retourné 0 pour $Url."
    }
    if (-not $ExpectFailure -and $process.ExitCode -ne 0) {
        throw "L’installation a échoué avec le code $($process.ExitCode)."
    }
}

try {
    [IO.File]::WriteAllText($invalidTokenFile, [guid]::NewGuid().ToString('N'))
    [IO.File]::WriteAllText($unavailableTokenFile, 'unavailable-test-token')

    Invoke-Setup -Url $ServerUrl -TokenFile $invalidTokenFile -ExpectFailure
    if (Get-Service -Name $serviceName -ErrorAction SilentlyContinue) {
        throw 'Le service existe après le test de jeton invalide.'
    }

    Invoke-Setup -Url 'https://127.0.0.1:1' -TokenFile $unavailableTokenFile -ExpectFailure
    if (Get-Service -Name $serviceName -ErrorAction SilentlyContinue) {
        throw 'Le service existe après le test de serveur indisponible.'
    }

    Invoke-Setup -Url $ServerUrl -TokenFile $EnrollmentFile
    $service = Get-Service -Name $serviceName
    $serviceConfiguration = Get-CimInstance Win32_Service -Filter "Name='$serviceName'"
    if ($serviceConfiguration.StartMode -ne 'Auto') {
        throw "Le service n’est pas en démarrage automatique : $($serviceConfiguration.StartMode)"
    }
    if ($service.Status -ne 'Running') { throw 'Le service ne fonctionne pas après installation.' }
    if (-not (Test-Path -LiteralPath $agentExecutable)) { throw 'Le binaire agent est absent.' }

    $configText = Get-Content -Raw -LiteralPath (Join-Path $dataDirectory 'config.json')
    $enrollmentValue = (Get-Content -Raw -LiteralPath $EnrollmentFile).Trim()
    if ($configText.Contains($enrollmentValue) -or $configText -match '(?i)token|secret|password') {
        throw 'La configuration contient une information qui ressemble à un secret.'
    }

    Invoke-Setup -Url $ServerUrl -TokenFile ''
    if ((Get-Service -Name $serviceName).Status -ne 'Running') {
        throw 'Le service ne fonctionne pas après mise à niveau.'
    }

    Restart-Service -Name $serviceName -Force
    (Get-Service -Name $serviceName).WaitForStatus('Running', [TimeSpan]::FromSeconds(30))

    $uninstaller = Get-ChildItem -LiteralPath $installDirectory -Filter 'unins*.exe' | Select-Object -First 1
    if (-not $uninstaller) { throw 'Le désinstalleur est introuvable.' }
    $uninstall = Start-Process -FilePath $uninstaller.FullName -ArgumentList @(
        '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART'
    ) -Wait -PassThru
    if ($uninstall.ExitCode -ne 0) { throw 'La désinstallation a échoué.' }
    if (Get-Service -Name $serviceName -ErrorAction SilentlyContinue) {
        throw 'Le service existe encore après désinstallation.'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $dataDirectory 'config.json'))) {
        throw 'La désinstallation n’a pas conservé la configuration attendue.'
    }

    [pscustomobject]@{
        InvalidToken = 'PASS'
        ServerUnavailable = 'PASS'
        Installation = 'PASS'
        Upgrade = 'PASS'
        ServiceRestart = 'PASS'
        Uninstall = 'PASS'
        ConfigurationPreserved = 'PASS'
    }
}
finally {
    Remove-Item -LiteralPath $invalidTokenFile, $unavailableTokenFile -Force -ErrorAction SilentlyContinue
}
