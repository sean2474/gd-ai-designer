"""Self-supervised style encoder (Phase 4).

Bootstrap pipeline that learns a stylistic representation of GD level windows
without supervision, and iteratively refines itself by excluding transition
regions (ENCODER.md §9).

Entry points:
    - `train_v1(cfg)` / `bootstrap(cfg)` for full pipeline
    - `encode(window)` for downstream use (Planner / Designer)
"""
