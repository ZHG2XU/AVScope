$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = if ($env:AVSCOPE_PYTHON) { $env:AVSCOPE_PYTHON } else { (Get-Command python -ErrorAction Stop).Source }
$output = Join-Path $root "dist\AVScope-release-manifest.json"
$tmpRoot = Join-Path $root "tmp"
New-Item -ItemType Directory -Force -Path $tmpRoot | Out-Null

$env:PYTHONPATH = $root
$env:TEMP = $tmpRoot
$env:TMP = $tmpRoot

& $python "$root\scripts\release_manifest.py" --root $root --output $output
Write-Host $output
