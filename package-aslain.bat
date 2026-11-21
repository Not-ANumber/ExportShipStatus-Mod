@echo off
rem ============================================================
rem  ExportShipStatus -> Aslain custom-mod package
rem
rem  Builds ExportShipStatus-aslain.zip with this layout:
rem    res_mods\PnFModsLoader.py                  (0-byte activation marker)
rem    res_mods\PnFMods\ExportShipStatus\Main.py
rem    res_mods\PnFMods\ExportShipStatus\core.py
rem
rem  The same zip works with both Aslain products:
rem    - classic installer: <game>\Aslain_Modpack\Custom_mods
rem    - Mod Manager app : <game>\Aslain_custom_mods
rem
rem  No version folder is used, because the classic installer requires
rem  res_mods\... at the archive root; the Mod Manager also accepts that
rem  layout (it remaps it to bin\<active build>\res_mods\...).
rem ============================================================
setlocal EnableExtensions
cd /d "%~dp0"

set "SRC=%~dp0src\ExportShipStatus"
set "OUT=%~dp0ExportShipStatus-aslain.zip"
set "STAGE=%TEMP%\sst_aslain_%RANDOM%"

if not exist "%SRC%\Main.py" (
    echo [ERROR] mod source not found: "%SRC%\Main.py"
    exit /b 1
)
if not exist "%SRC%\core.py" (
    echo [ERROR] mod source not found: "%SRC%\core.py"
    exit /b 1
)

del "%OUT%" >nul 2>&1
if exist "%STAGE%" rmdir /s /q "%STAGE%"
mkdir "%STAGE%\res_mods\PnFMods\ExportShipStatus" >nul

copy /Y "%SRC%\Main.py" "%STAGE%\res_mods\PnFMods\ExportShipStatus\Main.py" >nul
copy /Y "%SRC%\core.py" "%STAGE%\res_mods\PnFMods\ExportShipStatus\core.py" >nul

rem PnFModsLoader.py only has to exist; the client's scanner is activated by
rem the file's presence. Aslain's own PnF mods ship the same 0-byte marker.
type nul > "%STAGE%\res_mods\PnFModsLoader.py"

rem Use the .NET ZipArchive helper instead of Compress-Archive: Windows
rem PowerShell 5.1 writes backslash entry names, which some extractors take
rem as one literal filename. The helper writes standard '/' separators.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\make-aslain-zip.ps1" -SourceDir "%STAGE%" -OutFile "%OUT%"
if errorlevel 1 (
    echo [ERROR] packaging failed
    rmdir /s /q "%STAGE%" >nul 2>&1
    exit /b 1
)
rmdir /s /q "%STAGE%" >nul 2>&1

echo [OK] created: %OUT%
echo.
echo Install:
echo   Mod Manager : put the zip in  ^<game^>\Aslain_custom_mods\
echo                 then click Install/Apply in the app.
echo   Classic     : put the zip in  ^<game^>\Aslain_Modpack\Custom_mods\
echo                 then run the modpack installer.
exit /b 0
