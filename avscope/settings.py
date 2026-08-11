from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


MAX_RECENT_FILES = 12


def app_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def state_dir() -> Path:
    base = app_base_dir()
    state = base / "data"
    state.mkdir(parents=True, exist_ok=True)
    return state


class AppSettings:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else state_dir() / "settings.json"
        self.data: dict[str, Any] = {"recent_files": []}
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if isinstance(loaded, dict):
            recent = loaded.get("recent_files", [])
            self.data["recent_files"] = [str(item) for item in recent if isinstance(item, str)]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def recent_files(self) -> list[str]:
        return list(self.data.get("recent_files", []))

    def add_recent_file(self, path: str | Path) -> None:
        value = str(Path(path))
        existing = [item for item in self.recent_files() if item.lower() != value.lower()]
        self.data["recent_files"] = [value] + existing[: MAX_RECENT_FILES - 1]
        self.save()

    def clear_recent_files(self) -> None:
        self.data["recent_files"] = []
        self.save()
