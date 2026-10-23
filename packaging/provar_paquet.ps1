<#
.SYNOPSIS
  Prova el ZIP portable com ho faria un usuari (bloc B12; la CI l'executa en un Windows sense Python).
  1. Descomprimeix el ZIP en una carpeta amb accents i espais.
  2. PassiMaker.exe --autoprova: exporta un vídeo de 5 s; ha d'acabar amb el codi 0.
  3. Obre la finestra tres vegades (buida, buida, amb el projecte de l'autoprova com a argument) i mesura quant
     triga a aparèixer; la tanca com ho faria l'usuari. Màxim: 4 s (la primera, en fred, només s'informa).
  4. Comprova que el programa no ha escrit res a la seva carpeta i sí a %APPDATA% i %LOCALAPPDATA%.
  Ús: pwsh packaging/provar_paquet.ps1 -Zip dist/PassiMaker-<versió>-win64.zip [-Informes carpeta]
#>
param(
    [Parameter(Mandatory)] [string]$Zip,
    [string]$Informes = ''
)
$ErrorActionPreference = 'Stop'

$MaxWindowS = 4.0
$WindowTimeoutS = 60
$TitleTimeoutS = 10
$Exe = if ($IsWindows) { 'PassiMaker.exe' } else { 'PassiMaker' }

$Work = Join-Path ([System.IO.Path]::GetTempPath()) ("Prova PassiMaker àèòç " + [guid]::NewGuid().ToString('N').Substring(0, 8))
if (-not $Informes) { $Informes = Join-Path $Work 'informes' }
$Informes = [System.IO.Path]::GetFullPath($Informes, (Get-Location).Path)  # the program runs in $Work
New-Item -ItemType Directory -Force -Path $Work, $Informes | Out-Null
$Failures = [System.Collections.Generic.List[string]]::new()

function Get-FolderState([string]$Path) {
    # Folders by name only: Windows updates their dates by itself after the extraction.
    Get-ChildItem -Recurse -Force $Path | ForEach-Object {
        $Name = [System.IO.Path]::GetRelativePath($Path, $_.FullName)
        if ($_.PSIsContainer) { "$Name\" } else { '{0}|{1}|{2:o}' -f $Name, $_.Length, $_.LastWriteTimeUtc }
    } | Sort-Object
}

function Wait-Window([System.Diagnostics.Process]$Process) {
    $Clock = [System.Diagnostics.Stopwatch]::StartNew()
    while ($Clock.Elapsed.TotalSeconds -lt $WindowTimeoutS) {
        if ($Process.HasExited) { throw "El programa s'ha tancat abans d'obrir la finestra (codi $($Process.ExitCode))" }
        $Process.Refresh()
        if ($Process.MainWindowHandle -ne [IntPtr]::Zero) { return $Clock.Elapsed.TotalSeconds }
        Start-Sleep -Milliseconds 50
    }
    throw "La finestra no s'ha obert en $WindowTimeoutS s"
}

function Test-Window([string]$App, [string]$Label, [string[]]$Arguments, [string]$Title, [bool]$Enforce) {
    $Options = @{ FilePath = (Join-Path $App $Exe); PassThru = $true; WorkingDirectory = $Work }
    if ($Arguments) { $Options.ArgumentList = $Arguments }
    $Process = Start-Process @Options
    try {
        $Seconds = Wait-Window $Process
        if ($Title) {
            # The project is opened just after the window appears: wait for its name in the title.
            $Clock = [System.Diagnostics.Stopwatch]::StartNew()
            while ($Clock.Elapsed.TotalSeconds -lt $TitleTimeoutS -and $Process.MainWindowTitle -notlike "*$Title*") {
                Start-Sleep -Milliseconds 100
                $Process.Refresh()
            }
        }
        $Process.Refresh()
        $Line = ('{0}: la finestra s''obre en {1:N2} s ("{2}")' -f $Label, $Seconds, $Process.MainWindowTitle)
        Add-Content -Path (Join-Path $Informes 'finestra.txt') -Value $Line -Encoding utf8
        Write-Host ('  {0}: la finestra s''obre en {1:N2} s ("{2}")' -f $Label, $Seconds, $Process.MainWindowTitle)
        if ($Enforce -and $Seconds -gt $MaxWindowS) {
            $Failures.Add(('{0}: la finestra triga {1:N2} s (màxim {2} s)' -f $Label, $Seconds, $MaxWindowS))
        }
        if ($Title -and $Process.MainWindowTitle -notlike "*$Title*") {
            $Failures.Add("${Label}: el títol és ""$($Process.MainWindowTitle)"", sense ""$Title""")
        }
        Start-Sleep -Milliseconds 500
        [void]$Process.CloseMainWindow()
        if (-not $Process.WaitForExit(20000)) { throw "${Label}: el programa no es tanca en 20 s" }
        if ($Process.ExitCode -ne 0) { $Failures.Add("${Label}: en tancar, codi de sortida $($Process.ExitCode)") }
    }
    finally {
        if (-not $Process.HasExited) { $Process.Kill() }
    }
}

try {
    Write-Host "Descomprimint $Zip a $Work"
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::ExtractToDirectory((Resolve-Path $Zip).Path, $Work)
    $App = Get-ChildItem -Directory $Work | Where-Object Name -like 'PassiMaker-*' | Select-Object -First 1
    if (-not $App) { throw 'El ZIP no conté cap carpeta PassiMaker-<versió>' }
    $App = $App.FullName
    if (-not $IsWindows) { & chmod +x (Join-Path $App $Exe) }
    $Before = Get-FolderState $App

    Write-Host 'Autoprova...'
    $Kept = Join-Path $Work 'autoprova'
    $Report = Join-Path $Informes 'autoprova.txt'
    $Clock = [System.Diagnostics.Stopwatch]::StartNew()
    $SelfTest = Start-Process -FilePath (Join-Path $App $Exe) -Wait -PassThru -WorkingDirectory $Work `
        -ArgumentList @('--autoprova', '--conservar', """$Kept""", '--informe', """$Report""")
    Write-Host ('  Codi de sortida {0} en {1:N1} s' -f $SelfTest.ExitCode, $Clock.Elapsed.TotalSeconds)
    if (Test-Path $Report) {
        Get-Content $Report -Encoding utf8 | Where-Object { $_ -notlike 'Exportant*' } | ForEach-Object { Write-Host "  | $_" }
    }
    if ($SelfTest.ExitCode -ne 0) { $Failures.Add("L'autoprova acaba amb el codi $($SelfTest.ExitCode)") }
    $Project = Join-Path $Kept 'autoprova.pmk'

    if ($IsWindows) {
        Write-Host 'Finestra...'
        Test-Window $App 'Primera obertura (en fred)' @() '' $false
        Test-Window $App 'Segona obertura' @() '' $true
        if (Test-Path $Project) {
            Test-Window $App 'Amb el projecte com a argument' @("""$Project""") 'autoprova' $true
        }
        else {
            $Failures.Add("No hi ha el projecte de l'autoprova per obrir-lo amb la finestra")
        }
    }
    else {
        Write-Host 'Finestra: només es prova a Windows'
    }

    Write-Host "Carpetes de l'usuari..."
    $After = Get-FolderState $App
    $Changed = Compare-Object $Before $After
    if ($Changed) {
        $Failures.Add('El programa ha escrit a la seva carpeta: ' + (($Changed | ForEach-Object InputObject) -join '; '))
    }
    else {
        Write-Host "  La carpeta del programa no ha canviat"
    }
    if ($IsWindows) {
        $Cache = Join-Path $env:LOCALAPPDATA 'PassiMaker'
        $Settings = Join-Path $env:APPDATA 'PassiMaker'
        foreach ($Place in @($Cache, $Settings)) {
            if (Test-Path $Place) {
                Write-Host "  $Place"
                Get-ChildItem -Recurse -Force $Place -Depth 1 | ForEach-Object { Write-Host "    $($_.FullName.Substring($Place.Length))" }
            }
            else {
                $Failures.Add("No s'ha creat $Place")
            }
        }
        # B15: el registre d'errors es crea en obrir la finestra.
        $Log = Join-Path $Cache 'logs\passimaker.log'
        if (Test-Path $Log) {
            Write-Host "  Registre: $Log"
        }
        else {
            $Failures.Add("No s'ha creat el registre $Log")
        }
    }

    if ($Failures.Count) {
        $Failures | ForEach-Object { Write-Host "ERROR: $_" }
        exit 1
    }
    Write-Host 'Paquet correcte'
    exit 0
}
finally {
    Remove-Item -Recurse -Force $Work -ErrorAction SilentlyContinue
}
