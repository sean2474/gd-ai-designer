"""Stage 1 runner — fetch rated GD levels to data/raw/.

All settings live in `gd_designer/data/config.py`. Edit that file to change
tiers, rate, dry-run cap, etc. This script takes no arguments.

    uv run python scripts/collect_raw.py
"""
from __future__ import annotations

import asyncio
import logging
import sys

from gd_designer.data.config import FETCH_CONFIG, LOG_VERBOSITY
from gd_designer.data.fetch import collect_raw


def _configure_logging(verbose: int) -> None:
    level = logging.WARNING
    if verbose == 1:
        level = logging.INFO
    elif verbose >= 2:
        level = logging.DEBUG
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


async def _run() -> int:
    stats = await collect_raw(FETCH_CONFIG)
    print(
        f"done: fetched={stats.fetched} skipped={stats.skipped_existing} "
        f"rejected={stats.rejected} errors={stats.errors} by_rating={stats.by_rating}"
    )
    return 0 if stats.errors == 0 else 1


def main() -> int:
    _configure_logging(LOG_VERBOSITY)
    try:
        return asyncio.run(_run())
    except KeyboardInterrupt:
        print("\ninterrupted — partial progress preserved; rerun to resume.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
