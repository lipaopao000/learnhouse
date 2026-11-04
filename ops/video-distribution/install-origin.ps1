$ErrorActionPreference = 'Stop'
$root = 'D:\deploy\LearnHouseVideo'
if (Test-Path (Join-Path $root 'nginx')) { throw 'Existing installation; review before replacing it' }
$zip = Join-Path $root 'nginx-1.31.8.zip'
$expected = 'FBB1501009BE34655CC238D460714CF20391B639013F4C73859813D7938783FD'
if ((Get-FileHash $zip -Algorithm SHA256).Hash -ne $expected) { throw 'nginx archive checksum mismatch' }
Expand-Archive -Path $zip -DestinationPath $root
Rename-Item (Join-Path $root 'nginx-1.31.8') 'nginx'
New-Item -ItemType Directory -Force -Path (Join-Path $root 'cache') | Out-Null
Copy-Item (Join-Path $root 'origin.nginx.private.conf') (Join-Path $root 'nginx\conf\nginx.conf')
# Only administrators and SYSTEM may access this dedicated deployment tree.
& icacls.exe $root /inheritance:r /grant:r '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-18:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Directory ACL update failed' }
& icacls.exe (Join-Path $root '*') /reset /T /C | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Child ACL inheritance failed' }
$action = New-ScheduledTaskAction -Execute (Join-Path $root 'nginx\nginx.exe') -Argument '-p D:/deploy/LearnHouseVideo/nginx/' -WorkingDirectory (Join-Path $root 'nginx')
$triggers = @(
    (New-ScheduledTaskTrigger -AtStartup),
    (New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 2))
)
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName 'LearnHouseVideo-Origin' -Action $action -Trigger $triggers -Principal $principal -Settings $settings | Out-Null
New-NetFirewallRule -DisplayName 'LearnHouseVideo source from Tencent Tailnet' -Direction Inbound -Protocol TCP -LocalPort 18887 -LocalAddress '__ORIGIN_IP__' -RemoteAddress '100.64.0.3' -Action Allow -Profile Any | Out-Null
Start-ScheduledTask -TaskName 'LearnHouseVideo-Origin'
Start-Sleep -Seconds 3
Get-ScheduledTaskInfo -TaskName 'LearnHouseVideo-Origin' | Select LastRunTime,LastTaskResult | ConvertTo-Json -Compress
Get-NetTCPConnection -State Listen -LocalPort 18887 -ErrorAction SilentlyContinue | Select LocalAddress,LocalPort | ConvertTo-Json -Compress
