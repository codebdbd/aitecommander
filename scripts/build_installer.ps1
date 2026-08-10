param(
    [switch]$SkipPyInstaller
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$SpecPath = Join-Path $Root "installer\AiteCommander.iss"
$DistExe = Join-Path $Root "dist\AiteCommander\AiteCommander.exe"

if (-not $SkipPyInstaller) {
    $VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $VenvPython) {
        $Python = $VenvPython
    } else {
        $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
        if (-not $PythonCommand) {
            throw "Python not found. Create .venv or add python.exe to PATH."
        }
        $Python = $PythonCommand.Source
    }

    & $Python (Join-Path $PSScriptRoot "build.py")
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

if (-not (Test-Path -LiteralPath $DistExe)) {
    throw "PyInstaller output not found: $DistExe. Run python scripts/build.py first or omit -SkipPyInstaller."
}

$IsccCandidates = @(
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }

$Iscc = $IsccCandidates | Select-Object -First 1
if (-not $Iscc) {
    $Command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($Command) {
        $Iscc = $Command.Source
    }
}

if (-not $Iscc) {
    throw "Inno Setup compiler ISCC.exe not found. Install Inno Setup 6 or add ISCC.exe to PATH."
}

& $Iscc $SpecPath
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "Installer created in: $(Join-Path $Root 'dist\installer')"
