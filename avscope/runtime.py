"""Portable runtime paths for source, PyInstaller and installed builds."""
from __future__ import annotations
import os
import sys
from pathlib import Path

def executable_dir() -> Path:
    return Path(sys.executable).resolve().parent

def app_root() -> Path:
    override = os.environ.get("AVSCOPE_ROOT")
    if override:
        return Path(override).expanduser()
    exe = executable_dir()
    for candidate in (exe, exe / "_internal", Path(__file__).resolve().parent.parent):
        if (candidate / "plugins").is_dir() or (candidate / "samples").is_dir():
            return candidate
    return exe

def user_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    return Path(base) / "AVScope" if base else Path.home() / ".avscope"

def temp_dir(name: str) -> Path:
    path = user_data_dir() / "tmp" / name
    path.mkdir(parents=True, exist_ok=True)
    return path

def bundled_file(name: str) -> Path | None:
    candidates = [executable_dir() / name, executable_dir() / "_internal" / name]
    if hasattr(sys, "_MEIPASS"):
        candidates.insert(0, Path(getattr(sys, "_MEIPASS")) / name)
    return next((path for path in candidates if path.is_file()), None)
