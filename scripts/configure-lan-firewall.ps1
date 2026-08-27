param(
  [ValidateSet('Status', 'Install', 'Remove')]
  [string]$Action = 'Status',
  [ValidateRange(1, 65535)]
  [int]$FrontendPort = 5173,
  [ValidateRange(1, 65535)]
  [int]$ApiPort = 8000
)

$ErrorActionPreference = 'Stop'
$rulePrefix = 'InfraSentinel LAN'
$rules = @(
  @{ Name = "$rulePrefix Frontend"; Port = $FrontendPort; Purpose = 'React/Nginx dashboard' },
  @{ Name = "$rulePrefix API"; Port = $ApiPort; Purpose = 'Django API, agent ingestion and WebSocket' }
)

function Test-Administrator {
  $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = [Security.Principal.WindowsPrincipal]::new($identity)
  return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if ($Action -in @('Install', 'Remove') -and -not (Test-Administrator)) {
  throw "Cette action exige PowerShell exécuté en tant qu'administrateur."
}

if ($Action -eq 'Install') {
  foreach ($rule in $rules) {
    Get-NetFirewallRule -DisplayName $rule.Name -ErrorAction SilentlyContinue |
      Remove-NetFirewallRule
    New-NetFirewallRule `
      -DisplayName $rule.Name `
      -Description "$($rule.Purpose) - réseau local InfraSentinel autorisé" `
      -Direction Inbound `
      -Action Allow `
      -Protocol TCP `
      -LocalPort $rule.Port `
      -Profile Private `
      -RemoteAddress LocalSubnet | Out-Null
  }
}

if ($Action -eq 'Remove') {
  foreach ($rule in $rules) {
    Get-NetFirewallRule -DisplayName $rule.Name -ErrorAction SilentlyContinue |
      Remove-NetFirewallRule
  }
}

$profiles = Get-NetConnectionProfile |
  Select-Object InterfaceAlias, NetworkCategory, IPv4Connectivity
$state = foreach ($rule in $rules) {
  $firewallRule = Get-NetFirewallRule -DisplayName $rule.Name -ErrorAction SilentlyContinue
  [pscustomobject]@{
    Rule = $rule.Name
    Port = $rule.Port
    Protocol = 'TCP'
    Profile = 'Private'
    RemoteAddress = 'LocalSubnet'
    Enabled = [bool]$firewallRule
    Purpose = $rule.Purpose
  }
}

Write-Output 'Network profiles:'
$profiles | Format-Table -AutoSize
Write-Output 'InfraSentinel inbound rules:'
$state | Format-Table -AutoSize
