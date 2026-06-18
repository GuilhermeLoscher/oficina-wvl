$ErrorActionPreference = "Stop"

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$bundledPython = Join-Path $here "..\_desktop_source\source_v2\WVL orçamentos\.venv\Scripts\python.exe"

if (Test-Path -LiteralPath $bundledPython) {
    & $bundledPython (Join-Path $here "app.py")
    exit $LASTEXITCODE
}

& python (Join-Path $here "app.py")
