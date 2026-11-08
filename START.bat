@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto run
where py >nul 2>&1
if %errorlevel%==0 (py -3 -m venv .venv) else (python -m venv .venv)
if errorlevel 1 goto failed
:run
".venv\Scripts\python.exe" -c "import googleapiclient, google_auth_oauthlib, google_auth_httplib2, requests" >nul 2>&1
if errorlevel 1 (
    if exist requirements-lock.txt (
        ".venv\Scripts\python.exe" -m pip install -r requirements-lock.txt
    ) else (
        ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    )
    if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" app.py
if errorlevel 1 goto failed
exit /b 0
:failed
echo.
echo Khong the mo ung dung. Kiem tra Python 3.11+, Internet va thong bao loi ben tren.
pause
exit /b 1
