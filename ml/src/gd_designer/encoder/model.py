"""Symbolic Transformer encoder + DINO projection head (ENCODER.md §13).

Deliberately small (~5M params) so v1 trains on a single consumer GPU within
hours. Downstream we expose the [CLS] hidden state as the 256-d latent.

Skeleton: types and shapes are correct; actual forward pass is not yet wired
to a dataloader (that lands with trainer.py).
"""
from __future__ import annotations

from dataclasses import dataclass

import torch
import torch.nn as nn
import torch.nn.functional as F

from .config import EncoderConfig


@dataclass
class EncoderOutput:
    cls_latent: torch.Tensor      # [B, latent_dim]
    token_logits: torch.Tensor    # [B, T, vocab_size]  — for aux recon
    projected: torch.Tensor       # [B, dino_head_dim]   — DINO head output


class SymbolicTransformer(nn.Module):
    """Single-view backbone. Shared by student and teacher."""

    def __init__(self, cfg: EncoderConfig):
        super().__init__()
        self.cfg = cfg

        self.token_embed = nn.Embedding(cfg.vocab_size, cfg.d_model, padding_idx=0)
        self.pos_embed = nn.Embedding(cfg.max_seq_len, cfg.d_model)

        enc_layer = nn.TransformerEncoderLayer(
            d_model=cfg.d_model,
            nhead=cfg.n_heads,
            dim_feedforward=cfg.ffn_dim,
            dropout=cfg.dropout,
            activation="gelu",
            batch_first=True,
            norm_first=True,
        )
        self.encoder = nn.TransformerEncoder(enc_layer, num_layers=cfg.n_layers)

        self.norm = nn.LayerNorm(cfg.d_model)

        # Aux reconstruction head — shares token embedding matrix (tied).
        self.recon_head = nn.Linear(cfg.d_model, cfg.vocab_size, bias=False)

    def forward(
        self,
        token_ids: torch.Tensor,            # [B, T] int
        attention_mask: torch.Tensor | None = None,  # [B, T] bool (True = valid)
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """Return (per-token hidden states [B,T,d], cls hidden [B,d]).

        Convention: the [CLS] token is the *last* non-pad token in each sequence
        (see tokenizer.encode_window). We pull it by scanning the mask.
        """
        B, T = token_ids.shape
        pos = torch.arange(T, device=token_ids.device).unsqueeze(0).expand(B, T)
        h = self.token_embed(token_ids) + self.pos_embed(pos)

        key_padding_mask = None
        if attention_mask is not None:
            # PyTorch wants True for PAD (ignored), not valid
            key_padding_mask = ~attention_mask

        h = self.encoder(h, src_key_padding_mask=key_padding_mask)
        h = self.norm(h)

        # Locate the CLS per batch element
        if attention_mask is not None:
            # last valid position index
            last_idx = attention_mask.long().sum(dim=1) - 1  # [B]
        else:
            last_idx = torch.full((B,), T - 1, device=h.device, dtype=torch.long)
        cls = h[torch.arange(B, device=h.device), last_idx]  # [B, d_model]
        return h, cls


class DINOHead(nn.Module):
    """3-layer MLP + weight-normalized linear, as in DINOv1."""

    def __init__(self, in_dim: int, out_dim: int, hidden_dim: int = 512, bottleneck: int = 256):
        super().__init__()
        self.mlp = nn.Sequential(
            nn.Linear(in_dim, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, bottleneck),
        )
        self.last = nn.utils.weight_norm(nn.Linear(bottleneck, out_dim, bias=False))
        # Freeze the gain of the weight_norm so that training is stable (DINO trick).
        self.last.weight_g.data.fill_(1.0)
        self.last.weight_g.requires_grad = False

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.mlp(x)
        x = F.normalize(x, dim=-1)
        return self.last(x)


class EncoderModel(nn.Module):
    """Backbone + DINO projection + aux recon head wired together."""

    def __init__(self, cfg: EncoderConfig):
        super().__init__()
        self.cfg = cfg
        self.backbone = SymbolicTransformer(cfg)
        self.dino_head = DINOHead(cfg.d_model, cfg.dino_head_dim)

    def forward(
        self,
        token_ids: torch.Tensor,
        attention_mask: torch.Tensor | None = None,
    ) -> EncoderOutput:
        per_token, cls = self.backbone(token_ids, attention_mask)
        return EncoderOutput(
            cls_latent=cls,
            token_logits=self.backbone.recon_head(per_token),
            projected=self.dino_head(cls),
        )

    @torch.no_grad()
    def embed(self, token_ids: torch.Tensor, attention_mask: torch.Tensor | None = None) -> torch.Tensor:
        """Inference helper: returns the CLS latent only."""
        self.eval()
        _, cls = self.backbone(token_ids, attention_mask)
        return cls
