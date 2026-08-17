$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = if ($env:AVSCOPE_PYTHON) { $env:AVSCOPE_PYTHON } else { (Get-Command python -ErrorAction Stop).Source }
$outputDir = Join-Path $root "dist\sample-reports"
$tmpRoot = Join-Path $root "tmp"
New-Item -ItemType Directory -Force -Path $tmpRoot | Out-Null

$env:PYTHONPATH = $root
$env:TEMP = $tmpRoot
$env:TMP = $tmpRoot

& $python "$root\scripts\sample_reports.py" --root $root --output-dir $outputDir
Write-Host $outputDir
