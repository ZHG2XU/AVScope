$ErrorActionPreference = "Stop"

$root = "G:\AVScope"
$python = "E:\DevelopmentEnvironment\python\python.exe"
$outputDir = "G:\AVScope\dist\sample-reports"

$env:PYTHONPATH = $root
$env:TEMP = "G:\AVScope\tmp"
$env:TMP = "G:\AVScope\tmp"

& $python "$root\scripts\sample_reports.py" --root $root --output-dir $outputDir
Write-Host $outputDir
