# AVScope Installation Log

Date: 2026-08-11

This file records tools installed after the project started. Project source and deliverables remain under `.`; tool dependencies installed for packaging are under `%AVSCOPE_TOOLS%`.

## Installed Tool Root

- `%AVSCOPE_TOOLS%`

## Installed Python Packages

Installed with:

```powershell
python -m pip install --target "$env:AVSCOPE_TOOLS\python-packages" --cache-dir "$env:AVSCOPE_TOOLS\pip-cache" --disable-pip-version-check pyinstaller
```

Packages installed under `%AVSCOPE_TOOLS%\python-packages`:

- `pyinstaller==6.22.0`
- `pyinstaller-hooks-contrib==2026.6`
- `altgraph==0.17.5`
- `packaging==26.3`
- `pefile==2024.8.26`
- `pywin32-ctypes==0.2.3`
- `setuptools==84.0.0`

## New Tool Directories

- `%AVSCOPE_TOOLS%\python-packages`
- `%AVSCOPE_TOOLS%\pip-cache`
- `%AVSCOPE_TOOLS%\tmp`
- `%AVSCOPE_TOOLS%\pyinstaller-config`
- `%AVSCOPE_TOOLS%\downloads`
- `%AVSCOPE_TOOLS%\nsis_extract\nsis-3.12`

## Downloaded / Extracted Installer Tool

- `%AVSCOPE_TOOLS%\downloads\nsis-3.12.real.zip`
- `%AVSCOPE_TOOLS%\nsis_extract\nsis-3.12\makensis.exe`
- NSIS version: `3.12`

## Purpose

PyInstaller is used to produce a Windows executable build of AVScope without installing files on `%SYSTEMDRIVE%\`.

NSIS is used from its portable zip distribution to produce `.\dist\AVScope-Setup.exe`.

## Existing Qt Environment Reused

No new Qt files were installed by this refactor. The following pre-existing E-drive toolchain is used:

- `%AVSCOPE_QT_ROOT%` - Qt 6.9.0 libraries and deployment tools
- `%AVSCOPE_MINGW%` - MinGW 13.1 C++ compiler
- `%AVSCOPE_CMAKE_HOME%` - CMake
- `%AVSCOPE_NINJA_HOME%` - Ninja build tool

The Qt source, build cache, runtime output, screenshots, and temporary analysis JSON remain under `.`.
