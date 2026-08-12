$ErrorActionPreference = "Stop"

$root = "G:\AVScope"
$python = "E:\DevelopmentEnvironment\python\python.exe"
$packages = "E:\AVScopeTools\python-packages"
$output = "$root\dist\AVScopeQt\engine"
$work = "$root\build\qt-engine"
$ffmpegRoot = "E:\DevelopmentEnvironment\ffmpeg-8.1-essentials_build\bin"

$env:PYTHONPATH = "$root;$packages"
$env:PYINSTALLER_CONFIG_DIR = "E:\AVScopeTools\pyinstaller-config"
$env:TEMP = "$root\tmp"
$env:TMP = "$root\tmp"

New-Item -ItemType Directory -Force -Path "$root\dist\AVScopeQt" | Out-Null
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
