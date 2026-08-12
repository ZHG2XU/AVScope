# AVScope Installation Log

Date: 2026-08-11

This file records tools installed after the project started. Project source and deliverables remain under `G:\AVScope`; tool dependencies installed for packaging are under `E:\AVScopeTools`.

## Installed Tool Root

- `E:\AVScopeTools`

## Installed Python Packages

Installed with:

```powershell
E:\DevelopmentEnvironment\python\python.exe -m pip install --target E:\AVScopeTools\python-packages --cache-dir E:\AVScopeTools\pip-cache --disable-pip-version-check pyinstaller
```

Packages installed under `E:\AVScopeTools\python-packages`:

- `pyinstaller==6.22.0`
- `pyinstaller-hooks-contrib==2026.6`
- `altgraph==0.17.5`
- `packaging==26.3`
- `pefile==2024.8.26`
- `pywin32-ctypes==0.2.3`
- `setuptools==84.0.0`

## New Tool Directories

- `E:\AVScopeTools\python-packages`
- `E:\AVScopeTools\pip-cache`
- `E:\AVScopeTools\tmp`
- `E:\AVScopeTools\pyinstaller-config`
- `E:\AVScopeTools\downloads`
- `E:\AVScopeTools\nsis_extract\nsis-3.12`

## Downloaded / Extracted Installer Tool

- `E:\AVScopeTools\downloads\nsis-3.12.real.zip`
- `E:\AVScopeTools\nsis_extract\nsis-3.12\makensis.exe`
- NSIS version: `3.12`

## Purpose

PyInstaller is used to produce a Windows executable build of AVScope without installing files on `C:\`.

NSIS is used from its portable zip distribution to produce `G:\AVScope\dist\AVScope-Setup.exe`.

## Existing Qt Environment Reused

No new Qt files were installed by this refactor. The following pre-existing E-drive toolchain is used:

- `E:\QT\6.9.0\mingw_64` - Qt 6.9.0 libraries and deployment tools
- `E:\QT\Tools\mingw1310_64` - MinGW 13.1 C++ compiler
- `E:\QT\Tools\CMake_64` - CMake
- `E:\QT\Tools\Ninja` - Ninja build tool

The Qt source, build cache, runtime output, screenshots, and temporary analysis JSON remain under `G:\AVScope`.
