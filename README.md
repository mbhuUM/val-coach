# valorant-coach

Match review and decision coaching for professional VALORANT. It finds the most costly decisions in a match, estimates how much a different decision would have helped, explains why, and tracks player habits.

Built for the Sky's The Limit 2026 (Cloud9 x JetBrains) hackathon, Category 1. Design: [docs/DESIGN.md](docs/DESIGN.md).

## Setup

The GRID data is **not** in this repo. Clone it next to this folder:

```
Hackathon/
├── stl-hackathon-2026-grid-starter/   # data (separate repo)
└── valorant-coach/                    # this repo
```

If it lives elsewhere, set `STL_DATA_DIR` (see `.env.example`).

Requires Python 3.14+.

```
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

## Usage

```
coach inspect --series 2748743     # sanity-check one series feed
pytest
```

Pipeline stages (`ingest`, `features`, `train`, `score`, `app`) are being built; see the design doc.

## Data rules

The data is licensed for local hackathon use only. Nothing from the data repo, and nothing derived from it (tables, caches, models), is ever committed. All outputs go to the git-ignored `derived/` folder. See [AGENTS.md](AGENTS.md).

Match data provided by GRID. VALORANT is a trademark of Riot Games, Inc. This project is not endorsed by Riot Games.
