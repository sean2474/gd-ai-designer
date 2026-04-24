from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.0"


class Rating(str, Enum):
    FEATURED = "featured"
    EPIC = "epic"
    LEGENDARY = "legendary"
    MYTHIC = "mythic"


class Length(str, Enum):
    TINY = "tiny"
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"
    XL = "xl"
    PLATFORMER = "platformer"


class RawLevel(BaseModel):
    """Stage 1 output: one JSON per level under data/raw/{level_id}.json.

    Mirrors DATA_COLLECTION.md §5.2 Stage 1 schema.
    """

    model_config = ConfigDict(extra="ignore")

    schema_version: str = SCHEMA_VERSION
    level_id: int
    name: str
    creator: str
    rating: Rating
    song_id: int
    object_count: int
    length: Length
    platformer: bool
    game_version: int
    level_string_raw: str
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RejectionReason(str, Enum):
    NOT_RATED = "NOT_RATED"
    PLATFORMER = "PLATFORMER"
    OBJECT_COUNT_OUT_OF_RANGE = "OBJECT_COUNT_OUT_OF_RANGE"
    EMPTY_LEVEL_STRING = "EMPTY_LEVEL_STRING"
    GAME_VERSION_TOO_OLD = "GAME_VERSION_TOO_OLD"
    FETCH_ERROR = "FETCH_ERROR"
    PARSE_ERROR = "PARSE_ERROR"


class RejectionEntry(BaseModel):
    """One line in data/rejection_log.jsonl."""

    model_config = ConfigDict(extra="ignore")

    schema_version: str = SCHEMA_VERSION
    level_id: int
    reason: RejectionReason
    detail: str = ""
    stage: Literal["fetch", "parse", "prepare"] = "fetch"
    at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ManifestEntry(BaseModel):
    """One row in data/manifest.csv."""

    model_config = ConfigDict(extra="ignore")

    level_id: int
    creator: str
    name: str
    rating: Rating
    object_count: int
    raw_hash: str
