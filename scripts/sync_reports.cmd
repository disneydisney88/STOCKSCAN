@echo off
cd /d "G:\我的雲端硬碟\STOCKSCAN"
git add -A data\reports
git commit -m "reports sync (scheduled)" --quiet
if not %errorlevel%==0 exit /b 0
git pull --rebase origin main --quiet
git push origin main --quiet
