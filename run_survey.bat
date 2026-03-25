@echo off
chcp 65001 >nul
cd /d "%~dp0"
python "%~dp0launch_survey.py"
echo.
pause
