@echo off
setlocal
cd /d "%~dp0"
if not exist "rtss_console.py" (
    echo rtss_console.py not found. Keep this BAT in the STOCKSCAN folder.
    pause
    exit /b 1
)
if exist "C:\Python313\python.exe" (
    "C:\Python313\python.exe" -m streamlit run rtss_console.py
) else (
    python -m streamlit run rtss_console.py
)
