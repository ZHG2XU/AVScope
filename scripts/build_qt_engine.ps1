$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = if ($env:AVSCOPE_PYTHON) { $env:AVSCOPE_PYTHON } else { (Get-Command python -ErrorAction SilentlyContinue).Source }
$packages = if ($env:AVSCOPE_PYTHON_PACKAGES) { $env:AVSCOPE_PYTHON_PACKAGES } else { "" }
$output = "$root\dist\AVScopeQt\engine"
$work = "$root\build\qt-engine"
$ffmpegRoot = if ($env:AVSCOPE_FFMPEG_ROOT) { $env:AVSCOPE_FFMPEG_ROOT } else { "" }

$env:PYTHONPATH = "$root;$packages"
$env:PYINSTALLER_CONFIG_DIR = if ($env:PYINSTALLER_CONFIG_DIR) { $env:PYINSTALLER_CONFIG_DIR } else { Join-Path $root "tmp\pyinstaller-config" }
$env:TEMP = "$root\tmp"
$env:TMP = "$root\tmp"

New-Item -ItemType Directory -Force -Path "$root\dist\AVScopeQt" | Out-Null
New-Item -ItemType Directory -Force -Path $work | Out-Null
# The repository directory is named AVScope while imports use the canonical
# lowercase package name avscope. PyInstaller needs an exact package path.
$packageCopy = Join-Path $work "avscope"
if (Test-Path -LiteralPath $packageCopy) { Remove-Item -LiteralPath $packageCopy -Recurse -Force }
Copy-Item -LiteralPath "$root\AVScope" -Destination $packageCopy -Recurse -Force
$env:PYTHONPATH = "$work;$root;$packages"
if (-not $python) { throw "Python not found. Set AVSCOPE_PYTHON." }
if (-not $ffmpegRoot -or -not (Test-Path (Join-Path $ffmpegRoot "ffmpeg.exe"))) { throw "ffmpeg not found. Set AVSCOPE_FFMPEG_ROOT." }
<##
if (-not $python) { throw "未找到 Python。请设置 `$env:AVSCOPE_PYTHON。" }
if (-not $ffmpegRoot -or -not (Test-Path (Join-Path $ffmpegRoot "ffmpeg.exe"))) { throw "未找到 ffmpeg。请设置 `$env:AVSCOPE_FFMPEG_ROOT 为包含 ffmpeg.exe/ffprobe.exe 的目录。" }
##>
& $python -m PyInstaller --noconfirm --clean --console --name AVScopeEngine `
    --add-binary "$ffmpegRoot\ffprobe.exe;." `
    --add-binary "$ffmpegRoot\ffmpeg.exe;." `
    --add-data "$root\plugins;plugins" `
    --distpath "$root\dist\AVScopeQt" `
    --workpath $work `
    --specpath "$root\packaging" `
    "$root\avscope_engine.py"
if ($LASTEXITCODE -ne 0) { throw "AVScope Qt engine build failed" }

if (Test-Path -LiteralPath $output) {
    Remove-Item -LiteralPath $output -Recurse -Force
}
Move-Item -LiteralPath "$root\dist\AVScopeQt\AVScopeEngine" -Destination $output
Write-Output "$output\AVScopeEngine.exe"
