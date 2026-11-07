@echo off
rem ============================================================
rem  ExportShipStatus distribution packager
rem  Builds ExportShipStatus-dist.zip next to this script with:
rem    install.bat / uninstall.bat / tools\find-game.ps1
rem    src\ExportShipStatus\  (the mod itself)
rem    README.md               (install guide)
rem    LICENSE                 (MIT)
rem  This packager ships the mod and its installer only.
rem ============================================================
setlocal EnableExtensions
cd /d "%~dp0"

set "STAGE=%TEMP%\sst_dist_%RANDOM%"
set "OUT=%~dp0ExportShipStatus-dist.zip"
del "%OUT%" >nul 2>&1

if not exist "%STAGE%" mkdir "%STAGE%"
copy /Y "install.bat" "%STAGE%\" >nul
copy /Y "uninstall.bat" "%STAGE%\" >nul
copy /Y "README.md" "%STAGE%\README.md" >nul
copy /Y "LICENSE" "%STAGE%\LICENSE" >nul
if not exist "%STAGE%\tools" mkdir "%STAGE%\tools"
copy /Y "tools\find-game.ps1" "%STAGE%\tools\" >nul
if not exist "%STAGE%\src" mkdir "%STAGE%\src"
rem never ship bytecode left behind by local test runs
if exist "src\ExportShipStatus\__pycache__" rmdir /s /q "src\ExportShipStatus\__pycache__"
xcopy /E /Y /Q "src\ExportShipStatus" "%STAGE%\src\ExportShipStatus\" >nul

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Compress-Archive -Path '%STAGE%\*' -DestinationPath '%OUT%' -Force"
if errorlevel 1 (
    echo [ERROR] packaging failed
    exit /b 1
)
rmdir /s /q "%STAGE%" >nul 2>&1
echo [OK] created: %OUT%
exit /b 0
