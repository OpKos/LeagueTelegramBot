from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_DIR = PROJECT_ROOT / "app"


def app_path(*parts: str) -> Path:
    """Resolve a path under the app/ directory, falling back to CWD if present."""
    candidate = Path.cwd().joinpath(*parts)
    if candidate.exists():
        return candidate
    return APP_DIR.joinpath(*parts)
