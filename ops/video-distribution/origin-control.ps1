param([ValidateSet('reload', 'stop')][string]$Action = 'reload')
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
# nginx's control event is owned by SYSTEM; signal it from the same account.
$taskName = 'LearnHouseVideo-Control'
$job = New-ScheduledTaskAction -Execute 'D:\deploy\LearnHouseVideo\nginx\nginx.exe' -Argument ('-p D:/deploy/LearnHouseVideo/nginx/ -s ' + $Action) -WorkingDirectory 'D:\deploy\LearnHouseVideo\nginx'
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName $taskName -Action $job -Principal $principal -Force | Out-Null
try {
    Start-ScheduledTask -TaskName $taskName
    Start-Sleep -Seconds 2
    $result = (Get-ScheduledTaskInfo -TaskName $taskName).LastTaskResult
    if ($result -ne 0) { throw ('nginx control failed: ' + $result) }
} finally {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}
