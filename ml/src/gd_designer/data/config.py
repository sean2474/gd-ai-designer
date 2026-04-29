"""Central data-pipeline config. Edit values here instead of passing CLI flags.

Everything Stage 1 needs is defined below as module-level constants and one
`FetchConfig` dataclass (the same one `fetch.py` consumes). The `collect_raw`
script imports `FETCH_CONFIG` from here directly.
"""
from __future__ import annotations

from pathlib import Path

from .fetch import FetchConfig
from .schema import Rating

# ---- paths (relative to repo root when scripts are run from `ml/`) ----

REPO_ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"
MANIFEST_PATH = DATA_DIR / "manifest.csv"
REJECTION_LOG_PATH = DATA_DIR / "rejection_log.jsonl"
DB_PATH = DATA_DIR / "gd.db"
OBJECT_IDS_JSON = DATA_DIR / "object_ids.json"

# ---- Stage 1 (fetch) ----

# Full run vs dry-run: set MAX_LEVELS to None for full crawl, or a small int
# (e.g. 10) to validate the pipeline end-to-end against DATA_COLLECTION.md §12.
MAX_LEVELS: int | None = None

# Search tiers. Drop any you don't want; order is fetch order.
RATINGS: tuple[Rating, ...] = (
    Rating.FEATURED,
    Rating.EPIC,
    Rating.LEGENDARY,
    Rating.MYTHIC,
)

EXCLUDE_PLATFORMER: bool = True
RATE_PER_SEC: float = 1.0          # §4.1 — token bucket average.
MAX_PAGES_PER_QUERY: int = 500     # featured pre-2.2 era can go very deep.
FORCE_REFETCH: bool = False        # True to re-download levels whose JSON already exists.
FROM_MANIFEST: Path | None = None  # set to MANIFEST_PATH to reproduce a prior dataset.

# Logging verbosity: 0=WARNING, 1=INFO, 2=DEBUG.
LOG_VERBOSITY: int = 1

# ---- Stage 2 (parse) ----

# Re-parse raw JSONs even when an interim output already exists.
PARSE_FORCE: bool = False

# ---- Stage 2.5 (build_db) ----

# Re-insert levels that already have rows in gd.db.
DB_FORCE: bool = False
# How often (in levels) to commit during the migration.
DB_COMMIT_EVERY: int = 50

# ---- Export-for-testing ----

# Pick a downloaded level to mutate + save as .gmd for manual GD import.
# 66202727 = "InsideTheGravity" (8k objects — smallest of the 10 dry-run downloads).
TEST_EXPORT_LEVEL_ID: int = 66202727

# Drop every object with x < this threshold before re-encoding. In GD, 1 "block"
# = 30 units of x, so 30 blocks = 900. This removes everything in the level's
# front 30-block span (including the hidden setup zone at x=-29).
TEST_EXPORT_DROP_X_BELOW: float = 900.0

# Output path for the modified .gmd.
TEST_EXPORT_GMD_PATH = DATA_DIR / "test_export.gmd"

# ---- Assembled configs ----

FETCH_CONFIG = FetchConfig(
    output_dir=RAW_DIR,
    ratings=RATINGS,
    exclude_platformer=EXCLUDE_PLATFORMER,
    rate_per_sec=RATE_PER_SEC,
    max_pages_per_query=MAX_PAGES_PER_QUERY,
    force=FORCE_REFETCH,
    from_manifest=FROM_MANIFEST,
    max_levels=MAX_LEVELS,
)
