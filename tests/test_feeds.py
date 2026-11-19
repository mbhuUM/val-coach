"""Tests for the feed readers, using small synthetic files (never real data)."""

from __future__ import annotations

import json
from compression import zstd
from pathlib import Path

from coach.inspect import summarize_feed
from coach.io.feeds import is_undo, iter_envelopes, iter_events, undone_type


def _event(eid: str, actor: str, action: str, target: str, **extra) -> dict:
    return {
        "id": eid,
        "type": f"{actor}-{action}-{target}",
        "actor": {"type": actor, "id": f"{actor}-1", "state": {"name": f"{actor} one"}},
        "action": action,
        "target": {"type": target, "id": extra.pop("target_id", f"{target}-1")},
        **extra,
    }


def _write_feed(path: Path, envelopes: list[dict]) -> Path:
    with zstd.open(path, "wt", encoding="utf-8") as fh:
        for env in envelopes:
            fh.write(json.dumps(env) + "\n")
    return path


def _envelope(seq: int, events: list[dict]) -> dict:
    return {
        "id": f"env-{seq}",
        "correlationId": f"corr-{seq}",
        "occurredAt": f"2026-01-01T00:00:{seq:02d}.000Z",
        "seriesId": "999",
        "sequenceNumber": seq,
        "events": events,
    }


def test_undo_helpers() -> None:
    assert is_undo("series-!started-game")
    assert not is_undo("series-started-game")
    assert undone_type("player-!purchased-item") == "player-purchased-item"


def test_streams_envelopes_and_events(tmp_path: Path) -> None:
    feed = _write_feed(
        tmp_path / "feed.jsonl.zst",
        [
            _envelope(1, [_event("e1", "series", "started", "game", target_id="g1")]),
            _envelope(2, [_event("e2", "team", "won", "round"), _event("e3", "team", "won", "round")]),
        ],
    )
    assert [e["sequenceNumber"] for e in iter_envelopes(feed)] == [1, 2]
    assert [ev["id"] for _, ev in iter_events(feed)] == ["e1", "e2", "e3"]


def test_summary_tracks_rollbacks_and_rounds(tmp_path: Path) -> None:
    feed = _write_feed(
        tmp_path / "feed.jsonl.zst",
        [
            _envelope(1, [_event("e1", "series", "started", "game", target_id="g1")]),
            _envelope(2, [_event("e2", "series", "!started", "game", target_id="g1")]),
            _envelope(3, [_event("e3", "series", "started", "game", target_id="g2")]),
            _envelope(4, [_event("e4", "team", "won", "round")]),
            _envelope(5, [_event("e5", "team", "won", "round")]),
            _envelope(6, [_event("e6", "team", "!won", "round")]),
        ],
    )
    s = summarize_feed(feed)
    assert s.envelopes == 6 and s.events == 6
    assert s.rolled_back_games == {"g1"}
    assert s.undo_types["series-!started-game"] == 1
    assert s.rounds_won_by_team["team one"] == 1
