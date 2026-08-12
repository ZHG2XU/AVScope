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
    $env:AVSCOPE_WINDOW_WIDTH = "1560"
    $env:AVSCOPE_WINDOW_HEIGHT = "940"
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

$compactScreenshot = "$output\compact-1120x720.png"
Remove-Item -LiteralPath $compactScreenshot -Force -ErrorAction SilentlyContinue
$env:AVSCOPE_THEME = "dark"
$env:AVSCOPE_WINDOW_WIDTH = "1120"
$env:AVSCOPE_WINDOW_HEIGHT = "720"
$env:AVSCOPE_START_TAB = "0"
$env:AVSCOPE_SCREENSHOT = $compactScreenshot
$compactProcess = Start-Process -FilePath $executable -ArgumentList $sample -WindowStyle Hidden -PassThru
if (-not $compactProcess.WaitForExit(10000)) {
    $compactProcess.Kill()
    throw "Qt compact layout smoke test timed out"
}
if (-not (Test-Path -LiteralPath $compactScreenshot)) {
    throw "Qt compact layout screenshot was not generated"
}
Remove-Item Env:\AVSCOPE_WINDOW_WIDTH, Env:\AVSCOPE_WINDOW_HEIGHT, Env:\AVSCOPE_START_TAB -ErrorAction SilentlyContinue
$env:AVSCOPE_WINDOW_WIDTH = "1560"
$env:AVSCOPE_WINDOW_HEIGHT = "940"

$timelineScreenshot = "$output\timeline-pcap.png"
Remove-Item -LiteralPath $timelineScreenshot -Force -ErrorAction SilentlyContinue
$env:AVSCOPE_THEME = "dark"
$env:AVSCOPE_START_TAB = "3"
$env:AVSCOPE_SCREENSHOT = $timelineScreenshot
$timelineProcess = Start-Process -FilePath $executable -ArgumentList "$root\samples\sample.pcap" -WindowStyle Hidden -PassThru
if (-not $timelineProcess.WaitForExit(10000)) {
    $timelineProcess.Kill()
    throw "Qt timeline smoke test timed out"
}
if (-not (Test-Path -LiteralPath $timelineScreenshot)) {
    throw "Qt timeline screenshot was not generated"
}
Remove-Item Env:\AVSCOPE_START_TAB -ErrorAction SilentlyContinue

$rawPcmScreenshot = "$output\raw-pcm.png"
$rawPcmJson = "$output\raw-pcm.json"
Remove-Item -LiteralPath $rawPcmScreenshot, $rawPcmJson -Force -ErrorAction SilentlyContinue
$env:AVSCOPE_RAW_SAMPLE_RATE = "8000"
$env:AVSCOPE_RAW_CHANNELS = "1"
$env:AVSCOPE_RAW_BITS = "16"
$env:AVSCOPE_RAW_ENDIAN = "little"
$env:AVSCOPE_START_TAB = "4"
$env:AVSCOPE_SCREENSHOT = $rawPcmScreenshot
$rawPcmProcess = Start-Process -FilePath $executable -ArgumentList "$root\samples\sample.pcm" -WindowStyle Hidden -PassThru
if (-not $rawPcmProcess.WaitForExit(10000)) {
    $rawPcmProcess.Kill()
    throw "Qt Raw PCM smoke test timed out"
}
if (-not (Test-Path -LiteralPath $rawPcmScreenshot)) {
    throw "Qt Raw PCM screenshot was not generated"
}
Copy-Item -LiteralPath "$root\tmp\qt-runtime\current-analysis.json" -Destination $rawPcmJson -Force

Remove-Item Env:\AVSCOPE_RAW_SAMPLE_RATE, Env:\AVSCOPE_RAW_CHANNELS, Env:\AVSCOPE_RAW_BITS, Env:\AVSCOPE_RAW_ENDIAN -ErrorAction SilentlyContinue
$rawYuvScreenshot = "$output\raw-yuv.png"
$rawYuvJson = "$output\raw-yuv.json"
Remove-Item -LiteralPath $rawYuvScreenshot, $rawYuvJson -Force -ErrorAction SilentlyContinue
$env:AVSCOPE_RAW_WIDTH = "64"
$env:AVSCOPE_RAW_HEIGHT = "48"
$env:AVSCOPE_RAW_PIXEL_FORMAT = "yuv420p"
$env:AVSCOPE_RAW_FPS = "30"
$env:AVSCOPE_SCREENSHOT = $rawYuvScreenshot
$rawYuvProcess = Start-Process -FilePath $executable -ArgumentList "$root\samples\sample.yuv" -WindowStyle Hidden -PassThru
if (-not $rawYuvProcess.WaitForExit(10000)) {
    $rawYuvProcess.Kill()
    throw "Qt Raw YUV smoke test timed out"
}
if (-not (Test-Path -LiteralPath $rawYuvScreenshot)) {
    throw "Qt Raw YUV screenshot was not generated"
}
Copy-Item -LiteralPath "$root\tmp\qt-runtime\current-analysis.json" -Destination $rawYuvJson -Force

Remove-Item Env:\AVSCOPE_RAW_WIDTH, Env:\AVSCOPE_RAW_HEIGHT, Env:\AVSCOPE_RAW_PIXEL_FORMAT, Env:\AVSCOPE_RAW_FPS, Env:\AVSCOPE_START_TAB -ErrorAction SilentlyContinue
$compareScreenshot = "$output\compare-protocol.png"
$compareJson = "$output\compare-protocol.json"
Remove-Item -LiteralPath $compareScreenshot, $compareJson -Force -ErrorAction SilentlyContinue
$env:AVSCOPE_COMPARE_MODE = "protocol"
$env:AVSCOPE_COMPARE_PATH = "$root\samples\sample_changed.mp4"
$env:AVSCOPE_SCREENSHOT = $compareScreenshot
$compareProcess = Start-Process -FilePath $executable -ArgumentList "$root\samples\sample.mp4" -WindowStyle Hidden -PassThru
if (-not $compareProcess.WaitForExit(10000)) {
    $compareProcess.Kill()
    throw "Qt protocol compare smoke test timed out"
}
if (-not (Test-Path -LiteralPath $compareScreenshot)) {
    throw "Qt protocol compare screenshot was not generated"
}
Copy-Item -LiteralPath "$root\tmp\qt-runtime\compare-protocol.json" -Destination $compareJson -Force
Remove-Item Env:\AVSCOPE_COMPARE_MODE, Env:\AVSCOPE_COMPARE_PATH -ErrorAction SilentlyContinue
Remove-Item Env:\AVSCOPE_WINDOW_WIDTH, Env:\AVSCOPE_WINDOW_HEIGHT -ErrorAction SilentlyContinue

$env:PYTHONPATH = $root
& "E:\DevelopmentEnvironment\python\python.exe" -c "from pathlib import Path; from avscope.ffmpeg_preview import png_dimensions; paths=[Path(r'$output/dark.png'),Path(r'$output/light.png'),Path(r'$output/timeline-pcap.png'),Path(r'$output/raw-pcm.png'),Path(r'$output/raw-yuv.png'),Path(r'$output/compare-protocol.png')]; dims=[png_dimensions(p) for p in paths]; assert len(set(dims)) == 1, dims; width,height=dims[0]; assert width >= 1560 and height >= 940, dims; assert abs(width / height - 1560 / 940) < 0.01, dims; assert all(p.stat().st_size > 50000 for p in paths), [(p.name,p.stat().st_size) for p in paths]; compact=Path(r'$compactScreenshot'); compact_dims=png_dimensions(compact); assert compact_dims == (1680,1080), compact_dims; assert compact.stat().st_size > 40000; settings=Path(r'$root/data/qt-settings.ini'); assert settings.exists() and settings.stat().st_size > 0; print({'screenshots': [str(p) for p in paths], 'dimensions': dims, 'compact': {'path': str(compact), 'dimensions': compact_dims}, 'dpi_scale': round(width / 1560, 2), 'settings': str(settings)})"
if ($LASTEXITCODE -ne 0) { throw "Qt screenshot validation failed" }

& "E:\DevelopmentEnvironment\python\python.exe" -c "import json; from pathlib import Path; document=json.loads(Path(r'$root/tmp/qt-runtime/current-analysis.json').read_text(encoding='utf-8')); root=document['root']; assert root['children'] and root['children'][0]['fields']; pcm=json.loads(Path(r'$rawPcmJson').read_text(encoding='utf-8'))['media']['summary']; assert (pcm['sample_rate'],pcm['channels'],pcm['bits_per_sample'],pcm['endian']) == (8000,1,16,'little'), pcm; yuv=json.loads(Path(r'$rawYuvJson').read_text(encoding='utf-8'))['media']['summary']; assert (yuv['width'],yuv['height'],yuv['pixel_format'],yuv['fps']) == (64,48,'yuv420p',30.0), yuv; compare=json.loads(Path(r'$compareJson').read_text(encoding='utf-8')); assert len(compare['added']) == 1 and len(compare['changed']) >= 1, compare; print({'nodes': len(root['children']), 'first_fields': len(root['children'][0]['fields']), 'raw_pcm': {k:pcm[k] for k in ('sample_rate','channels','bits_per_sample','endian')}, 'raw_yuv': {k:yuv[k] for k in ('width','height','pixel_format','fps')}, 'protocol_compare': {k:len(compare[k]) for k in ('added','removed','changed')}})"
if ($LASTEXITCODE -ne 0) { throw "Qt protocol tree data contract is incomplete" }

& "E:\DevelopmentEnvironment\python\python.exe" -c "import json; from pathlib import Path; pcm=json.loads(Path(r'$rawPcmJson').read_text(encoding='utf-8'))['media']['summary']; yuv=json.loads(Path(r'$rawYuvJson').read_text(encoding='utf-8'))['media']['summary']; assert pcm['waveform']['energy']['peak_level'] > 0.5; preview=Path(yuv['yuv_preview']['path']); assert yuv['yuv_preview']['available'] and preview.exists() and preview.stat().st_size > 100; source=Path(r'$root/qt/src/MainWindow.cpp').read_text(encoding='utf-8'); assert 'waitForFinished' not in source; print({'pcm_peak': pcm['waveform']['energy']['peak_level'], 'yuv_preview': str(preview), 'async_tasks': True})"
if ($LASTEXITCODE -ne 0) { throw "Qt media visualization or asynchronous task validation failed" }

Write-Output "Qt UI validation OK"
