"""Project paths and settings.

The GRID data repo is resolved from ``STL_DATA_DIR`` (environment variable or
``.env``), defaulting to ``../stl-hackathon-2026-grid-starter`` next to this
project. Relative paths are resolved against the project root.
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = "../stl-hackathon-2026-grid-starter"
DERIVED_DIR = PROJECT_ROOT / "derived"  # git-ignored; all outputs go here
CONFIGS_DIR = PROJECT_ROOT / "configs"

# GRID invalidated this series; its feed holds no match data.
INVALID_SERIES = frozenset({"2855902"})


def _read_dotenv(path: Path) -> dict[str, str]:
    """Minimal .env parser: KEY=VALUE lines, # comments, optional quotes."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def data_dir(override: str | os.PathLike[str] | None = None) -> Path:
    """Return the GRID data repo path, checking that it looks right."""
    raw = (
        override
        or os.environ.get("STL_DATA_DIR")
        or _read_dotenv(PROJECT_ROOT / ".env").get("STL_DATA_DIR")
        or DEFAULT_DATA_DIR
    )
    path = Path(raw)
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()
    if not (path / "val" / "series.csv").is_file():
        raise FileNotFoundError(
            f"GRID data not found at {path} (expected val/series.csv). "
            "Set STL_DATA_DIR to the stl-hackathon-2026-grid-starter folder."
        )
    if path == PROJECT_ROOT or PROJECT_ROOT in path.parents:
        raise RuntimeError(
            f"Data dir {path} is inside the project repo. Keep the data outside "
            "this repo so it can never be committed."
        )
    return path
