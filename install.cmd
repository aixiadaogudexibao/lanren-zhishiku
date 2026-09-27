@echo off
rem lanren-zhishiku one-click installer (Windows).
rem Double-click this file. Advanced options: run install.ps1 directly.
setlocal
chcp 65001 >nul
title lanren-zhishiku installer

echo.
echo   lanren-zhishiku  one-click install
echo   ---------------------------------
echo   data root : %USERPROFILE%\.zhishiku
echo   skills to : %USERPROFILE%\.pi\agent\skills
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" -DataRoot "%USERPROFILE%\.zhishiku"
set RC=%ERRORLEVEL%

echo.
if not "%RC%"=="0" (
  echo   [!] install.ps1 exited with code %RC%
) else (
  echo   [OK] reopen your agent session so the skills get loaded.
)
echo.
pause
exit /b %RC%
