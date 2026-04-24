"""DINO + aux reconstruction trainer (ENCODER.md §10).

MVP scaffold: wires the model, loss, EMA, and centering together so a single
training step runs end-to-end. Actual dataloader + multi-crop augmentation is
a TODO; `train_one_iteration` is a placeholder that the caller fills.

Design keeps teacher parameters as a separate module with identical shape,
updated by EMA after each optimizer step.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass

import torch
import torch.nn as nn
import torch.nn.functional as F

from .config import EncoderConfig
from .model import EncoderModel


@dataclass
class DinoLossState:
    center: torch.Tensor   # [dino_head_dim]


class EncoderTrainer:
    """Owns the student/teacher pair plus the aux-recon head. The caller
    supplies multi-view batches; this class runs loss + optimizer step."""

    def __init__(self, cfg: EncoderConfig, device: str = "cuda"):
        self.cfg = cfg
        self.device = device

        self.student = EncoderModel(cfg).to(device)
        self.teacher = copy.deepcopy(self.student).to(device)
        for p in self.teacher.parameters():
            p.requires_grad = False

        self.optimizer = torch.optim.AdamW(
            self.student.parameters(),
            lr=cfg.lr,
            weight_decay=cfg.weight_decay,
        )

        self.state = DinoLossState(
            center=torch.zeros(cfg.dino_head_dim, device=device)
        )

    # ---- loss pieces ----

    def dino_loss(
        self,
        student_projected: torch.Tensor,   # [B_views_s, K]
        teacher_projected: torch.Tensor,   # [B_views_t, K]
    ) -> torch.Tensor:
        """Standard DINO cross-entropy; shapes: B_views = B · n_views, K = head dim."""
        s = F.log_softmax(student_projected / self.cfg.tau_student, dim=-1)
        t = F.softmax((teacher_projected - self.state.center) / self.cfg.tau_teacher, dim=-1)
        # Each teacher view is matched against all non-matching student views.
        # Leaving a clean pairing loop for clarity; optimize later.
        loss = 0.0
        n_pairs = 0
        n_t = teacher_projected.shape[0]
        n_s = student_projected.shape[0]
        for i in range(n_t):
            for j in range(n_s):
                if i == j:
                    continue
                loss = loss + -(t[i] * s[j]).sum()
                n_pairs += 1
        return loss / max(n_pairs, 1)

    def recon_loss(
        self,
        token_logits: torch.Tensor,      # [B, T, V]
        target_ids: torch.Tensor,        # [B, T] int
        mask_positions: torch.Tensor,    # [B, T] bool (True = was masked)
    ) -> torch.Tensor:
        """Cross-entropy only at masked positions (BERT-style)."""
        if mask_positions.sum() == 0:
            return token_logits.new_zeros(())
        flat_logits = token_logits[mask_positions]   # [N_masked, V]
        flat_targets = target_ids[mask_positions]    # [N_masked]
        return F.cross_entropy(flat_logits, flat_targets)

    # ---- EMA / centering ----

    def update_teacher(self) -> None:
        lam = self.cfg.teacher_ema
        with torch.no_grad():
            for p_t, p_s in zip(self.teacher.parameters(), self.student.parameters()):
                p_t.mul_(lam).add_(p_s.detach(), alpha=1 - lam)

    def update_center(self, batch_teacher_logits: torch.Tensor) -> None:
        with torch.no_grad():
            m = self.cfg.center_ema
            batch_mean = batch_teacher_logits.mean(dim=0)
            self.state.center.mul_(m).add_(batch_mean, alpha=1 - m)

    # ---- one step ----

    def step(
        self,
        student_inputs: dict[str, torch.Tensor],   # {"token_ids", "attention_mask"}
        teacher_inputs: dict[str, torch.Tensor],
        recon_targets: torch.Tensor,   # original token ids (before masking)
        recon_mask: torch.Tensor,      # bool: which positions were masked
    ) -> dict[str, float]:
        self.student.train()
        self.teacher.eval()

        s_out = self.student(
            student_inputs["token_ids"],
            student_inputs.get("attention_mask"),
        )
        with torch.no_grad():
            t_out = self.teacher(
                teacher_inputs["token_ids"],
                teacher_inputs.get("attention_mask"),
            )

        l_dino = self.dino_loss(s_out.projected, t_out.projected)
        l_recon = self.recon_loss(s_out.token_logits, recon_targets, recon_mask)
        loss = l_dino + self.cfg.recon_loss_weight * l_recon

        self.optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(self.student.parameters(), 1.0)
        self.optimizer.step()

        self.update_teacher()
        self.update_center(t_out.projected.detach())

        return {
            "loss": float(loss.detach().item()),
            "dino": float(l_dino.detach().item()),
            "recon": float(l_recon.detach().item()),
        }


# TODO: integrate a torch DataLoader built from windowizer.Window objects.
# Each iteration provides (global_views, local_views, recon_targets, recon_mask).
# Augmentation policy (object dropout, x/y jitter, color perm, crop) lives in
# a dedicated `augment.py` to be added in the next PR.
