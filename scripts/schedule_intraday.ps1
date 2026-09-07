# STOCKSCAN 訊號 B Windows 工作排程器範例（P3——只提供檔案，冇幫你註冊）
#
# 用法（管理員 PowerShell，或者普通 PowerShell 都得）：
#   .\scripts\schedule_intraday.ps1
# 效果：每個工作日 09:25 HKT 自動啟動 run_intraday --loop 60，
#       個 script 自己會喺 16:10 後閪嘴唔掃（in_scan_session 判斷），PC 熄機就停。
# 移除任務：
#   Unregister-ScheduledTask -TaskName "STOCKSCAN intraday" -Confirm:$false

$python = (Get-Command python).Source
$repo = Split-Path -Parent $PSScriptRoot   # scripts/ 上一層 = repo 根目錄
$action = New-ScheduledTaskAction -Execute $python `
    -Argument "-m scripts.run_intraday --loop 60" `
    -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -Daily -At 09:25
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 8)
Register-ScheduledTask -TaskName "STOCKSCAN intraday" `
    -Action $action -Trigger $trigger -Settings $settings `
    -Description "STOCKSCAN 訊號B 即市掃描（交易日 09:30-16:10 HKT）" -Force
Write-Host "已註冊排程：STOCKSCAN intraday（每日 09:25 啟動，8 小時上限）"
