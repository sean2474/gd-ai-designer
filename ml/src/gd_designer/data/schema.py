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

    Mirrors DATA_COLLECTION.md §5.2 Stage 1 schema. Holds the compressed
    `level_string_raw` + cheap metadata only; Stage 2 (parse_levels.py) is
    responsible for decoding and producing typed objects in data/interim/.
    Older crawls may have had parsed fields inline — those are tolerated via
    `extra="ignore"` but we don't write them anymore.
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

    # Undecoded base64+gzip blob — sole source of object data, decoded on demand.
    level_string_raw: str

    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RejectionReason(str, Enum):
    NOT_RATED = "NOT_RATED"
    PLATFORMER = "PLATFORMER"
    OBJECT_COUNT_OUT_OF_RANGE = "OBJECT_COUNT_OUT_OF_RANGE"
    EMPTY_LEVEL_STRING = "EMPTY_LEVEL_STRING"
    GAME_VERSION_TOO_OLD = "GAME_VERSION_TOO_OLD"
    GAME_VERSION_TOO_NEW = "GAME_VERSION_TOO_NEW"
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


class ParsedObject(BaseModel):
    """Typed view of a single GD object. Unknown keys preserved in `extra`."""

    model_config = ConfigDict(extra="ignore")

    object_id: int = 0
    x: float = 0.0
    y: float = 0.0
    rotation: float = 0.0
    scale: float = 1.0
    flip_x: bool = False
    flip_y: bool = False
    z_order: int = 0
    z_layer: int = 0
    editor_layer: int = 0
    editor_layer_2: int = 0
    color_channel: int = 0
    color_channel_2: int = 0
    group_ids: list[int] = Field(default_factory=list)
    extra: dict[str, str] = Field(default_factory=dict)


class ParsedLevel(BaseModel):
    """Stage 2 output: typed objects + bbox, one file per level in data/interim/."""

    model_config = ConfigDict(extra="ignore")

    schema_version: str = SCHEMA_VERSION
    level_id: int
    name: str
    creator: str
    rating: Rating
    length: Length
    game_version: int
    object_count: int

    header: dict[str, str] = Field(default_factory=dict)
    objects: list[ParsedObject] = Field(default_factory=list)

    bbox_min_x: float = 0.0
    bbox_min_y: float = 0.0
    bbox_max_x: float = 0.0
    bbox_max_y: float = 0.0
