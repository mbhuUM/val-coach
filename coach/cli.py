"""Command-line entry point: ``coach <command>``."""

from __future__ import annotations

import argparse
import sys

from coach import config
from coach.io import meta


def cmd_inspect(args: argparse.Namespace) -> int:
    from coach.inspect import summarize_feed, summarize_supplement

    data = config.data_dir(args.data)
    index = meta.load_series(data)
    games = meta.load_games(data)
    status = 0
    for sid in args.series:
        info = index.get(sid)
        print(f"\n=== series {sid} ===")
        if info is None:
            print("  not in val/series.csv")
            status = 1
            continue
        if sid in config.INVALID_SERIES:
            print("  invalidated by GRID; skipping")
            continue
        print(f"  {info.event} / {info.stage}: {info.teams}  ({info.scheduled_start})")
        for g in (g for g in games if g["series_id"] == sid):
            print(
                f"  map {g['game_number']}: {g['map']:<10} "
                f"{g['team1_name']} {g['team1_score']}-{g['team2_score']} {g['team2_name']}"
            )

        s = summarize_feed(info.feed_path)
        print(f"  envelopes {s.envelopes:,}  events {s.events:,}  ({s.first_at} -> {s.last_at})")
        print("  rounds won (feed): " + ", ".join(f"{k} {v}" for k, v in s.rounds_won_by_team.items()))
        print(f"  kill/damage events with 10 positions: {s.position_events:,}")
        if s.undo_types:
            print("  undo events: " + ", ".join(f"{k} x{v}" for k, v in s.undo_types.items()))
        if s.rolled_back_games:
            print(f"  rolled-back games: {sorted(s.rolled_back_games)}")
        print("  top event types:")
        for etype, n in s.event_types.most_common(args.top):
            print(f"    {n:>7,}  {etype}")

        if info.supplement_path:
            n, quality = summarize_supplement(info.supplement_path)
            q = ", ".join(f"{k} {v}" for k, v in quality.most_common())
            print(f"  ability supplement: {n:,} casts ({q})")
        else:
            print("  ability supplement: none")
    return status


def _not_built(name: str):
    def run(_args: argparse.Namespace) -> int:
        print(f"'coach {name}' is not built yet; see docs/DESIGN.md §7.", file=sys.stderr)
        return 2

    return run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="coach", description=__doc__)
    parser.add_argument("--data", help="GRID data dir (default: STL_DATA_DIR)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("inspect", help="sanity-check one or more series feeds")
    p.add_argument("--series", nargs="+", required=True, help="series IDs")
    p.add_argument("--top", type=int, default=15, help="event types to list")
    p.set_defaults(func=cmd_inspect)

    for name in ("ingest", "features", "train", "score", "app"):
        sub.add_parser(name, help="(not built yet)").set_defaults(func=_not_built(name))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
