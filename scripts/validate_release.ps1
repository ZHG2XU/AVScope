$ErrorActionPreference = "Stop"

$root = "G:\AVScope"
$python = "E:\DevelopmentEnvironment\python\python.exe"
$setup = "G:\AVScope\dist\AVScope-Setup.exe"
$appExe = "G:\AVScope\dist\AVScope\AVScope.exe"
$ffprobe = "G:\AVScope\dist\AVScope\_internal\ffprobe.exe"
$ffmpeg = "G:\AVScope\dist\AVScope\_internal\ffmpeg.exe"
$pluginTemplate = "G:\AVScope\dist\AVScope\_internal\plugins\demo_magic.json"
$portableZip = "G:\AVScope\dist\AVScope-portable-win-x64.zip"
$sourceZip = "G:\AVScope\dist\AVScope-portable-source.zip"
$manifestPath = "G:\AVScope\dist\AVScope-release-manifest.json"
$validationReportPath = "G:\AVScope\dist\AVScope-validation-report.md"
$sampleReportDir = "G:\AVScope\dist\sample-reports"
$sampleWavHtml = "$sampleReportDir\sample_wav_report.html"
$sampleWavJson = "$sampleReportDir\sample_wav_report.json"
$sampleWavCsv = "$sampleReportDir\sample_wav_report.csv"
$sampleMp4Html = "$sampleReportDir\sample_mp4_report.html"
$sampleMp4Json = "$sampleReportDir\sample_mp4_report.json"
$sampleProtocolCompare = "$sampleReportDir\sample_protocol_compare.json"
$sampleFrameCompare = "$sampleReportDir\sample_frame_compare.json"
$installDir = "G:\AVScopeInstalled\ValidationSmoke-$([DateTime]::Now.ToString('yyyyMMddHHmmss'))"

$env:PYTHONPATH = $root
$env:TEMP = "G:\AVScope\tmp"
$env:TMP = "G:\AVScope\tmp"

Write-Host "== AVScope release validation =="
Write-Host "Root: $root"

Write-Host "== Unit tests =="
& $python -m unittest discover -s "$root\tests" -v

Write-Host "== Sample reports =="
PowerShell -ExecutionPolicy Bypass -File "$root\scripts\make_sample_reports.ps1"
PowerShell -ExecutionPolicy Bypass -File "$root\scripts\make_release_manifest.ps1"
Write-Host "Sample reports OK"

Write-Host "== Required artifacts =="
$artifacts = @(
    $appExe,
    $ffprobe,
    $ffmpeg,
    $pluginTemplate,
    $setup,
    $portableZip,
    $sourceZip,
    $manifestPath,
    $sampleWavHtml,
    $sampleWavJson,
    $sampleWavCsv,
    $sampleMp4Html,
    $sampleMp4Json,
    $sampleProtocolCompare,
    $sampleFrameCompare
)
foreach ($artifact in $artifacts) {
    if (-not (Test-Path $artifact)) {
        throw "Missing artifact: $artifact"
    }
    $item = Get-Item $artifact
    if ($item.Length -le 0) {
        throw "Empty artifact: $artifact"
    }
    Write-Host "$($item.FullName) $($item.Length) bytes"
}

Write-Host "== Release manifest =="
$manifest = Get-Content -Path $manifestPath -Raw | ConvertFrom-Json
if ($manifest.manifest_type -ne "AVScope Release Manifest") {
    throw "Unexpected manifest type: $($manifest.manifest_type)"
}
$expectedManifestEntries = @(
    "dist\AVScope\AVScope.exe",
    "dist\AVScope\_internal\ffprobe.exe",
    "dist\AVScope\_internal\ffmpeg.exe",
    "dist\AVScope\_internal\plugins\demo_magic.json",
    "dist\AVScope-Setup.exe",
    "dist\AVScope-portable-win-x64.zip",
    "dist\AVScope-portable-source.zip",
    "dist\sample-reports\sample_wav_report.html",
    "dist\sample-reports\sample_wav_report.json",
    "dist\sample-reports\sample_wav_report.csv",
    "dist\sample-reports\sample_mp4_report.html",
    "dist\sample-reports\sample_mp4_report.json",
    "dist\sample-reports\sample_protocol_compare.json",
    "dist\sample-reports\sample_frame_compare.json"
)
$manifestEntries = @($manifest.artifacts | ForEach-Object { [string]$_.relative_path })
foreach ($entry in $expectedManifestEntries) {
    if ($manifestEntries -notcontains $entry) {
        throw "Manifest missing expected artifact: $entry"
    }
}
foreach ($artifact in $manifest.artifacts) {
    $path = [string]$artifact.path
    if (-not (Test-Path $path)) {
        throw "Manifest artifact missing: $path"
    }
    $item = Get-Item $path
    if ($item.Length -ne [Int64]$artifact.size) {
        throw "Manifest size mismatch: $path"
    }
    $hash = (Get-FileHash -Algorithm SHA256 -Path $path).Hash.ToLowerInvariant()
    if ($hash -ne [string]$artifact.sha256) {
        throw "Manifest hash mismatch: $path"
    }
}
Write-Host "Release manifest OK"

Write-Host "== Mojibake scan =="
$bad = @(
    [string][char]0x951B,
    [string][char]0x93B5,
    [string][char]0x93C3,
    [string][char]0x9357,
    [string][char]0x7487,
    [string][char]0x6FEF,
    [string][char]0x9225,
    [string][char]0x9239,
    [string][char]0xFFFD
)
$sourceFiles = Get-ChildItem -Path "$root\avscope" -Recurse -Filter "*.py" -File | ForEach-Object { $_.FullName }
foreach ($file in $sourceFiles) {
    $text = [System.IO.File]::ReadAllText($file, [System.Text.Encoding]::UTF8)
    foreach ($fragment in $bad) {
        if ($text.Contains($fragment)) {
            throw "Mojibake fragment '$fragment' found in $file"
        }
    }
}
Write-Host "Mojibake scan OK"

Write-Host "== Waveform preview smoke =="
$waveformCheck = @'
from pathlib import Path
from avscope.analyzer import Analyzer
from avscope.waveform import build_waveform_preview
source = Path("G:/AVScope/samples/sample.wav")
analysis = Analyzer().analyze(source)
result = build_waveform_preview(source, analysis.media.format_name, analysis.media.summary, output_dir=Path("G:/AVScope/tmp/waveform-preview-validation"))
print(result)
if not result.get("available") or not result.get("path"):
    raise SystemExit("Waveform preview was not generated")
if result.get("width") != 720 or result.get("height") != 180:
    raise SystemExit(f"Unexpected waveform preview size: {result}")
'@
$waveformCheck | & $python -
Write-Host "Waveform preview smoke OK"

Write-Host "== Video preview smoke =="
$previewSmokeDir = "G:\AVScope\tmp\preview-smoke-validation"
New-Item -ItemType Directory -Force -Path $previewSmokeDir | Out-Null
$previewSource = "$previewSmokeDir\source.mp4"
& $ffmpeg -hide_banner -v error -y -f lavfi -i "testsrc=size=160x90:rate=1:duration=2" -pix_fmt yuv420p $previewSource
$env:AVSCOPE_FFMPEG = $ffmpeg
$previewCheck = @'
from pathlib import Path
from avscope.ffmpeg_preview import build_video_preview
source = Path("G:/AVScope/tmp/preview-smoke-validation/source.mp4")
outputs = [
    build_video_preview(source, output_dir=Path("G:/AVScope/tmp/preview-smoke-validation"), position_seconds=0),
    build_video_preview(source, output_dir=Path("G:/AVScope/tmp/preview-smoke-validation"), position_seconds=1),
]
print(outputs)
for result in outputs:
    if not result.get("available") or not result.get("path"):
        raise SystemExit("Video preview PNG was not generated")
    if result.get("width") != 160 or result.get("height") != 90:
        raise SystemExit(f"Unexpected preview size: {result}")
if outputs[0].get("path") == outputs[1].get("path"):
    raise SystemExit("Preview seek did not produce a distinct cache path")
'@
$previewCheck | & $python -
Remove-Item Env:\AVSCOPE_FFMPEG -ErrorAction SilentlyContinue
Write-Host "Video preview smoke OK"

Write-Host "== Raw YUV preview smoke =="
$yuvCheck = @'
from pathlib import Path
from avscope.yuv_preview import build_yuv_preview
source = Path("G:/AVScope/samples/sample.yuv")
result = build_yuv_preview(source, 64, 48, "yuv420p", output_dir=Path("G:/AVScope/tmp/yuv-preview-validation"))
print(result)
if not result.get("available") or not result.get("path"):
    raise SystemExit("Raw YUV preview was not generated")
if result.get("width") != 64 or result.get("height") != 48:
    raise SystemExit(f"Unexpected Raw YUV preview size: {result}")
'@
$yuvCheck | & $python -
Write-Host "Raw YUV preview smoke OK"

Write-Host "== Frame compare smoke =="
$frameCompareCheck = @'
from pathlib import Path
from avscope.compare import compare_frames
source = Path("G:/AVScope/samples/sample.aac")
result = compare_frames(source, source)
print(result)
if result.get("left_frames", 0) <= 0 or result.get("right_frames", 0) <= 0:
    raise SystemExit("Frame compare did not parse AAC frames")
if result.get("added") or result.get("removed") or result.get("changed"):
    raise SystemExit(f"Unexpected frame compare diff: {result}")
'@
$frameCompareCheck | & $python -
Write-Host "Frame compare smoke OK"

Write-Host "== Media extraction smoke =="
$extractSmokeDir = "G:\AVScope\tmp\extract-smoke-validation"
New-Item -ItemType Directory -Force -Path $extractSmokeDir | Out-Null
$extractSource = "$extractSmokeDir\source.mp4"
& $ffmpeg -hide_banner -v error -y -f lavfi -i "testsrc=size=160x90:rate=1" -f lavfi -i "sine=frequency=1000:duration=1" -shortest -pix_fmt yuv420p $extractSource
$env:AVSCOPE_FFMPEG = $ffmpeg
$extractCheck = @'
from pathlib import Path
from avscope.extract import extract_media_stream
source = Path("G:/AVScope/tmp/extract-smoke-validation/source.mp4")
outputs = [
    extract_media_stream(source, Path("G:/AVScope/tmp/extract-smoke-validation/audio.aac"), "audio"),
    extract_media_stream(source, Path("G:/AVScope/tmp/extract-smoke-validation/video.h264"), "video"),
    extract_media_stream(source, Path("G:/AVScope/tmp/extract-smoke-validation/keyframe.png"), "keyframe"),
]
print(outputs)
for item in outputs:
    if item.get("error") or not item.get("output") or item.get("size", 0) <= 0:
        raise SystemExit(f"Media extraction failed: {item}")
'@
$extractCheck | & $python -
Remove-Item Env:\AVSCOPE_FFMPEG -ErrorAction SilentlyContinue
Write-Host "Media extraction smoke OK"

Write-Host "== Path constraint scan =="
$scanTargets = @("$root\avscope", "$root\packaging", "$root\plugins", "$root\scripts")
$scanFiles = Get-ChildItem -Path $scanTargets -Recurse -File |
    Where-Object { $_.FullName -ne "$root\scripts\validate_release.ps1" }
$matches = Select-String -Path $scanFiles.FullName -Pattern "C:\\|PROGRAMFILES|DESKTOP|SMPROGRAMS" -ErrorAction SilentlyContinue
if ($matches) {
    $matches | ForEach-Object { Write-Host $_.Path ":" $_.LineNumber ":" $_.Line }
    throw "Path constraint scan found forbidden target references"
}
Write-Host "Path constraint scan OK"

Write-Host "== Dist executable smoke =="
$process = Start-Process -FilePath $appExe -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 3
if ($process.HasExited) {
    throw "AVScope.exe exited early with code $($process.ExitCode)"
}
Stop-Process -Id $process.Id -Force
Write-Host "Dist executable smoke OK"

Write-Host "== Installer smoke =="
Start-Process -FilePath $setup -ArgumentList @("/S", "/D=$installDir") -Wait -WindowStyle Hidden
if (-not (Test-Path "$installDir\AVScope.exe")) {
    throw "Installed AVScope.exe not found"
}
if (-not (Test-Path "$installDir\_internal\ffprobe.exe")) {
    throw "Installed ffprobe.exe not found"
}
if (-not (Test-Path "$installDir\_internal\ffmpeg.exe")) {
    throw "Installed ffmpeg.exe not found"
}
if (-not (Test-Path "$installDir\_internal\plugins\demo_magic.json")) {
    throw "Installed plugin template not found"
}
$installedProcess = Start-Process -FilePath "$installDir\AVScope.exe" -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 3
if ($installedProcess.HasExited) {
    throw "Installed AVScope.exe exited early with code $($installedProcess.ExitCode)"
}
Stop-Process -Id $installedProcess.Id -Force
Start-Process -FilePath "$installDir\Uninstall.exe" -ArgumentList "/S" -Wait -WindowStyle Hidden
if (Test-Path "$installDir\AVScope.exe") {
    throw "Uninstall did not remove AVScope.exe"
}
Write-Host "Installer smoke OK"

Write-Host "== Validation report =="
& $python "$root\scripts\validation_report.py" --root $root --output $validationReportPath
if (-not (Test-Path $validationReportPath)) {
    throw "Validation report was not generated"
}
Write-Host "Validation report OK"

Write-Host "== Validation complete =="
