# find-game.ps1 — ExportShipStatus 安装辅助
# 用法:
#   1) 列出候选游戏根目录:  powershell -ExecutionPolicy Bypass -File find-game.ps1
#      (可选 -Explicit "D:\Games\World_of_Warships" 只校验该路径)
#   2) 取最新 bin 版本目录:  powershell -ExecutionPolicy Bypass -File find-game.ps1 -Root "..." -LatestBin
#
# 候选来源（去重、仅保留存在且含 bin 子目录的）:
#   参数显式路径 > 注册表卸载记录(WG 安装器/Steam 均写入) > Steam libraryfolders.vdf(多库) > 常见默认路径

param(
    [string]$Explicit = '',
    [string]$Root = '',
    [switch]$LatestBin
)

$ErrorActionPreference = 'SilentlyContinue'

function Test-GameRoot($path) {
    return ($path -and (Test-Path -LiteralPath $path) -and (Test-Path -LiteralPath (Join-Path $path 'bin')))
}

function Get-UninstallRoots {
    $roots = @()
    $views = @('HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
               'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*')
    foreach ($view in $views) {
        foreach ($key in Get-ItemProperty $view) {
            $name = $key.DisplayName
            $pub  = $key.Publisher
            $loc  = $key.InstallLocation
            if ($name -like 'World_of_Warships*' -and $pub -eq 'Wargaming.net' -and $loc) {
                $roots += $loc
            }
        }
    }
    return $roots
}

function Get-SteamRoots {
    $roots = @()
    $steamPaths = @()
    $steamPaths += (Get-ItemProperty 'HKCU:\Software\Valve\Steam' -Name SteamPath).SteamPath
    $steamPaths += (Get-ItemProperty 'HKLM:\SOFTWARE\WOW6432Node\Valve\Steam' -Name InstallPath).InstallPath
    $steamPaths += (Get-ItemProperty 'HKLM:\SOFTWARE\Valve\Steam' -Name InstallPath).InstallPath
    $libFiles = @()
    foreach ($sp in $steamPaths) {
        if ($sp -and (Test-Path -LiteralPath $sp)) {
            $libFiles += (Join-Path $sp 'steamapps\libraryfolders.vdf')
        }
    }
    foreach ($vdf in ($libFiles | Select-Object -Unique)) {
        if (-not (Test-Path -LiteralPath $vdf)) { continue }
        $lines = Get-Content -LiteralPath $vdf
        foreach ($line in $lines) {
            # libraryfolders.vdf:  "path"  "D:\\SteamLibrary"  之类的键值行
            if ($line -match '"path"\s+"(.+)"') {
                $lib = $matches[1] -replace '\\\\', '\'
                $roots += (Join-Path $lib 'steamapps\common\World of Warships')
            }
        }
    }
    return $roots
}

function Get-DefaultRoots {
    return @('C:\Program Files (x86)\Steam\steamapps\common\World of Warships',
             'C:\Games\World_of_Warships',
             'D:\Games\World_of_Warships',
             'E:\Games\World_of_Warships')
}

# ---------- 模式 2: 给定 Root 取最新 bin ----------
if ($LatestBin -and $Root) {
    $bins = @(Get-ChildItem -LiteralPath (Join-Path $Root 'bin') -Directory |
              Where-Object { $_.Name -match '^\d+$' } |
              Sort-Object { [int64]$_.Name } -Descending)
    if ($bins.Count -gt 0) {
        [Console]::WriteLine($bins[0].FullName)
    }
    exit 0
}

# ---------- 模式 1: 输出候选游戏根 ----------
$candidates = @()
if ($Explicit) {
    $candidates += $Explicit
} else {
    $candidates += Get-UninstallRoots
    $candidates += Get-SteamRoots
    $candidates += Get-DefaultRoots
}
$seen = @{}
foreach ($c in $candidates) {
    if (-not $c) { continue }
    $norm = $c.TrimEnd('\')
    if ($seen.ContainsKey($norm.ToLowerInvariant())) { continue }
    $seen[$norm.ToLowerInvariant()] = $true
    if (Test-GameRoot $norm) {
        [Console]::WriteLine($norm)
    }
}
exit 0
