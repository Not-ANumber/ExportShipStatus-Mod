@echo off
rem ============================================================
rem  ExportShipStatus install (distribution build)
rem  Usage:
rem    install.bat                     auto-detect the game path
rem    install.bat "D:\Games\World_of_Warships"   explicit path
rem
rem  Behaviour:
rem    - detects candidates: registry (WGC/Steam) -> Steam
rem      libraryfolders.vdf -> common default paths
rem    - asks to pick when several games are found
rem    - installs ONLY into the newest bin\<version> directory
rem    - checks write permission first (run as admin if it fails)
rem    - removes an old copy of the mod before installing
rem    - ensures res_mods\PnFModsLoader.py exists (mod loading switch)
rem
rem  NOTE: inside parenthesized blocks only !var! (delayed) is used;
rem  %var% would break on paths containing parentheses like "(x86)".
rem ============================================================
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "PS=powershell -NoProfile -ExecutionPolicy Bypass -File"
set "SCRIPT=%~dp0tools\find-game.ps1"
set "SRC=%~dp0src\ExportShipStatus"
if not exist "%SRC%\Main.py" (
    echo [ERROR] mod source not found next to this script: !SRC!
    exit /b 1
)

rem ---------- 1. resolve game root ----------
set "GAME=%~1"
if not defined GAME (
    set "TMPLIST=%TEMP%\sst_games_%RANDOM%.txt"
    %PS% "%SCRIPT%" > "!TMPLIST!" 2>nul
    set /a COUNT=0
    for /f "usebackq delims=" %%L in ("!TMPLIST!") do set /a COUNT+=1
    if !COUNT! EQU 0 (
        echo [INFO] No World of Warships installation auto-detected.
        set /p "GAME=Enter the full game folder path (e.g. D:\Games\World_of_Warships): "
    ) else if !COUNT! EQU 1 (
        for /f "usebackq delims=" %%L in ("!TMPLIST!") do set "GAME=%%L"
    ) else (
        echo [INFO] Multiple World of Warships installations found:
        set /a IDX=0
        for /f "usebackq delims=" %%L in ("!TMPLIST!") do (
            set /a IDX+=1
            call echo   %%IDX%%. %%L
        )
        set /p "PICK=Pick a number [1]: "
        if not defined PICK set "PICK=1"
        set /a IDX=0
        for /f "usebackq delims=" %%L in ("!TMPLIST!") do (
            set /a IDX+=1
            if !IDX! EQU !PICK! set "GAME=%%L"
        )
    )
    del "!TMPLIST!" >nul 2>&1
)
if not defined GAME (
    echo [ERROR] No game path given.
    exit /b 1
)
set "GAME=%GAME:"=%"
if not exist "%GAME%\bin" (
    echo [ERROR] Game path not found or has no bin folder: !GAME!
    exit /b 1
)

rem ---------- 2. locate newest bin version ----------
set "BINLIST=%TEMP%\sst_bin_%RANDOM%.txt"
%PS% "%SCRIPT%" -Root "%GAME%" -LatestBin > "%BINLIST%" 2>nul
for /f "usebackq delims=" %%B in ("%BINLIST%") do set "TARGETBIN=%%B"
del "%BINLIST%" >nul 2>&1
if not defined TARGETBIN (
    echo [ERROR] No versioned bin folder under: !GAME!\bin
    exit /b 1
)
echo [INFO] Game root : !GAME!
echo [INFO] Target    : !TARGETBIN!

rem ---------- 3. write permission check ----------
set "PROBE=!TARGETBIN!\res_mods\.sst_write_test"
echo test> "%PROBE%" 2>nul
if errorlevel 1 (
    echo.
    echo [ERROR] No write permission for: !TARGETBIN!\res_mods
    echo         Right-click this script and choose "Run as administrator",
    echo         or move the game outside Program Files.
    exit /b 1
)
del "%PROBE%" >nul 2>&1

rem ---------- 4. ensure the PnFMods loading switch ----------
rem The client scans res_mods\PnFMods and loads the mods in it ONLY when
rem res_mods\PnFModsLoader.py exists next to it. A fresh bin\<version> after a
rem game update has an empty res_mods, so the mod would silently never load
rem (python.log: "'PnFModsLoader.py' was not found at './res_mods/'").
rem The file itself is empty - its presence alone is the opt-in flag.
set "MARKER=!TARGETBIN!\res_mods\PnFModsLoader.py"
if exist "!MARKER!" (
    echo [INFO] PnFMods loading switch already present.
) else (
    type nul > "!MARKER!"
    if not exist "!MARKER!" (
        echo [ERROR] Could not create: !MARKER!
        exit /b 1
    )
    echo [INFO] Created PnFMods loading switch: !MARKER!
)

rem ---------- 5. clean previous copy, then install ----------
set "DEST=!TARGETBIN!\res_mods\PnFMods\ExportShipStatus"
rem never ship bytecode left behind by local test runs
if exist "%SRC%\__pycache__" rmdir /s /q "%SRC%\__pycache__"
if exist "%DEST%" rmdir /s /q "%DEST%"
if not exist "%DEST%" mkdir "%DEST%"
xcopy "%SRC%\*" "%DEST%\" /E /Y /Q >nul
if errorlevel 1 (
    echo [ERROR] Copy failed.
    exit /b 1
)
echo.
echo [OK] ExportShipStatus installed to:
echo     !DEST!
echo.
echo Next: restart the game client. After every game update, rerun this script.
exit /b 0
