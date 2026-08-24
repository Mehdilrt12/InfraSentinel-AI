param(
  [Parameter(Mandatory=$true)][string]$ComputerName,
  [string]$Username = ''
)
$ErrorActionPreference = 'Stop'
$collector = {
  $now = [DateTime]::UtcNow.ToString('o')
  $os = Get-CimInstance Win32_OperatingSystem
  $cpu = (Get-Counter '\Processor(_Total)\% Processor Time').CounterSamples[0].CookedValue
  $disks = Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3"
  $diskSize = ($disks | Measure-Object Size -Sum).Sum
  $diskFree = ($disks | Measure-Object FreeSpace -Sum).Sum
  $net = Get-Counter '\Network Interface(*)\Bytes Received/sec','\Network Interface(*)\Bytes Sent/sec'
  $received = ($net.CounterSamples | Where-Object Path -Match 'received' | Measure-Object CookedValue -Sum).Sum
  $sent = ($net.CounterSamples | Where-Object Path -Match 'sent' | Measure-Object CookedValue -Sum).Sum
  $vms = @(Get-VM | ForEach-Object {
    $vm = $_
    $adapters = @(Get-VMNetworkAdapter -VM $vm | Get-VMNetworkAdapterStatistics -ErrorAction SilentlyContinue)
    $drives = @(Get-VMHardDiskDrive -VM $vm -ErrorAction SilentlyContinue | ForEach-Object { if(Test-Path $_.Path){ Get-VHD -Path $_.Path } })
    $diskAllocated = ($drives | Measure-Object FileSize -Sum).Sum
    $diskMaximum = ($drives | Measure-Object Size -Sum).Sum
    [ordered]@{
      external_id = $vm.VMId.ToString(); kind = 'VM'; name = $vm.Name; state = $vm.State.ToString()
      parent_external_id = $env:COMPUTERNAME
      metadata = @{ generation=$vm.Generation; version=$vm.Version.ToString() }
      metrics = @(
        @{metric_name='system.cpu.utilization';metric_value=[double]$vm.CPUUsage;unit='%';timestamp=$now;metadata=@{}},
        @{metric_name='system.memory.utilization';metric_value=if($vm.MemoryAssigned){[double]($vm.MemoryDemand/$vm.MemoryAssigned*100)}else{$null};unit='%';timestamp=$now;metadata=@{assigned_bytes=$vm.MemoryAssigned;demand_bytes=$vm.MemoryDemand}},
        @{metric_name='system.disk.utilization';metric_value=if($diskMaximum){[double]($diskAllocated/$diskMaximum*100)}else{$null};unit='%';timestamp=$now;metadata=@{}},
        @{metric_name='system.network.in';metric_value=[double](($adapters|Measure-Object ReceivedBytes -Sum).Sum);unit='bytes';timestamp=$now;metadata=@{}},
        @{metric_name='system.network.out';metric_value=[double](($adapters|Measure-Object SentBytes -Sum).Sum);unit='bytes';timestamp=$now;metadata=@{}},
        @{metric_name='system.uptime';metric_value=[double]$vm.Uptime.TotalSeconds;unit='seconds';timestamp=$now;metadata=@{}},
        @{metric_name='virtual.machine.state';metric_value=if($vm.State -eq 'Running'){1}else{0};unit='state';status=$vm.State.ToString();timestamp=$now;metadata=@{}}
      )
    }
  })
  $hostMetrics = @(
    @{metric_name='system.cpu.utilization';metric_value=[double]$cpu;unit='%';timestamp=$now;metadata=@{}},
    @{metric_name='system.memory.utilization';metric_value=[double](($os.TotalVisibleMemorySize-$os.FreePhysicalMemory)/$os.TotalVisibleMemorySize*100);unit='%';timestamp=$now;metadata=@{}},
    @{metric_name='system.disk.utilization';metric_value=if($diskSize){[double](($diskSize-$diskFree)/$diskSize*100)}else{$null};unit='%';timestamp=$now;metadata=@{}},
    @{metric_name='system.disk.free';metric_value=[double]$diskFree;unit='bytes';timestamp=$now;metadata=@{}},
    @{metric_name='system.network.in';metric_value=[double]$received;unit='bytes/s';timestamp=$now;metadata=@{}},
    @{metric_name='system.network.out';metric_value=[double]$sent;unit='bytes/s';timestamp=$now;metadata=@{}},
    @{metric_name='system.uptime';metric_value=[double]((Get-Date)-$os.LastBootUpTime).TotalSeconds;unit='seconds';timestamp=$now;metadata=@{}}
  )
  [ordered]@{
    collected_at=$now
    hosts=@([ordered]@{external_id=$env:COMPUTERNAME;kind='HOST';name=$env:COMPUTERNAME;state='Available';parent_external_id='';metadata=@{vm_count=$vms.Count;os=$os.Caption};metrics=$hostMetrics})
    vms=$vms
  }
}
if($ComputerName -in @('.', 'localhost', '127.0.0.1', $env:COMPUTERNAME)) {
  $result = & $collector
} else {
  if(-not $Username -or -not $env:INFRASENTINEL_HYPERV_SECRET){ throw 'Remote Hyper-V credentials are required.' }
  $secure = ConvertTo-SecureString $env:INFRASENTINEL_HYPERV_SECRET -AsPlainText -Force
  $credential = [PSCredential]::new($Username, $secure)
  $result = Invoke-Command -ComputerName $ComputerName -Credential $credential -ScriptBlock $collector
}
$result | ConvertTo-Json -Depth 12 -Compress

