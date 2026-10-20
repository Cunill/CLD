<#
.SYNOPSIS
  Descarrega FFmpeg (versió fixada) a vendor/ffmpeg/bin i en verifica la suma SHA-256.
  Si ja hi és la mateixa versió, no fa res.
  Ús: pwsh tools/obtenir_ffmpeg.ps1
#>
$ErrorActionPreference = 'Stop'

$Version = '7.1.1'
$Url = "https://github.com/GyanD/codexffmpeg/releases/download/$Version/ffmpeg-$Version-essentials_build.zip"
$Sha256 = '04861D3339C5EBE38B56C19A15CF2C0CC97F5DE4FA8910E4D47E5E6404E4A2D4'

$Root = Split-Path -Parent $PSScriptRoot
$Vendor = Join-Path $Root 'vendor/ffmpeg'
$Bin = Join-Path $Vendor 'bin'
$VersionFile = Join-Path $Vendor 'VERSION'

if ((Test-Path $VersionFile) -and ((Get-Content $VersionFile -Raw).Trim() -eq $Version) -and
    (Test-Path (Join-Path $Bin 'ffmpeg.exe')) -and (Test-Path (Join-Path $Bin 'ffprobe.exe'))) {
    Write-Host "FFmpeg $Version ja és a $Bin"
    exit 0
}

$Temp = Join-Path ([System.IO.Path]::GetTempPath()) ("passi-ffmpeg-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $Temp | Out-Null
try {
    $Zip = Join-Path $Temp 'ffmpeg.zip'
    Write-Host "Descarregant FFmpeg $Version..."
    $ProgressPreference = 'SilentlyContinue'
    Invoke-WebRequest -Uri $Url -OutFile $Zip
    $Actual = (Get-FileHash -Algorithm SHA256 $Zip).Hash
    if ($Actual -ne $Sha256) {
        throw "La suma SHA-256 no coincideix: esperada $Sha256, obtinguda $Actual"
    }
    Expand-Archive -Path $Zip -DestinationPath $Temp
    $Source = Join-Path $Temp "ffmpeg-$Version-essentials_build"
    if (Test-Path $Vendor) { Remove-Item -Recurse -Force $Vendor }
    New-Item -ItemType Directory -Path $Bin | Out-Null
    Copy-Item (Join-Path $Source 'bin/ffmpeg.exe') $Bin
    Copy-Item (Join-Path $Source 'bin/ffprobe.exe') $Bin
    Copy-Item (Join-Path $Source 'LICENSE') (Join-Path $Vendor 'LICENSE.txt')
    Set-Content -Path $VersionFile -Value $Version -NoNewline
    Write-Host "FFmpeg $Version instal·lat a $Bin"
}
finally {
    Remove-Item -Recurse -Force $Temp -ErrorAction SilentlyContinue
}
