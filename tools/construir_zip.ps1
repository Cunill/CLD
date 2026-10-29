<#
.SYNOPSIS
  Construeix el ZIP portable PassiMaker-<versió>-win64.zip (bloc B12).
  PyInstaller en mode carpeta (packaging/PassiMaker.spec): PassiMaker.exe, LLEGEIX-ME.txt i bin/ (Python, Qt,
  les biblioteques i FFmpeg). Falla si el ZIP passa de 250 MB.
  Ús: pwsh tools/construir_zip.ps1 [-Sortida dist]
  A Linux (només per provar l'especificació) fa servir l'FFmpeg del sistema i el ZIP es diu ...-linux64.zip.
#>
param(
    [string]$Sortida = 'dist'
)
$ErrorActionPreference = 'Stop'

$MaxMB = 250
$Name = 'PassiMaker'
$Root = Split-Path -Parent $PSScriptRoot
$Platform = if ($IsWindows) { 'win64' } else { 'linux64' }
$Exe = if ($IsWindows) { "$Name.exe" } else { $Name }
$ExeSuffix = if ($IsWindows) { '.exe' } else { '' }

function Invoke-Native {
    param([string]$What, [scriptblock]$Command)
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$What ha fallat (codi $LASTEXITCODE)" }
}

Push-Location $Root
try {
    if ($IsWindows) {
        & (Join-Path $PSScriptRoot 'obtenir_ffmpeg.ps1')
    }
    else {
        Invoke-Native 'Comprovar FFmpeg' { bash (Join-Path $PSScriptRoot 'obtenir_ffmpeg.sh') }
    }
    Invoke-Native 'uv sync' { uv sync --locked --group packaging }
    $Version = (uv run --group packaging python -c 'import passimaker; print(passimaker.__version__)' 2>$null |
        Select-Object -Last 1).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $Version) { throw 'No es pot llegir la versió de passimaker' }
    $Folder = "$Name-$Version"
    Write-Host "Construint $Folder ($Platform)..."

    $Build = Join-Path $Root 'build'
    $Dist = Join-Path $Build 'dist'
    if (Test-Path $Dist) { Remove-Item -Recurse -Force $Dist }
    Invoke-Native 'PyInstaller' {
        uv run --group packaging pyinstaller packaging/PassiMaker.spec --noconfirm --clean `
            --distpath $Dist --workpath (Join-Path $Build 'pyinstaller')
    }

    $App = Join-Path $Dist $Folder
    Rename-Item (Join-Path $Dist $Name) $Folder
    $Required = @($Exe)
    if ($IsWindows) {
        # PortAudio, for the sound of the preview (B13): bin/_sounddevice_data/portaudio-binaries.
        $Required += @("bin/ffmpeg$ExeSuffix", "bin/ffprobe$ExeSuffix", 'bin/_sounddevice_data/portaudio-binaries',
            'bin/deno.exe', 'bin/yt_dlp_ejs/yt/solver/core.min.js', 'bin/yt_dlp_ejs/yt/solver/lib.min.js',
            'bin/soundcard/mediafoundation.py.h')
    }
    foreach ($File in $Required) {
        if (-not (Test-Path (Join-Path $App $File))) { throw "Falta $File a la carpeta del programa" }
    }
    Copy-Item (Join-Path $Root 'packaging/LLEGEIX-ME.txt') $App

    $OutDir = if ([System.IO.Path]::IsPathRooted($Sortida)) { $Sortida } else { Join-Path $Root $Sortida }
    New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
    $Zip = Join-Path $OutDir "$Folder-$Platform.zip"
    if (Test-Path $Zip) { Remove-Item -Force $Zip }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::CreateFromDirectory(
        $App, $Zip, [System.IO.Compression.CompressionLevel]::Optimal, $true)

    $FolderMB = (Get-ChildItem -Recurse -File $App | Measure-Object -Sum Length).Sum / 1MB
    $ZipMB = (Get-Item $Zip).Length / 1MB
    Write-Host ('Carpeta: {0:N0} MB · ZIP: {1:N0} MB (màxim {2} MB)' -f $FolderMB, $ZipMB, $MaxMB)
    Write-Host 'Els 15 fitxers més grans:'
    Get-ChildItem -Recurse -File $App | Sort-Object Length -Descending | Select-Object -First 15 |
        ForEach-Object { Write-Host ('  {0,6:N1} MB  {1}' -f ($_.Length / 1MB), [System.IO.Path]::GetRelativePath($App, $_.FullName)) }
    if ($ZipMB -gt $MaxMB) { throw ('El ZIP fa {0:N0} MB: el màxim és {1} MB' -f $ZipMB, $MaxMB) }
    Write-Host "ZIP creat: $Zip"
    if ($env:GITHUB_OUTPUT) {
        Add-Content -Path $env:GITHUB_OUTPUT -Value "zip=$Zip"
        Add-Content -Path $env:GITHUB_OUTPUT -Value "nom=$Folder-$Platform"
    }
}
finally {
    Pop-Location
}
