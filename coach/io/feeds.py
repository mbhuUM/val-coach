"""Streaming readers for GRID event feeds and VALORANT ability supplements.

Files are zstd-compressed JSON Lines. They are always streamed line by line;
never load or decompress a whole file (uncompressed they are 50-150x larger).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from compression import zstd
from pathlib import Path
from typing import Any

Envelope = dict[str, Any]
Event = dict[str, Any]


def iter_jsonl_zst(path: str | Path) -> Iterator[dict[str, Any]]:
    """Yield one parsed JSON object per line of a .jsonl.zst file."""
    with zstd.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def iter_envelopes(path: str | Path) -> Iterator[Envelope]:
    """Yield GRID envelopes in file order (ordered by ``sequenceNumber``)."""
    yield from iter_jsonl_zst(path)


def iter_events(path: str | Path) -> Iterator[tuple[Envelope, Event]]:
    """Yield ``(envelope, event)`` pairs for every event in a GRID feed."""
    for envelope in iter_envelopes(path):
        for event in envelope.get("events", ()):
            yield envelope, event


def iter_supplement(path: str | Path) -> Iterator[dict[str, Any]]:
    """Yield ability-cast records from a VALORANT ability supplement."""
    yield from iter_jsonl_zst(path)


def is_undo(event_type: str) -> bool:
    """True for events that reverse an earlier one (``actor-!action-target``)."""
    return "-!" in event_type


def undone_type(event_type: str) -> str:
    """Map an undo type to the type it reverses: ``a-!b-c`` -> ``a-b-c``."""
    return event_type.replace("-!", "-", 1)
