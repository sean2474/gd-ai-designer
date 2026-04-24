"""Encoder hyperparameters. See docs/ENCODER.md §16 for the symbol table.

Edit these values; no CLI flags (CLAUDE.md convention).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..data.config import DATA_DIR, REPO_ROOT


# ---- spatial axis / windowing (ENCODER.md §1) ----

WINDOW_RADIUS_UNITS: int = 30   # c; window width = 60 units = 2 blocks
WINDOW_STRIDE_UNITS: int = 5    # 91.7% overlap
MIN_LEVEL_WIDTH_UNITS: int = 120  # skip levels where <2 windows fit
N_OBJ_MAX: int = 128            # per-window object cap (ENCODER.md §11.3)

# ---- tokenizer (§11.2) ----

Y_BUCKETS: int = 32
ROT_BUCKETS: int = 8
SCALE_BUCKETS: int = 8
COLOR_BUCKETS: int = 33
VOCAB_SIZE: int = 256  # room above ≈195 effective tokens

# ---- model (§13) ----

D_MODEL: int = 256
N_LAYERS: int = 4
N_HEADS: int = 8
FFN_DIM: int = 1024
DROPOUT: float = 0.1
MAX_SEQ_LEN: int = 1024
LATENT_DIM: int = 256
DINO_HEAD_DIM: int = 65536

# ---- DINO loss (§10) ----

TAU_STUDENT: float = 0.1
TAU_TEACHER: float = 0.04
TEACHER_EMA: float = 0.996
CENTER_EMA: float = 0.9
N_GLOBAL_VIEWS: int = 2
N_LOCAL_VIEWS: int = 4
LOCAL_VIEW_RADIUS: int = 15   # half of window

# ---- aux recon loss (§10) ----

RECON_MASK_RATIO: float = 0.15
RECON_LOSS_WEIGHT: float = 0.3   # α

# ---- prototype + boundary (§2, §4, §5, §6) ----

K_PROTOTYPES: int = 4
SOFTMAX_T: float = 0.1           # T for soft membership
ENTROPY_THRESHOLD: float = 0.7   # τ (on normalized entropy ∈ [0,1])
LOCAL_MAXIMA_DELTA_UNITS: int = 10  # δ
MERGE_GAP_UNITS: int = 2         # g
TRANSITION_BUFFER_UNITS: int = 3   # T_buf
LR_WINDOW_SIZE: int = 6          # w for left/right comparison
ENSEMBLE_GAMMA: float = 0.7      # γ for s_final = γH + (1-γ) s_LR

# ---- bootstrap convergence (§9) ----

MAX_BOOTSTRAP_ITERS: int = 3
IOU_BOUNDARY_TARGET: float = 0.9
IOU_MATCH_TOLERANCE_UNITS: int = 5   # ε

# ---- training (§13) ----

BATCH_SIZE_EFFECTIVE: int = 256
LR: float = 5e-4
WEIGHT_DECAY: float = 0.04
WARMUP_FRAC: float = 0.1
EPOCHS_V1: int = 100
EPOCHS_V2: int = 50

# ---- paths ----

ENCODER_DATA_DIR: Path = DATA_DIR / "processed" / "encoder"
ENCODER_CKPT_DIR: Path = REPO_ROOT / "checkpoints" / "encoder"
ENCODER_RUNS_DIR: Path = REPO_ROOT / "runs" / "encoder"


@dataclass
class EncoderConfig:
    """Assembled config passed to trainer / bootstrap loop."""
    # Windowing
    window_radius: int = WINDOW_RADIUS_UNITS
    window_stride: int = WINDOW_STRIDE_UNITS
    n_obj_max: int = N_OBJ_MAX

    # Model
    d_model: int = D_MODEL
    n_layers: int = N_LAYERS
    n_heads: int = N_HEADS
    ffn_dim: int = FFN_DIM
    dropout: float = DROPOUT
    vocab_size: int = VOCAB_SIZE
    max_seq_len: int = MAX_SEQ_LEN
    latent_dim: int = LATENT_DIM
    dino_head_dim: int = DINO_HEAD_DIM

    # DINO
    tau_student: float = TAU_STUDENT
    tau_teacher: float = TAU_TEACHER
    teacher_ema: float = TEACHER_EMA
    center_ema: float = CENTER_EMA
    n_global_views: int = N_GLOBAL_VIEWS
    n_local_views: int = N_LOCAL_VIEWS
    local_view_radius: int = LOCAL_VIEW_RADIUS

    # Aux recon
    recon_mask_ratio: float = RECON_MASK_RATIO
    recon_loss_weight: float = RECON_LOSS_WEIGHT

    # Prototype/boundary
    k_prototypes: int = K_PROTOTYPES
    softmax_T: float = SOFTMAX_T
    entropy_threshold: float = ENTROPY_THRESHOLD
    local_maxima_delta: int = LOCAL_MAXIMA_DELTA_UNITS
    merge_gap: int = MERGE_GAP_UNITS
    transition_buffer: int = TRANSITION_BUFFER_UNITS
    lr_window_size: int = LR_WINDOW_SIZE
    ensemble_gamma: float = ENSEMBLE_GAMMA

    # Bootstrap
    max_iters: int = MAX_BOOTSTRAP_ITERS
    iou_target: float = IOU_BOUNDARY_TARGET
    iou_tolerance: int = IOU_MATCH_TOLERANCE_UNITS

    # Training
    batch_size: int = BATCH_SIZE_EFFECTIVE
    lr: float = LR
    weight_decay: float = WEIGHT_DECAY
    warmup_frac: float = WARMUP_FRAC
    epochs_v1: int = EPOCHS_V1
    epochs_v2: int = EPOCHS_V2

    # Paths
    data_dir: Path = field(default_factory=lambda: ENCODER_DATA_DIR)
    ckpt_dir: Path = field(default_factory=lambda: ENCODER_CKPT_DIR)
    runs_dir: Path = field(default_factory=lambda: ENCODER_RUNS_DIR)


DEFAULT_CONFIG = EncoderConfig()
