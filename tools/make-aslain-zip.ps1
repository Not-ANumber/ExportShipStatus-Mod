param(
    [Parameter(Mandatory = $true)][string]$SourceDir,
    [Parameter(Mandatory = $true)][string]$OutFile
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

if (Test-Path -LiteralPath $OutFile) {
    Remove-Item -LiteralPath $OutFile -Force
}

$src = (Resolve-Path -LiteralPath $SourceDir).Path.TrimEnd('\')
$zip = [System.IO.Compression.ZipFile]::Open(
    $OutFile,
    [System.IO.Compression.ZipArchiveMode]::Create)
try {
    Get-ChildItem -LiteralPath $src -Recurse -File -Name | ForEach-Object {
        # -Name is already relative to $src. Do not slice FullName: on some
        # runners TEMP resolves to a short path while children report the long
        # form (or vice versa), which leaves a stray directory prefix in the zip.
        $rel = $_.Replace('\', '/')
        $full = Join-Path -Path $src -ChildPath $_
        [void][System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $zip, $full, $rel,
            [System.IO.Compression.CompressionLevel]::Optimal)
    }
}
finally {
    $zip.Dispose()
}
