@echo off
rem ============================================================
rem  ExportShipStatus uninstall (distribution build)
rem  Same game-path resolution as install.bat; removes the mod
rem  from the newest bin\<version> directory only.
rem  NOTE: inside parenthesized blocks only !var! (delayed) is
rem  used; %var% would break on paths like "Program Files (x86)".
rem ============================================================
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "PS=powershell -NoProfile -ExecutionPolicy Bypass -File"
set "SCRIPT=%~dp0tools\find-game.ps1"

set "GAME=%~1"
if not defined GAME (
    set "TMPLIST=%TEMP%\sst_games_%RANDOM%.txt"
    %PS% "%SCRIPT%" > "!TMPLIST!" 2>nul
    set /a COUNT=0
    for /f "usebackq delims=" %%L in ("!TMPLIST!") do set /a COUNT+=1
    if !COUNT! EQU 0 (
        echo [INFO] No installation auto-detected; pass the path explicitly:
        echo        uninstall.bat "D:\Games\World_of_Warships"
        exit /b 1
    ) else if !COUNT! EQU 1 (
        for /f "usebackq delims=" %%L in ("!TMPLIST!") do set "GAME=%%L"
    ) else (
        echo [INFO] Multiple installations found:
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

set "BINLIST=%TEMP%\sst_bin_%RANDOM%.txt"
%PS% "%SCRIPT%" -Root "%GAME%" -LatestBin > "%BINLIST%" 2>nul
for /f "usebackq delims=" %%B in ("%BINLIST%") do set "TARGETBIN=%%B"
del "%BINLIST%" >nul 2>&1
if not defined TARGETBIN (
    echo [ERROR] No versioned bin folder under: !GAME!\bin
    exit /b 1
)
set "DEST=!TARGETBIN!\res_mods\PnFMods\ExportShipStatus"
if exist "%DEST%" (
    rmdir /s /q "%DEST%"
    echo [OK] Removed: !DEST!
) else (
    echo [INFO] Not installed: !DEST!
)

rem res_mods\PnFModsLoader.py is the shared loading switch for every PnFMods mod
rem (install.bat creates it if missing), so it is deliberately left in place.
if exist "!TARGETBIN!\res_mods\PnFModsLoader.py" (
    echo [INFO] Kept  : !TARGETBIN!\res_mods\PnFModsLoader.py ^(shared mod loading switch^)
)
exit /b 0
