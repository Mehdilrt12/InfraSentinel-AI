[CmdletBinding()]
param(
    [string]$Version = '2.0.0',
    [switch]$SkipTests
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$agentRoot = Join-Path $projectRoot 'agent'
$specPath = Join-Path $agentRoot 'InfraSentinelAgent.spec'
$sourceExe = Join-Path $agentRoot 'dist\InfraSentinelAgent.exe'
$installerScript = Join-Path $projectRoot 'installer\windows\InfraSentinelAgent.iss'
$installerOutput = Join-Path $projectRoot "installer\windows\output\InfraSentinelAgent-$Version-setup.exe"
$isccCandidates = @(
    (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'),
    (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
    (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe')
)
$iscc = $isccCandidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
$declaredVersion = (& python -c "import sys; sys.path.insert(0, r'$agentRoot'); from infrasentinel_agent import __version__; print(__version__)").Trim()

if (-not $IsWindows -and $PSVersionTable.PSEdition -eq 'Core') {
    throw 'La construction de l’agent nécessite Windows.'
}
if (-not $iscc) {
    throw 'Inno Setup 6 (ISCC.exe) est requis pour construire le package.'
}
if (-not (Get-Command pyinstaller.exe -ErrorAction SilentlyContinue)) {
    throw 'PyInstaller est requis pour construire l’exécutable agent.'
}
if ($Version -ne $declaredVersion) {
    throw "La version demandée ($Version) diffère de la version agent ($declaredVersion)."
}

if (-not $SkipTests) {
    Push-Location $agentRoot
    try {
        python -m unittest discover -s tests -v
        if ($LASTEXITCODE -ne 0) { throw 'Les tests unitaires de l’agent ont échoué.' }
    }
    finally {
        Pop-Location
    }
}

Push-Location $agentRoot
try {
    pyinstaller.exe --clean --noconfirm $specPath
    if ($LASTEXITCODE -ne 0) { throw 'La construction PyInstaller a échoué.' }
}
finally {
    Pop-Location
}

& $sourceExe --version
if ($LASTEXITCODE -ne 0) { throw 'Le binaire construit ne démarre pas.' }

& $iscc "/DMyAppVersion=$Version" "/DSourceExe=$sourceExe" $installerScript
if ($LASTEXITCODE -ne 0) { throw 'La compilation Inno Setup a échoué.' }
if (-not (Test-Path -LiteralPath $installerOutput)) {
    throw "Le package attendu n’a pas été produit : $installerOutput"
}

$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $installerOutput).Hash.ToLowerInvariant()
$hashPath = "$installerOutput.sha256"
"$hash  $(Split-Path -Leaf $installerOutput)" | Set-Content -LiteralPath $hashPath -Encoding ascii

[pscustomobject]@{
    Installer = $installerOutput
    Sha256 = $hash
    HashFile = $hashPath
}
