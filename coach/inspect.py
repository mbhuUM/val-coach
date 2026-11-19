"""Cheap sanity check of one series: event counts, games, rounds, undo events.

Prints small summaries only, never whole envelopes or ``seriesState``.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from coach.io.feeds import is_undo, iter_events, iter_supplement


@dataclass
class FeedSummary:
    envelopes: int = 0
    events: int = 0
    first_at: str | None = None
    last_at: str | None = None
    event_types: Counter[str] = field(default_factory=Counter)
    undo_types: Counter[str] = field(default_factory=Counter)
    rolled_back_games: set[str] = field(default_factory=set)
    rounds_won_by_team: Counter[str] = field(default_factory=Counter)
    position_events: int = 0  # kill/damage events whose game state has 10 positions


def summarize_feed(path: Path) -> FeedSummary:
    s = FeedSummary()
    last_envelope_id = None
    for envelope, event in iter_events(path):
        if envelope["id"] != last_envelope_id:
            last_envelope_id = envelope["id"]
            s.envelopes += 1
            s.first_at = s.first_at or envelope["occurredAt"]
            s.last_at = envelope["occurredAt"]
        s.events += 1
        etype = event["type"]
        s.event_types[etype] += 1
        if is_undo(etype):
            s.undo_types[etype] += 1
            if etype == "series-!started-game":
                s.rolled_back_games.add(str(event["target"]["id"]))
        if etype in ("team-won-round", "team-!won-round"):
            team = str((event["actor"].get("state") or {}).get("name", event["actor"]["id"]))
            s.rounds_won_by_team[team] += -1 if is_undo(etype) else 1
        if etype in ("player-killed-player", "player-damaged-player"):
            games = (event.get("seriesState") or {}).get("games") or []
            if games:
                players = [p for t in games[-1].get("teams", []) for p in t.get("players", [])]
                if len(players) == 10 and all("position" in p for p in players):
                    s.position_events += 1
    return s


def summarize_supplement(path: Path) -> tuple[int, Counter[str]]:
    n = 0
    quality: Counter[str] = Counter()
    for rec in iter_supplement(path):
        n += 1
        quality[rec.get("quality", "?")] += 1
    return n, quality
