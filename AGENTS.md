# AGENTS.md

Instructions for AI coding agents (primarily Claude Code, used through JetBrains Air) working on **valorant-coach**: a local match-review tool that finds costly decisions in pro VALORANT matches, estimates how much a different decision would have helped, explains why, and tracks habits. Built for the Sky's The Limit 2026 (Cloud9 x JetBrains) hackathon, Category 1.

The design is in [docs/DESIGN.md](docs/DESIGN.md). Read it before making structural changes. If you change the architecture, data model or fight definition, update DESIGN.md in the same change.

## 🚫 Rule 1: the data never enters this repo

The GRID data is licensed for local hackathon use only. Committing it, even to a private repo, is redistribution.

- The data lives in a **separate** repo, `../stl-hackathon-2026-grid-starter`, referenced by the `STL_DATA_DIR` env var (default `../stl-hackathon-2026-grid-starter`). Never copy it into this repo. Never hardcode an absolute path.
- **Everything derived from the data is also data:** Parquet tables, decompressed `.jsonl`, caches, DuckDB files, trained models, calibrators, SHAP outputs, plots containing real match data. All of it goes in `derived/`, which is git-ignored.
- **Before every commit**, run `git diff --cached --name-only` and check nothing from `derived/` or the data repo, and no `*.zst`, `*.jsonl`, `*.parquet`, `*.duckdb`, model or `.env` file, is staged. Never use `git add -A` / `git add .`; stage files by path.
- If data was ever committed, **stop and tell the user** before pushing.
- Test fixtures must be **small, hand-written** synthetic events, never excerpts copied from the real feeds.
- Don't upload the data or derived data anywhere (no external APIs, no LLM calls with raw events, no hosting). If an optional LLM feature is added, send it only aggregated model factors, never raw events.
- The data license ends when the hackathon ends; nothing here should assume long-term use of the models.

The data repo's own rules are in `../stl-hackathon-2026-grid-starter/AGENTS.md`. Follow them too.

## Project layout

```
valorant-coach/
├── coach/              # Python package
│   ├── io/             # feed + meta readers
│   ├── ingest/         # series replayer → events tables
│   ├── features/       # fights + round states
│   ├── model/          # train, calibrate, what-if, explain
│   └── app/            # Streamlit pages
├── configs/            # fight definition etc. (versioned YAML)
├── tests/              # unit tests with synthetic events
├── docs/DESIGN.md
└── derived/            # GIT-IGNORED outputs (events, features, models, scored)
```

The pipeline is five independent, re-runnable stages: `ingest → features → train → score → app`. Each reads the previous stage's folder under `derived/` and writes its own. Keep that separation: the app only reads precomputed tables, it never parses feeds or trains.

## Commands (planned; update when they exist)

```
coach ingest   --data $STL_DATA_DIR --out derived/events [--series ID ...]
coach features --in derived/events --out derived/features
coach train    --in derived/features --out derived/models
coach score    --features derived/features --models derived/models --out derived/scored
coach app
pytest
```

During development, run ingest on 2–3 series (`--series 2748743 ...`) before the full corpus.

## Reading the data

- Pick series from `$STL_DATA_DIR/val/series.csv`; maps, results and agents come from `meta/games.csv` and `meta/rosters.csv`. Don't glob directories or open every feed to find a match.
- **Stream** feeds line by line with `compression.zstd.open(path, "rt")` (Python ≥ 3.14). Never load a whole file, never decompress the corpus to disk.
- Never print or log a whole envelope or `seriesState`; it's huge. Log keys, counts or single fields.
- IDs are **strings**. Supplement `grid_event_id` = GRID `events[].id`.

### Data facts and gotchas (verified)
- Event `type` = `{actor.type}-{action}-{target.type}`. A `!` before the action **undoes** an earlier event; the replayer must apply undos.
- **Abandoned maps:** `series-!started-game` rolls back a game; drop every row for that game ID.
- Series `2855902` is invalidated (no match data). Skip it.
- Game state per event has all players' **2D** `position`, `money`, `loadoutValue`, `netWorth`; round segment has `alive`, `currentHealth`. **Map and agent are not in the feed state**; join from meta. No armor field seen so far.
- Kill events carry the weapon (`weaponKills`); damage events don't.
- **No aim during fights, no shots fired, no line of sight.** Aim (`view`, unit 3D vector) exists only on ability casts in the supplement. Respect its `quality` flag (`ok`, `gap_exceeded`, `missing_*`).
- VCT Americas 2025 series sample movement at **1 Hz** instead of ~5 Hz. Carry an `is_low_rate` flag on every derived row.

## Modelling rules

- **Train/test split by tournament or series, never by random row.** Fights from one match leak into each other.
- Feature columns are tagged **situation** (can't change: numbers advantage, HP, economy, clock) or **decision** (can change: teammate distance, utility before the fight, taking a fight while outnumbered). Keep the lists in one place in code. What-if scoring may only change **decision** columns.
- `landed_first_hit` is partly an outcome. Never use it in the model used for what-if.
- Every derived table and model records `fight_def_version` (from `configs/`). Never mix versions.
- Report calibrated probabilities (check Brier score and a reliability plot) and always compare against the logistic-regression baseline.
- Only recommend a what-if when enough similar real fights took that decision (support check, default `n ≥ 30`). Present gains as **estimates**, with real examples alongside; they are correlational.

## Code conventions

- Python, typed (`from __future__ import annotations`, type hints on public functions). pandas/pyarrow for tables, DuckDB for ad-hoc queries, LightGBM + SHAP for models, Streamlit for the UI.
- Paths via `pathlib` and config, never hardcoded. Data dir from `STL_DATA_DIR`.
- Per-series work runs in a process pool and writes one output file per series, so stages are resumable and skip up-to-date outputs.
- Errors on a single series are logged (`derived/ingest_errors.csv`) and the pipeline continues; schema checks between stages fail loudly.
- Add or update tests for any change to the replayer or fight builder: rollbacks, abandoned maps, trades, self-damage, missing supplement.

## Working style

- Prefer small, verifiable steps. After changing extraction logic, re-run on 2–3 series and sanity-check numbers (positions in range, HP 0–100+, fights per round plausible) before running everything.
- Ask before long or disk-heavy operations (full re-ingest, decompressing files, installing large packages).
- Don't commit or push unless asked.
