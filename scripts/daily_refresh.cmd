@echo off
rem P6c daily refresh: rerun research reports + incremental warm + push to GitHub
rem (pure ASCII on purpose: cmd console codepage garbles UTF-8 Chinese paths)
cd /d "%~dp0.."
set "SSROOT=%~dp0.."
set "LOG=%~dp0..\logs\daily_refresh.log"
echo === %date% %time% daily_refresh start === >> "%LOG%"
python scripts\build_tracking.py >> "%LOG%" 2>&1
python scripts\build_go_predictors.py >> "%LOG%" 2>&1
python scripts\spring_duck.py >> "%LOG%" 2>&1
python scripts\build_concentration_features.py >> "%LOG%" 2>&1
python scripts\analyze_recurrence_concentration.py >> "%LOG%" 2>&1
pushd "C:\Users\klcho\webbsite-ccass-tool"
python scripts\warm_incremental.py --panel "%SSROOT%\data\eod\radar_eod_panel_full.csv" >> "%LOG%" 2>&1
popd
git add -A data\reports
git commit -m "daily refresh (scheduled)" --quiet
if %errorlevel%==0 (
  git pull --rebase origin main --quiet >> "%LOG%" 2>&1
  git push origin main --quiet >> "%LOG%" 2>&1
  echo pushed to GitHub, Streamlit Cloud will auto-redeploy >> "%LOG%"
)
echo === %date% %time% daily_refresh done === >> "%LOG%"
