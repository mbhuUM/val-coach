"""Readers for the data repo's index and ``meta/`` tables (VALORANT rows only).

Use these to choose series and to get facts that are not in the feed state,
such as map name, agents and final results. All IDs are strings.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

TITLE = "val"


@dataclass(frozen=True)
class SeriesInfo:
    series_id: str
    event: str
    stage: str
    scheduled_start: str
    teams: str
    feed_path: Path
    supplement_path: Path | None


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def load_series(data_dir: Path) -> dict[str, SeriesInfo]:
    """Index of VALORANT series from ``val/series.csv``, keyed by series ID."""
    out: dict[str, SeriesInfo] = {}
    for row in _read_csv(data_dir / "val" / "series.csv"):
        supp = row.get("ability_supplement") or ""
        out[row["series_id"]] = SeriesInfo(
            series_id=row["series_id"],
            event=row["event"],
            stage=row["stage"],
            scheduled_start=row["scheduled_start"],
            teams=row["teams"],
            feed_path=data_dir / row["file"],
            supplement_path=(data_dir / supp) if supp else None,
        )
    return out


def _load_meta(data_dir: Path, name: str) -> list[dict[str, str]]:
    return [r for r in _read_csv(data_dir / "meta" / name) if r["title"] == TITLE]


def load_games(data_dir: Path) -> list[dict[str, str]]:
    """Per-map rows: map, patch, winner, teams, sides, scores."""
    return _load_meta(data_dir, "games.csv")


def load_rosters(data_dir: Path) -> list[dict[str, str]]:
    """Per-player-per-map rows, including the agent (``character_name``)."""
    return _load_meta(data_dir, "rosters.csv")


def load_players(data_dir: Path) -> list[dict[str, str]]:
    return _load_meta(data_dir, "players.csv")


def load_teams(data_dir: Path) -> list[dict[str, str]]:
    return _load_meta(data_dir, "teams.csv")
