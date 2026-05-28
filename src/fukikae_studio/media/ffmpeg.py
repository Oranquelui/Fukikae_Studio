import shutil
from pathlib import Path
from typing import Callable, Optional


class MediaToolError(RuntimeError):
    """Raised when a required local media executable is unavailable."""


class MediaPathError(ValueError):
    """Raised when a media artifact path violates local project boundaries."""


def require_media_tool(name: str, which: Optional[Callable[[str], Optional[str]]] = None) -> str:
    resolver = shutil.which if which is None else which
    found = resolver(name)
    if not found:
        raise MediaToolError(f"Required media tool '{name}' was not found on PATH.")
    return found


def assert_inside_project(project_dir: Path, candidate: Path) -> Path:
    project_root = Path(project_dir).resolve(strict=False)
    resolved = Path(candidate).resolve(strict=False)
    try:
        resolved.relative_to(project_root)
    except ValueError as exc:
        raise MediaPathError(f"Media artifact paths must stay inside project: {candidate}") from exc
    return candidate
