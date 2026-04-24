# Encoder — Self-Supervised Style Representation

Designer 를 본격적으로 학습시키기 **전**, 기존 GD 레벨의 **스타일 표현(임베딩)** 을 먼저 확보하는 단계. 목적은 세 가지:

1. Planner 가 참고할 **스타일 벡터 `z_ref`** 를 추출 (retrieval / conditioning).
2. Designer 학습 시 **condition 신호** 로 사용 (classifier-free guidance 등 — [DESIGNER.md](DESIGNER.md) 참고).
3. **전환 영역**(한 스타일 → 다른 스타일 넘어가는 구간) 을 자동 탐지해 Designer 학습 데이터에서 제외 — 혼합 샘플이 학습을 노이즈로 만드는 문제 회피.

방법: **Bootstrap + iterative refinement.** 라벨 없음.

관련:
- [DESIGNER.md](DESIGNER.md) — 인코더를 소비하는 쪽 (z_ref 조건화, CFG)
- [DATA_FORMAT.md](DATA_FORMAT.md) — `SymbolicWindow` 스키마
- [ROADMAP.md](ROADMAP.md) — Phase 배치

---

## 0. 축 / 단위 확정

- **축**: GD x 좌표 (음악 시간 기반 아님).
- **단위**: GD 유닛 (1 유닛 = 30 px). 정수 또는 float.
- **음악 결합**: **Phase 5+** 로 연기 (§11 Future).
- **플레이어 속도 변화 / 포털 / STOP** 은 윈도우 단계에서 **무시** — 순수 x 좌표 기반. 향후 필요시 `x → player_time` 매핑을 보조로 사용 가능하나 MVP 에서는 고려하지 않음.

이 결정의 근거: 데코 스타일의 "시각적 밀집도" 는 레벨의 **공간적** 배치에 걸려있지 player 체류 시간에 걸려있지 않음. 같은 위치의 데코는 속도 느려도 빨라도 같은 데코.

---

## 1. 정의

기호:
- `N` — 레벨의 x축 길이 (유닛). `N = max_x - min_x`.
- `c` — 윈도우 반경 (유닛). **기본 `c = 30`** (블록 1개).
- `window_width = 2c = 60` 유닛 (블록 2개).
- `stride` — 윈도우 간격. **기본 `stride = 5`** 유닛 (오버랩 91.7%, DINO 용 data augmentation 밀도 확보).
- `v_n ∈ ℝ^d` — 지점 `n` 의 local 임베딩.
- `d` — latent 차원. **기본 `d = 256`**.

Encoder:
```
f : SymbolicWindow(n - c, n + c)  →  v_n ∈ ℝ^d
```

`SymbolicWindow` 의 구체 포맷은 §12 (Token sequence).

---

## 2. Prototype

레벨별 **스타일 대표 벡터 집합**:
```
P_level = { p_1, p_2, …, p_k } ⊂ ℝ^d
```

- 추출: 레벨 내 전체 `{v_n}` 에 **KMeans** 적용, centroid 를 prototype 으로. HDBSCAN 은 noise 분류 때문에 경계 탐지 안정성에 불리 → KMeans 를 기본.
- `k_level` 자동 결정: **elbow on inertia** 또는 고정 `k = 4` 로 시작해 경험적 조정. MVP 는 `k = 4`.
- Prototype 은 **레벨별**. 레벨간 비교할 때는 임베딩 자체로 하고 prototype 은 사용 안 함.

---

## 3. 경계 점수

Cosine distance:
```
d(u, v) = 1 - (u · v) / (||u|| · ||v||)
```

k=2 특수 경우 (prototypes a, b):
```
s(n) = d(v_n, a) + d(v_n, b)
```
`s(n)` peak 가 경계.

정규화:
```
s_norm(n) = s(n) / (d(a, b) + ε_numeric)
```

- `s_norm > 1` → `v_n` 이 a-b 축에서 이탈 (진짜 애매).
- `s_norm ≈ 1` → a-b 선분 위.
- `s_norm < 1` → 한 쪽에 가까움.

---

## 4. k 개 prototype — soft membership + entropy

Soft assignment (temperature `T`):
```
w_i(n) = exp( - d(v_n, p_i) / T )  /  Σ_j exp( - d(v_n, p_j) / T )
```

Entropy:
```
H_raw(n) = - Σ_i w_i(n) · log w_i(n)
```

**레벨간 비교를 위해 정규화**:
```
H(n) = H_raw(n) / log(k_level)   ∈  [0, 1]
```

- `H(n) = 1` 일 때 uniform (가장 애매) = 경계 후보.
- `H(n) = 0` 일 때 한 prototype 에 집중 = 확실한 소속.

Temperature 기본: **`T = 0.1`** (distance 대비 sharp 하게 → 전환 영역이 더 뚜렷이 드러남).

---

## 5. Boundary / Transition 추출

**Transition 후보 지점들**:
```
τ ∈ (0, 1),  예: τ = 0.7
Raw = { n ∈ [0, N] : H(n) > τ }
```

**Interval merge** (짧은 gap 병합):
```
merge_gap_g = 2  (units)
Transition = morphological_closing(Raw, g)
= { connected intervals after filling gaps ≤ g }
```

**단일 경계점 (local maxima 로 요약)**:
```
δ = 10  (units, 최소 boundary 간 간격)
B = { n : H(n) is local maximum in (n - δ, n + δ)  and  H(n) > τ }
```

**Transition 영역 vs Boundary 포인트** 의 관계:
- `Transition` = 구간 집합 (폭 있음) → 학습 데이터에서 제외할 때 사용.
- `B` = 단일 포인트 집합 (굵기 0) → IoU 수렴 체크, 외부 API 에 "이 레벨의 스타일 경계들" 로 노출할 때 사용.

---

## 6. 좌우 비교 (보완)

Entropy 는 gradual transition 에 강함. Sudden transition 에는 **좌우 임베딩 평균 차이** 가 더 민감:
```
L(n) = (1/w) · Σ_{i=1..w} v_{n - i·stride}
R(n) = (1/w) · Σ_{i=1..w} v_{n + i·stride}

s_LR(n) = d( L(n), R(n) )
```
기본 `w = 6` (좌우 각 30 units = 블록 1개 범위).

Ensemble:
```
s_final(n) = γ · H(n) + (1 - γ) · normalize(s_LR(n))
```
기본 `γ = 0.7`. `s_LR` 은 min-max 로 [0, 1] 정규화 후 결합.

`s_final` 이 최종 경계 점수. §5 의 피크 탐지는 `H` 대신 `s_final` 로 치환.

---

## 7. Intra / Inter — 품질 지표

구간 `S` 내 샘플 `{v_n}` 에 대해:
```
μ_S = (1/|S|) · Σ_{n ∈ S} v_n
intra_S = mean_{n ∈ S}  d(v_n, μ_S)         # 표준 silhouette 용
```

두 구간 `S_i, S_j`:
```
inter_{ij} = d(μ_{S_i}, μ_{S_j})
```

**표준 silhouette** (bulk 지표):
```
silhouette(n) = ( b(n) - a(n) ) / max( a(n), b(n) )
  where a(n) = mean distance to own-segment points
        b(n) = mean distance to nearest-other-segment points

level_score = mean_n silhouette(n)  ∈ [-1, 1]
```

- `level_score → 1` : 스타일 축이 잘 학습됨.
- `≈ 0` : 임베딩 공간이 무의미.
- 음수 : 엉킴 (collapse).

---

## 8. Pure 학습 데이터

Transition 영역의 **buffer 확장**:
```
T_buf = 3  (units)
Buffer_Transition = { n : ∃ m ∈ Transition, |n - m| ≤ T_buf }
```

Pure 구간:
```
Pure = [0, N] \ Buffer_Transition
```

v2 의 self-supervised 학습 샘플은 `Pure` 에서만 샘플링. v1 은 전체 `[0, N]` 에서 샘플링.

손실 추정: MVP 가정상 대략 **10~15%** 정도가 Buffer_Transition. (원 제안의 7% 는 낙관적.)

---

## 9. Bootstrap 반복

반복 구조:
```
f_0 : random init
train f_0 on naive windows (Pure == 전체)
for t = 1, 2, …:
    v_n ← f_{t-1}(window_n)  ∀ n
    P_level ← KMeans(v_n)
    H(n), s_final(n) ← §5~§6
    Transition_t, B_t ← boundary extraction
    Pure_t ← §8
    train f_t on Pure_t via DINO + aux recon
    if IoU_boundary(B_t, B_{t-1}) ≥ 0.9:
        converged.
```

**Boundary IoU with tolerance** (ε = 5 units):
```
match(n, B) = ∃ m ∈ B : |n - m| ≤ ε

TP = |{ n ∈ B_t : match(n, B_{t-1}) }|
FP = |B_t| - TP
FN = |{ m ∈ B_{t-1} : ¬ match(m, B_t) }|

IoU_boundary = TP / (TP + FP + FN)
```

**Transition interval IoU** (보조 지표, 같이 보고):
```
IoU_interval = |Transition_t ∩ Transition_{t-1}| / |Transition_t ∪ Transition_{t-1}|
```
(측정 단위: 유닛 길이)

**수렴 기준**: `IoU_boundary ≥ 0.9`. 2 iteration 연속 만족하면 stop.
**상한**: `t_max = 3` — v3 까지 수렴 안 하면 중단하고 원인 분석 (§14 리스크).

---

## 10. DINO 학습 loss

Student / teacher networks:
- Student `f_s`, projection head `g_s`, params `θ_s`.
- Teacher `f_t`, `g_t`, `θ_t` (EMA of student).
- Projection: `[CLS]` output → K 차원 softmax (`K = 65536` 기본 DINO).

Per-window 의 augmented views:
- **Global views** (`x_g`) — 윈도우 폭 60 units 전부.
- **Local views** (`x_l`) — crop: 30 units 만, 내부 위치 랜덤.
- Multi-crop: global 2개 + local 4개 기본.

분포:
```
p_s(x) = softmax( g_s(f_s(x)) / τ_s )
p_t(x) = softmax( ( g_t(f_t(x)) - c_center ) / τ_t )
```
- `τ_s = 0.1`, `τ_t = 0.04` 기본.
- `c_center` = centering vector (EMA).

Loss (student → teacher 모방):
```
L_dino = Σ_{x_g ∈ G} Σ_{x ∈ V, x ≠ x_g}  H( p_t(x_g), p_s(x) )
       where H(a, b) = - Σ a_i · log b_i
             V = all views (global + local)
```

Teacher EMA:
```
θ_t ← λ · θ_t + (1 - λ) · θ_s,   λ = 0.996
```

Centering:
```
c_center ← m · c_center + (1 - m) · (1/B) · Σ_{x ∈ batch} g_t(f_t(x))
          m = 0.9
```

**보조 복원 loss** (collapse 방지 + 낮은 레벨 피처 보강):
```
L_recon = cross_entropy( token_logits, masked_token_targets )
L_total = L_dino + α · L_recon,  α = 0.3
```
Masking: 윈도우 토큰의 15% 를 `[MASK]` 로 대체, 원본 예측. BERT 스타일.

---

## 11. Token sequence (Symbolic 표현)

Encoder 입력 포맷. `SymbolicWindow` = 윈도우 하나의 표현.

### 11.1 토큰 구성

윈도우 내 각 오브젝트가 **연속 토큰 블록** 으로:
```
[OBJ_BEGIN] KIND_ID  X_BUCKET  Y_BUCKET  ROT_BUCKET  SCALE_BUCKET  COLOR_BUCKET  [OBJ_END]
```

다수 오브젝트가 나열되면:
```
[WINDOW] ... [OBJ_BEGIN] ... [OBJ_END] [OBJ_BEGIN] ... [OBJ_END] ... [WINDOW_END] [CLS]
```

정렬: 오브젝트를 **x 오름차순**, 동률이면 y 오름차순, 동률이면 id 오름차순. 결정적 순서 중요 (DINO 에 invariance 주입).

### 11.2 Vocab

| Token group | Cardinality | Notes |
|---|---|---|
| Special (`[WINDOW]`, `[CLS]`, `[OBJ_BEGIN]`, `[OBJ_END]`, `[MASK]`, `[PAD]`, `[WINDOW_END]`) | 7 | 고정 |
| KIND_ID | ~9 | `ObjectKind` enum 값 (BLOCK_SOLID, SPIKE, …, DECORATION) |
| GameObjectType direct | ~47 | 옵션: kind 대신 raw GameObjectType. `encoder/tokenizer.py` 에서 플래그로 전환 |
| X_BUCKET | 60 | 윈도우 내 상대 x: `[-c, +c]` 를 60 등분 (1 유닛 = 1 bucket) |
| Y_BUCKET | 32 | y 범위 `[0, 960px]` = `[0, 32 units]` 를 32 등분. 레벨 최대 y 는 보통 32 units 이내 |
| ROT_BUCKET | 8 | 0°, 45°, 90°, …, 315° |
| SCALE_BUCKET | 8 | log 스케일 `0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0` 로 양자화 |
| COLOR_BUCKET | 33 | 기본 채널 0~30, + "default", + "custom" |

**Vocab 총 ≈ 7 + 47 + 60 + 32 + 8 + 8 + 33 ≈ 195.** 단일 shared vocab 또는 **group-separated embeddings** 중 후자를 권장 (각 group 에 별도 embedding, concat 또는 sum). MVP 는 단일 shared vocab (간단).

### 11.3 최대 길이

윈도우당 오브젝트 수 상한 `N_obj_max = 128`.
- 토큰 수 ≤ `1 (window) + 128 * 8 + 1 (window_end) + 1 (cls) = 1027`.
- 초과 시 truncate (x 기준 가까운 순서로).

Transformer max_seq_len = 1024 에 맞추기 위해 `N_obj_max = 127` 로 조정 가능.

### 11.4 결정 사항

- 토큰 group 은 **shared vocab** 로 시작 (MVP). v3 이후 group-embedding 로 실험.
- MASK 는 단일 token 단위 (전체 OBJ 블록 마스킹 아님). 이유: 블록 전체 마스킹은 DINO local view 랑 역할 중복.
- Positional embedding: 표준 sinusoidal. 상대 위치는 X_BUCKET 토큰이 이미 표현하므로 rotary 불필요.

---

## 12. 좌우 비교 보완 (§6 의 구현 결정)

- `w = 6`: 좌우 각각 6 샘플 평균, stride 5 units → 좌우 30 units 범위.
- `s_LR` 정규화: level 전체 분포의 `[p5, p95]` 로 clip 후 min-max.

---

## 13. 모델 사양 (MVP)

| Hyperparam | 값 | 비고 |
|---|---|---|
| Backbone | Transformer encoder | |
| Layers | 4 | MVP; v3 에서 6~8 로 |
| d_model | 256 | |
| heads | 8 | |
| ffn | 1024 | 4× d_model |
| dropout | 0.1 | |
| max_seq_len | 1024 | §11.3 |
| Vocab | 195 (shared) | §11.2 |
| Output latent dim | 256 (= d_model) | [CLS] 벡터 직접 사용 |
| Projection head (DINO) | MLP 3 layer, out=65536 | |
| Params (추정) | ~5M | |

학습:
- Batch size (effective): 256
- Optimizer: AdamW, lr=5e-4, weight_decay=0.04
- Warmup: 10% of steps
- Scheduler: cosine
- Epochs: 100 (v1), 50 (v2, v3)
- Hardware: GPU 권장 (1x A10 / RTX 4090 급). CPU 도 가능 (느림).

---

## 14. 리스크와 완화

| 리스크 | 완화 |
|---|---|
| DINO collapse (모든 임베딩 동일) | centering + aux recon loss + 학습률 warmup |
| Cluster 불안정 (k 설정 민감) | k=4 고정 시작, elbow 로 자동 튜닝은 v3 |
| Entropy peak 가 의미없는 곳 | 수동 라벨 10 레벨 준비, `level_score` (silhouette) 동시 모니터 |
| IoU 수렴 안 함 (v3 에서도) | (a) augmentation 재검토, (b) τ, T 튜닝, (c) N_obj_max 상향 |
| 짧은 레벨 (N < 120 units) | window 수 적어 학습 샘플 부족 → 제외 또는 데이터 증강 |
| 포털/속도 변화 | MVP 에서는 무시. Phase 5 에서 player_time 축 실험 |
| 오브젝트 수 많은 레벨 (2000+) | N_obj_max truncation 빈도 측정 → vocab 늘리거나 윈도우 폭 조정 |

---

## 15. Bootstrap 의사코드

```python
def bootstrap_encoder(levels, max_iters=3, iou_target=0.9):
    # --- v0: warmup ---
    f = init_encoder()
    train_dino_aux(f, windows_from(levels, pure=None))  # 전체 사용

    prev_B = None
    for t in range(1, max_iters + 1):
        # inference
        embeds = {lvl: [f(w) for w in windows_from(lvl)] for lvl in levels}

        # boundary extraction
        all_B = []
        all_T = []
        for lvl in levels:
            protos = kmeans(embeds[lvl], k=4)
            H = normalized_entropy(embeds[lvl], protos, T=0.1)
            s_LR = left_right_score(embeds[lvl], w=6)
            s = 0.7 * H + 0.3 * minmax(s_LR)

            T_raw = {n: s[n] > 0.7}
            Transition = morphological_close(T_raw, gap=2)
            B = local_maxima(s, delta=10, thresh=0.7)

            all_B.append(B); all_T.append(Transition)

        # pure filtering
        pure_windows = []
        for lvl, T in zip(levels, all_T):
            buf = expand(T, T_buf=3)
            pure = complement(buf, [0, N_lvl])
            pure_windows.extend(windows_in(lvl, pure))

        # retrain
        f = init_encoder()        # 재초기화 권장 (or continue training)
        train_dino_aux(f, pure_windows)

        # convergence
        if prev_B is not None:
            iou = boundary_iou(all_B, prev_B, epsilon=5)
            if iou >= iou_target:
                return f, all_B, all_T
        prev_B = all_B

    return f, all_B, all_T   # not converged, return best-effort
```

---

## 16. 기호 요약표

| 기호 | 의미 | 기본값 |
|---|---|---|
| `N` | 레벨 x축 길이 (units) | per-level |
| `c` | 윈도우 반경 (units) | 30 |
| `stride` | 윈도우 간격 (units) | 5 |
| `d` | 임베딩 차원 | 256 |
| `v_n` | 지점 n 의 local 임베딩 | — |
| `f` | encoder | — |
| `P_level` | 레벨 prototype 집합 | size=4 |
| `k_level` | 레벨 prototype 개수 | 4 |
| `T` | soft membership temperature | 0.1 |
| `w_i(n)` | prototype i 에 대한 soft 소속도 | — |
| `H(n)` | 정규화 엔트로피 (∈ [0,1]) | — |
| `τ` | transition threshold | 0.7 |
| `δ` | local maxima 최소 간격 (units) | 10 |
| `g` | interval merge gap (units) | 2 |
| `T_buf` | transition buffer (units) | 3 |
| `ε` | boundary matching tolerance (units) | 5 |
| `γ` | H / s_LR ensemble weight | 0.7 |
| `w` (LR) | 좌우 평균 윈도우 크기 | 6 |
| `α` | L_recon 가중치 | 0.3 |
| `λ` | teacher EMA | 0.996 |
| `τ_s, τ_t` | student / teacher softmax temperature | 0.1 / 0.04 |
| `t_max` | bootstrap 상한 | 3 |
| `iou_target` | 수렴 기준 | 0.9 |

---

## 17. Future (이번 MVP 범위 밖)

- **음악 / 오디오 결합** — `H_combined = β H + (1-β) H_music`, `H_music = α_1 · struct + α_2 · novelty + α_3 · onset`. Phase 5+ 에서 `ml/src/gd_designer/audio/` 신설.
- **Player-time 축** — 속도/포털 반영. MVP 이후 실험.
- **Group-embedding** — §11.4, shared vocab 과 A/B.
- **HDBSCAN** — KMeans 대안, noise 분류로 cluster 선명화.
- **Retrieval** — 학습 후 `z_ref` 를 사용자 선택 레벨의 centroid 로 뽑는 UX — [DESIGNER.md](DESIGNER.md) 에서 다룸.

---

## 18. 관련 파일 (구현)

```
ml/src/gd_designer/encoder/
├── tokenizer.py      # Layout/Window → token ids (§11)
├── windowizer.py     # 레벨 전체 → stride 윈도우 리스트 (§1)
├── model.py          # Transformer + DINO head (§13)
├── trainer.py        # DINO + aux recon loss + EMA (§10)
├── prototypes.py     # KMeans + soft membership (§2, §4)
├── boundary.py       # H, s_LR, peak, interval merge (§5, §6)
├── refine.py         # bootstrap loop + IoU 체크 (§9, §15)
└── metrics.py        # silhouette, IoU, collapse detectors (§7)

ml/scripts/
├── train_encoder.py          # 단일 iteration 학습
├── bootstrap_encoder.py      # §15 반복 전체
└── evaluate_encoder.py       # silhouette, boundary 시각화
```

테스트는 `ml/tests/encoder/` 에 대응 파일.
