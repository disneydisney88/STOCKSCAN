$action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument '/c "G:\我的雲端硬碟\STOCKSCAN\scripts\daily_refresh.cmd"'
$trigger = New-ScheduledTaskTrigger -Daily -At '14:30'
Register-ScheduledTask -TaskName 'STOCKSCAN_daily_refresh' -Action $action -Trigger $trigger -Force | Out-Null
Start-ScheduledTask -TaskName 'STOCKSCAN_daily_refresh'
Get-ScheduledTaskInfo -TaskName 'STOCKSCAN_daily_refresh' | Select-Object TaskName, LastRunTime, LastTaskResult | Format-List
