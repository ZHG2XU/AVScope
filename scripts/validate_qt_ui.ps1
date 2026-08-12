$ErrorActionPreference = "Stop"

$root = "G:\AVScope"
$executable = "$root\build\qt6\bin\AVScope.exe"
$sample = "$root\samples\sample.aac"
$output = "$root\tmp\qt-ui-validation"

& "$root\scripts\build_qt.ps1"
if ($LASTEXITCODE -ne 0) { throw "Qt build validation failed" }

New-Item -ItemType Directory -Force -Path $output | Out-Null
$env:AVSCOPE_ROOT = $root
$env:AVSCOPE_PYTHON = "E:\DevelopmentEnvironment\python\python.exe"
$env:QT_QPA_PLATFORM = "windows"
$env:PATH = "E:\QT\6.9.0\mingw_64\bin;E:\QT\Tools\mingw1310_64\bin;$env:PATH"
$env:TEMP = "$root\tmp"
$env:TMP = "$root\tmp"

foreach ($theme in @("dark", "light")) {
    $screenshot = "$output\$theme.png"
    Remove-Item -LiteralPath $screenshot -Force -ErrorAction SilentlyContinue
    $env:AVSCOPE_THEME = $theme
    $env:AVSCOPE_SCREENSHOT = $screenshot
    $process = Start-Process -FilePath $executable -ArgumentList $sample -WindowStyle Hidden -PassThru
    if (-not $process.WaitForExit(10000)) {
        $process.Kill()
        throw "Qt $theme theme smoke test timed out"
    }
    if (-not (Test-Path -LiteralPath $screenshot)) {
        throw "Qt $theme theme screenshot was not generated"
    }
}

$env:PYTHONPATH = $root
& "E:\DevelopmentEnvironment\python\python.exe" -c "from pathlib import Path; from avscope.ffmpeg_preview import png_dimensions; paths=[Path(r'$output/dark.png'),Path(r'$output/light.png')]; dims=[png_dimensions(p) for p in paths]; assert dims[0] == dims[1], dims; width,height=dims[0]; assert width >= 1560 and height >= 940, dims; assert abs(width / height - 1560 / 940) < 0.01, dims; assert all(p.stat().st_size > 50000 for p in paths); print({'screenshots': [str(p) for p in paths], 'dimensions': dims, 'dpi_scale': round(width / 1560, 2)})"
if ($LASTEXITCODE -ne 0) { throw "Qt screenshot validation failed" }

& "E:\DevelopmentEnvironment\python\python.exe" -c "import json; from pathlib import Path; document=json.loads(Path(r'$root/tmp/qt-runtime/current-analysis.json').read_text(encoding='utf-8')); root=document['root']; assert root['children'] and root['children'][0]['fields']; print({'nodes': len(root['children']), 'first_fields': len(root['children'][0]['fields'])})"
if ($LASTEXITCODE -ne 0) { throw "Qt protocol tree data contract is incomplete" }

Write-Output "Qt UI validation OK"
