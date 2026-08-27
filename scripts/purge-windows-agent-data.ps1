[CmdletBinding()]
param(
    [switch]$ConfirmPurge
)

$ErrorActionPreference = 'Stop'
$isAdministrator = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)
$expectedPath = [IO.Path]::GetFullPath((Join-Path $env:ProgramData 'InfraSentinel')).TrimEnd('\')

if (-not $ConfirmPurge) {
    throw 'Ajoutez -ConfirmPurge pour confirmer la suppression irréversible.'
}
if (-not $isAdministrator) {
    throw 'Exécutez ce script depuis PowerShell en tant qu’administrateur.'
}
if (Get-Service -Name InfraSentinelAgent -ErrorAction SilentlyContinue) {
    throw 'Désinstallez le service InfraSentinelAgent avant la purge.'
}
if (-not (Test-Path -LiteralPath $expectedPath)) {
    Write-Output 'Aucune donnée agent à supprimer.'
    exit 0
}

$resolvedPath = (Resolve-Path -LiteralPath $expectedPath).Path.TrimEnd('\')
if ($resolvedPath -ne $expectedPath) {
    throw "Cible de purge inattendue : $resolvedPath"
}

Remove-Item -LiteralPath $resolvedPath -Recurse -Force
if (Test-Path -LiteralPath $resolvedPath) {
    throw 'La purge des données agent a échoué.'
}
Write-Output "Données agent supprimées : $resolvedPath"
