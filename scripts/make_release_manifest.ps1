$ErrorActionPreference = "Stop"

$root = "G:\AVScope"
$python = "E:\DevelopmentEnvironment\python\python.exe"
$output = "G:\AVScope\dist\AVScope-release-manifest.json"

$env:PYTHONPATH = $root
$env:TEMP = "G:\AVScope\tmp"
$env:TMP = "G:\AVScope\tmp"

& $python "$root\scripts\release_manifest.py" --root $root --output $output
Write-Host $output
