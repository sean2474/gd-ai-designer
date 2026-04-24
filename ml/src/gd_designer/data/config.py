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

# ---- Stage 1 (fetch) ----

# Full run vs dry-run: set MAX_LEVELS to None for full crawl, or a small int
# (e.g. 10) to validate the pipeline end-to-end against DATA_COLLECTION.md §12.
MAX_LEVELS: int | None = 10

# Search tiers. Drop any you don't want; order is fetch order.
RATINGS: tuple[Rating, ...] = (
    Rating.FEATURED,
    Rating.EPIC,
    Rating.LEGENDARY,
    Rating.MYTHIC,
)

EXCLUDE_PLATFORMER: bool = True
RATE_PER_SEC: float = 1.0          # §4.1 — token bucket average.
MAX_PAGES_PER_QUERY: int = 100     # safety cap; one tier rarely exceeds this.
FORCE_REFETCH: bool = False        # True to re-download levels whose JSON already exists.
FROM_MANIFEST: Path | None = None  # set to MANIFEST_PATH to reproduce a prior dataset.

# Logging verbosity: 0=WARNING, 1=INFO, 2=DEBUG.
LOG_VERBOSITY: int = 1

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
