# System Design: VALORANT Fight Coach

Status: draft v1 · 2026-11-18

A match-review tool for VALORANT coaches. It flags the most costly decisions in a match, estimates how much a different decision would have helped, explains why, and tracks player habits across matches. Built on the GRID data in `stl-hackathon-2026-grid-starter`.

---

## 1. Requirements

### Functional
| # | Requirement |
|---|---|
| F1 | Extract **fights** (from damage/kill events) and **round states** (after each kill/plant) from every VALORANT series. |
| F2 | Predict **P(win fight)** and **P(win round)** for any situation. |
| F3 | **What-if scoring:** re-score a fight with only the *decision* features changed (wait vs take, utility first, teammate in trade range), and report the best alternative and its estimated gain. |
| F4 | **Explain** each prediction with SHAP (top factors, split into "your decision" vs "the situation"). |
| F5 | **Match review:** pick a series → map → see rounds, the 5–10 costliest decisions, each with a 2D map view, explanation, best alternative and 2–3 real pro examples. |
| F6 | **Habit tracking:** per-player and per-team habit scores (spacing/trade, utility timing) across matches. |

### Non-functional
- **Runs locally** on one Windows laptop (16 cores). No cloud, no hosting of data (license).
- **Interactive UI:** review page loads in < 2 s; scoring a fight < 50 ms.
- **Full rebuild** (extract + train) in under ~30 min, so we can iterate on fight definitions.
- **Reproducible:** same data + config → same tables and models.
- **Data never in git:** data, derived tables and model files live in ignored dirs.

### Constraints and assumptions
- Small team, hackathon timeline (weeks, not months). Prefer boring, fast tools.
- Must use a JetBrains tool (JetBrains Air with Claude Code).
- Python only. Python 3.15 venv exists; fall back to 3.14 if LightGBM/SHAP wheels are missing. `compression.zstd` is built in from 3.14.
- Data facts verified from the feeds:
  - Game state per event: all players' **2D position**, `money`, `loadoutValue`, `netWorth`; round segment has `alive`, `currentHealth`.
  - **Not in the feed state:** map name and agent → join from `meta/games.csv` and `meta/rosters.csv`. No armor field seen yet.
  - No aim during fights, no shot events, no line of sight. Aim only on ability casts (supplement).
  - `!` events undo earlier events; abandoned maps are rolled back; series `2855902` is invalid.

---

## 2. High-level design

```
 stl-hackathon-2026-grid-starter/ (read-only, STL_DATA_DIR)
   val/*.jsonl.zst   val-ability-supplements/*.jsonl.zst   meta/*.csv
          │                         │                          │
          ▼                         ▼                          │
 ┌──────────────────────────────────────────────┐              │
 │ 1. INGEST  (per series, parallel)            │◄─────────────┘
 │   stream envelopes → apply/undo events →     │  map, agents, results
 │   replay state → emit raw rows               │
 └──────────────────────────────────────────────┘
          │  events.parquet (damage, kills, casts, round markers + state)
          ▼
 ┌──────────────────────────────────────────────┐
 │ 2. BUILD FEATURES                            │
 │   group hits → fights; snapshot pre-fight    │
 │   state; round states; join supplement casts │
 └──────────────────────────────────────────────┘
          │  fights.parquet   round_states.parquet
          ▼
 ┌──────────────────────────────────────────────┐
 │ 3. TRAIN + EVALUATE                          │
 │   LogReg baseline · LightGBM · calibration   │
 │   split by series/tournament · metrics       │
 └──────────────────────────────────────────────┘
          │  models/*.txt  calibrators  metrics.json
          ▼
 ┌──────────────────────────────────────────────┐
 │ 4. SCORE (batch)                             │
 │   P(win) + SHAP + what-if gains + nearest    │
 │   pro examples for every fight               │
 └──────────────────────────────────────────────┘
          │  scored_fights.parquet  habits.parquet
          ▼
 ┌──────────────────────────────────────────────┐
 │ 5. APP  (Streamlit, local)                   │
 │   match review · fight detail · habits       │
 │   optional LLM text from top factors         │
 └──────────────────────────────────────────────┘
```

**Key decision:** everything expensive (parsing, SHAP, what-if, examples) is **precomputed in batch**. The app only reads Parquet with DuckDB/pandas. That keeps the UI fast and simple, at the cost of a rebuild when models change.

### Components and interfaces
Each stage is a CLI command that reads the previous stage's output folder and writes its own. Stages are independently re-runnable.

```
coach ingest   --data $STL_DATA_DIR --out derived/events      [--series 2748743 ...]
coach features --in derived/events --out derived/features
coach train    --in derived/features --out derived/models
coach score    --features derived/features --models derived/models --out derived/scored
coach app                                                    # streamlit run
```

Python modules (internal API):
```
coach/io/feeds.py        iter_envelopes(path) -> Iterator[dict]
coach/io/meta.py         load_games(), load_rosters(), load_series()
coach/ingest/replay.py   SeriesReplayer: apply(event), undo(event), state()
coach/features/fights.py build_fights(events_df, cfg) -> fights_df
coach/features/rounds.py build_round_states(events_df) -> rounds_df
coach/model/train.py     train(df, target, features, cfg) -> Model
coach/model/whatif.py    what_if(model, row, changes: dict) -> gain
coach/model/explain.py   shap_top(model, rows, k) -> list[Factor]
coach/app/               Streamlit pages
```

---

## 3. Deep dive

### 3.1 Ingest: replaying a series
- Stream with `compression.zstd.open(path, "rt")`, one envelope at a time. Never load a whole file.
- Keep a small **replayer** per series: current game, round, alive set, health, positions, money/loadout.
- **Rollbacks:** event types with `!` undo the matching earlier event. Track game IDs hit by `series-!started-game` and **drop all their rows** at the end.
- Emit only what later stages need (damage, kills, ability casts, round start/end, plant/defuse, freeze time end) plus a compact snapshot of the 10 players. Never store full `seriesState`.
- Join supplement casts on `grid_event_id` → add 3D position, `view`, `quality`, low-rate flag.
- Join `meta/games.csv` (map, winner, sides) and `meta/rosters.csv` (agent per player per game).
- **Parallelism:** one process per series (`ProcessPoolExecutor`, 14 workers). Write one Parquet file per series → partial reruns and crash safety for free.

### 3.2 Fight definition (configurable, versioned)
```yaml
fight:
  quiet_gap_s: 2.5        # no damage between the pair for this long → new fight
  join_window_s: 2.0      # damage/kill within this window and radius joins the fight
  join_radius_m: 15
  end_after_s: 3.0
  pre_fight_utility_s: 4.0
```
- **Start:** first hit between two opponents after `quiet_gap_s`.
- **Outcome label (per player):** survived and the opponent(s) in the fight died, vs died. Mixed/unclear fights are dropped or labelled separately.
- Stored with `fight_def_version` so models and tables never silently mix definitions.

### 3.3 Data model (Parquet tables)

**`fights`** (one row per player-in-fight, ~few hundred k rows)
| Column group | Columns |
|---|---|
| Keys | `fight_id, series_id, game_id, round_num, player_id, opponent_ids, team_id, side, map, agent, tournament, is_low_rate` |
| Time | `t_start, round_clock_s, spike_planted, t_since_plant_s` |
| Situation (can't change) | `alive_us, alive_them, hp, opp_hp, loadout, opp_loadout, team_money, weapon_est, map_zone` |
| Decision (can change) | `nearest_teammate_m, teammates_within_15m, own_util_last_4s, team_util_last_4s, util_type_last, took_fight_while_outnumbered, moved_since_last_contact` |
| Leaky / separate | `landed_first_hit` |
| Labels | `won_fight, won_round` |

**`round_states`** (one row per state change after a kill/plant): `alive_atk, alive_def, hp_sum_*, loadout_*, spike_planted, time_left_s, map, won_round_atk`.

**`scored_fights`**: `fight_id, player_id, p_win, p_win_cal, round_wp_before, round_wp_after, round_swing, shap_top (json), best_alt (json), best_alt_gain, example_fight_ids`.

**`habits`**: `player_id, team_id, map, metric, value, n, period`.

Map zones: grid cells (e.g. 8×8 per map) at first; replace with named callouts later if time allows.

### 3.4 Models
| Model | Target | Algorithm | Notes |
|---|---|---|---|
| Baseline | `won_fight` | Logistic regression | Sanity floor |
| Fight model | `won_fight` | LightGBM + isotonic calibration | Main engine; `landed_first_hit` excluded from the version used for what-if |
| Round model | `won_round` | LightGBM | Gives each fight's value as round-win swing |

- **Split:** by **tournament** (or series), never by row. Hold out one recent event as the final test set.
- **Metrics:** log loss, Brier score, AUC, reliability plot. Report vs baseline.
- **What-if:** change only decision columns to plausible values (e.g. `nearest_teammate_m → 8`, `own_util_last_4s → 1`). Gain = Δ calibrated P(win) × round swing. Only suggest changes seen often enough in that situation (support check, `n ≥ 30` similar fights) to avoid extrapolating.
- **Examples:** nearest neighbours in the situation-feature space among fights where the suggested decision was taken and won. Evidence only, not the engine.
- **Explain:** `shap.TreeExplainer`; top 3 factors, tagged decision vs situation.

### 3.5 App (Streamlit)
1. **Match picker:** tournament → series → map (from `series.csv`, `meta/games.csv`).
2. **Match review:** round timeline with round-WP line; ranked list of costliest decisions.
3. **Fight detail:** 2D map with 10 player dots at fight start, utility casts, P(win) gauge, SHAP bars, best alternative + gain, pro example links (series/round/time).
4. **Habits:** per player/team habit scores vs pro average, trend across matches.
- Optional: LLM writes a 2-sentence coaching note from the structured factors (no raw data sent; or skip entirely to keep everything local).
- Map images: need per-map minimap images and a world→image transform. **Open question:** sourcing these within license/copyright; fallback is a plain scatter with fitted bounds.

### 3.6 Caching and error handling
- Each stage skips series whose output file is newer than its input + code version (`--force` to redo).
- Bad series (parse error, no games, invalidated `2855902`) → logged to `derived/ingest_errors.csv`, pipeline continues.
- Schema checks between stages (expected columns, no NaN in labels, row counts per series) fail loudly.
- Unit tests on small hand-made event sequences: rollback, abandoned map, trade within window, self-damage, missing supplement.

---

## 4. Scale and reliability

| Item | Estimate |
|---|---|
| Raw VALORANT data | 816 MB compressed (~40–120 GB uncompressed, streamed only) + 164 MB supplements |
| Series / games | ~856 series, ~2,080 maps (`meta/games.csv`) |
| Fight rows | ~0.5–1 M player-in-fight rows → < 200 MB Parquet |
| Ingest time | JSON parsing dominates; ~1–3 s/series/core → **~2–5 min on 14 workers** |
| Train | LightGBM on ~1 M rows × ~40 features: < 2 min |
| SHAP + what-if for all fights | Tree SHAP ~ minutes; precomputed |

- Single machine is enough; scaling is "more processes", not more machines.
- Reliability = idempotent stages + per-series outputs + versioned configs. No services to keep alive.
- "Monitoring" = `metrics.json` per training run and an ingest summary (series ok/failed, rows per stage).

---

## 5. Trade-offs

| Decision | Chosen | Alternative | Why / cost |
|---|---|---|---|
| Processing | Batch precompute | Score on demand in app | Fast, simple UI; must rebuild after model changes |
| Storage | Parquet + DuckDB | SQLite/Postgres | Columnar, zero setup, fast analytics; no concurrent writes (not needed) |
| Model | LightGBM | Random forest, neural net | Best on tabular, fast, good SHAP; NN only as stretch goal |
| Recommendations | Model what-if + support check | Pure nearest-neighbour search | Generalises; risk of selection bias → show estimates + examples |
| UI | Streamlit | FastAPI + React | Days faster, Python only; less polished / custom |
| Fight definition | Rule-based, configurable | Learned segmentation | Explainable and tunable; misses no-hit fights |
| Map zones | Grid cells | Named callouts | Works for every map now; less readable for coaches |

---

## 6. Project layout

```
Hackathon/
├── stl-hackathon-2026-grid-starter/   # data repo (never inside our git repo)
└── valorant-coach/                    # our git repo
    ├── coach/                         # package (see §2)
    ├── tests/
    ├── configs/fight_v1.yaml
    ├── docs/DESIGN.md
    ├── derived/                       # GIT-IGNORED: parquet, models, caches
    ├── .env.example                   # STL_DATA_DIR=../stl-hackathon-2026-grid-starter
    ├── .gitignore                     # derived/, *.zst, *.jsonl, *.parquet, models, .env
    ├── pyproject.toml
    └── README.md
```

Before every commit: `git diff --cached --name-only`. Nothing from the data repo or `derived/` is ever staged.

---

## 7. Build order

1. Skeleton repo, `.gitignore`, `STL_DATA_DIR`, feed reader. **Check with 3 series.**
2. Replayer + ingest for 3 series; eyeball positions/health/rollbacks.
3. Fight builder + `data:explore-data` profile; tune fight config.
4. Full ingest; baseline + LightGBM fight model; calibration; series-split eval.
5. Round model + round swing.
6. What-if + SHAP + examples → `scored_fights`.
7. Streamlit review pages; then habits.
8. Polish, README, demo script for judges.

---

## 8. Open questions / revisit later

- **Fight labels** for multi-player fights (2v1 where one side trades): per-player label vs team label.
- **Weapon in fights** without a kill: estimate from loadout value / earlier kills, or drop.
- **Armor:** not seen in state; confirm whether it exists anywhere.
- **Selection bias** in what-if gains: consider propensity weighting or matched comparisons if gains look implausibly large.
- **Low-rate series** (VCT Americas 2025): filter vs down-weight.
- **Map images:** source and coordinate transforms.
- **Neural set/sequence model** on raw player states, if the hand-built features plateau.
- **License end:** models and derived tables can't be used after the hackathon. Plan deletion or archival without use.
