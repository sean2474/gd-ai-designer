"""Stage 2 runner — convert raw JSON dumps to typed ParsedLevel files.

Reads every `data/raw/*.json`, produces `data/interim/{id}.json` with
`ParsedLevel` structure (typed objects + bbox). Idempotent: existing outputs
are skipped unless `PARSE_FORCE=True` in config.py.
"""
from __future__ import annotations

import logging
import sys

from gd_designer.data.config import INTERIM_DIR, LOG_VERBOSITY, PARSE_FORCE, RAW_DIR
from gd_designer.data.fetch import iter_raw_files
from gd_designer.data.parse import convert_level
from gd_designer.data.schema import RawLevel

log = logging.getLogger(__name__)


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


def main() -> int:
    _configure_logging(LOG_VERBOSITY)
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)

    n_ok = n_skip = n_err = 0
    total_objects = 0

    for raw_path in iter_raw_files(RAW_DIR):
        out_path = INTERIM_DIR / raw_path.name
        if out_path.exists() and not PARSE_FORCE:
            n_skip += 1
            continue
        try:
            raw = RawLevel.model_validate_json(raw_path.read_text(encoding="utf-8"))
            parsed = convert_level(raw)
            out_path.write_text(parsed.model_dump_json(indent=2), encoding="utf-8")
            n_ok += 1
            total_objects += parsed.object_count
            log.info(
                "parsed %d (%s, %d objs, bbox=[%.0f..%.0f,%.0f..%.0f])",
                parsed.level_id,
                parsed.name,
                parsed.object_count,
                parsed.bbox_min_x,
                parsed.bbox_max_x,
                parsed.bbox_min_y,
                parsed.bbox_max_y,
            )
        except Exception as exc:
            log.error("parse failed %s: %r", raw_path.name, exc)
            n_err += 1

    print(
        f"done: ok={n_ok} skipped={n_skip} err={n_err} total_objects={total_objects}"
    )
    return 0 if n_err == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
