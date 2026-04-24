# Designer — Learned Decoration Model

Designer 는 `Layout` + `PlannerOutput` 을 받아 `DecorationOp[]` 을 반환하는 모델이다. 프로젝트의 **중심 R&D 산출물**. Phase 4 에 집중.

관련:
- [PLANNER.md](PLANNER.md) — 상위에서 내려오는 힌트
- [DATA_FORMAT.md](DATA_FORMAT.md) — 입출력 타입
- [ROADMAP.md Phase 4](ROADMAP.md#phase-4--learned-designer-mvp) — 마일스톤

---

## 1. 문제 정의

### 1.1 입출력

- **입력:** `Layout` (게임플레이 오브젝트 N개) + `PlannerOutput` (테마/밀도/세그먼트)
- **출력:** `DecorationOp[]` (데코 오브젝트 M개, M 은 밀도 * bbox 면적 에 대략 비례)

### 1.2 왜 어려운가

- **출력 차원이 가변** — M 은 입력마다 다름. 표준 회귀/분류 포맷 안 맞음.
- **구조화 출력** — 각 op 은 (id, x, y, rot, z, color, scale) 7 필드, 타입 다름.
- **정답이 다수** — 같은 Layout 에 "좋은 데코" 는 여러 개. 단순 MSE 로는 안 됨.
- **미적 품질** — 수치 지표만으로 충분히 잡히지 않음.

### 1.3 좋은 데코의 조건 (암묵지)

- 게임플레이를 가리지 않음 (zOrder, 위치)
- 테마에 일관됨 (팔레트, 모티프)
- 밀도가 구간별로 의미 있게 변함
- 반복 느낌 없이 변주
- GD 사용자의 "감각" 과 일치

---

## 2. 접근 후보 3가지

### 2.1 (MVP) Supervised Learning on Object Sequences

**아이디어:** 레이아웃을 prefix, 데코를 target sequence 로 두고 **autoregressive 생성**. Transformer decoder.

- Input tokenization:
  - Layout object 1개 = 토큰 ~8개 (kind, x_bucket, y_bucket, rot_bucket, …)
  - Planner output = 토큰 ~30개 (theme, palette, segments)
  - Special tokens: `<SEP>`, `<BEGIN_DECO>`
- Output tokenization:
  - DecorationOp 1개 = 토큰 ~8개 (id, x_bucket, y_bucket, rot_bucket, z, color, scale, `<END_OP>`)
  - 전체 시퀀스 끝 `<END>`

**장점:**
- 아키텍처가 성숙 (LLM 바디 재활용 가능).
- Autoregressive 특성상 이전 op 보고 다음 op 결정 → 자연스러운 연출.
- 가변 길이 출력 자연 처리.

**단점:**
- 긴 시퀀스 → 속도 느림.
- 좌표 이산화 (bucket) 로 정밀도 손실.
- 학습 데이터 많이 필요.

**시작 권장 이유:** 가장 낮은 리스크. 결과가 평이하더라도 "동작"은 함.

### 2.2 Diffusion on 2D Grid

**아이디어:** 레벨 bbox 를 coarse 2D 그리드 (예: 128×32) 로 나누고, 각 셀에 "이 셀에 어떤 데코가 얼마나" 의 멀티채널 tensor. UNet 으로 denoising.

- Input conditioning:
  - Gameplay grid (같은 128×32 mask)
  - Theme/density embedding (class-conditional)
- Output:
  - `(C, H, W)` where C = 주요 데코 kind 수
  - 각 셀의 확률 → sampling → op list 화

**장점:**
- 고해상도 공간 분포 자연스러움.
- Diffusion 생태계 (U-Net, scheduler, classifier-free guidance) 활용.
- 한 방에 전체 레벨 병렬 샘플링.

**단점:**
- 개별 op 의 정확한 좌표/회전/색 복원이 어려움 (second stage decoder 필요).
- GD 의 오브젝트는 grid-free 이라 rasterization loss.

**가치:** Phase 4 후반 실험. 2.1 로 베이스라인 잡은 후 비교.

### 2.3 RL with Environment Sim

**아이디어:** Policy 가 한 번에 op 1개 배치. 환경은 현재까지 배치된 상태 + plan.
- State: 게임플레이 mask + 현재 데코 상태 + plan embedding
- Action: (id, x, y, rot, z, color, scale) — 연속+이산 혼합
- Reward: 미적 스코어 (학습된 discriminator) + 밀도 목표 일치 + 겹침 penalty + 종료 보상

**장점:**
- 명시적 목적함수 설계 가능.
- "겹침 금지" 같은 하드 제약을 reward shaping 으로 학습.

**단점:**
- Reward 설계 어려움 (미적은 주관).
- 긴 에피소드 (수백 스텝) → 샘플 효율 낮음.
- GD 상호작용 자동화가 어려워 시뮬레이터를 별도로 만들어야 함.

**가치:** 탐색 가치 있음. 하지만 MVP 는 2.1 로 간다.

---

## 3. MVP 계획 — 2.1 지도학습 상세

### 3.1 데이터

**원천:**
- 공개된 유명 레벨 (creator 100+). `.gmd2` 또는 `.gmd` 포맷.
- 최소 100 레벨 → 데이터 증강 후 ~100k 학습 쌍 목표.

**파싱:**
- `ml/src/gd_designer/data/collect.py`
- GD 레벨 포맷 → 오브젝트 리스트 (id, x, y, rot, ...)
- `ObjectKind` 기준으로 layout(gameplay) vs decoration 분리.
- 문제점: 동일 오브젝트 id 가 상황에 따라 deco 로도 layout 으로도 쓰임 → Phase 4 중반에 refining 필요.

**증강:**
- 수평 시프트 (x 평행이동)
- 밀도 perturbation (랜덤 일부 데코 제거 → fewer-shot 강제)
- 색 채널 셔플 (테마 일관성 유지 선에서)

**포맷:**
- `data/processed/train.jsonl` — 각 줄이 `{layout_summary, plan_inferred, target_ops}`.
- `plan_inferred` 는 **학습 시엔** 원본 레벨에서 휴리스틱으로 추출한 테마/팔레트/밀도.

### 3.2 모델 아키텍처 (기본안)

```
Inputs:
  tokens: [B, T_in]   # layout + plan 인코딩
Outputs:
  next_token: [B, T_in]  # teacher forcing
  generate:   [B, T_out] # autoregressive

Architecture:
  - Token embedding (vocab_size=~2000)
  - 8-layer transformer decoder (d_model=512, heads=8, ffn=2048)
  - LM head

Params: ~50M
```

- Vocab 구성:
  - ObjectKind 10종
  - GD object id (deco 한정 ~200종)
  - 좌표 bucket (x: 1024 buckets 전체 레벨 길이 기준, y: 256)
  - rotation bucket (16)
  - color channel (빈번 상위 20)
  - scale bucket (8)
  - theme (6)
  - palette tokens (컬러 ids 직접)
  - special tokens (`<SEP>`, `<BEGIN_DECO>`, `<END_OP>`, `<END>`, `<PAD>`)

### 3.3 학습

- Cross-entropy (next token).
- Loss masking: layout 부분은 학습 X, deco 부분만 학습.
- Optimizer: AdamW, lr=3e-4, warmup 1000 steps.
- Batch: gradient accumulation 으로 effective 64.
- Epochs: 100 (MVP)
- Framework: PyTorch + Hydra configs.
- `ml/scripts/train.py` + `ml/src/gd_designer/train/trainer.py`.

### 3.4 추론

- Greedy 또는 top-k sampling (k=20, temperature=0.8).
- 종료: `<END>` 토큰 또는 max_ops=5000.
- Decoding:
  - Generated token sequence → parse 하여 `DecorationOp[]`.
  - 검증: bbox 이내, id 유효, scale 범위.
  - 실패한 op 은 스킵.

### 3.5 배치

- FastAPI 서버 로딩 시 체크포인트 로드 (CPU 또는 CUDA).
- GPU 없으면 CPU fallback (속도 ~30s/레벨).
- ONNX 내보내기는 Phase 5 고려 (모드 내장 목적).

---

## 4. 평가 (Evaluation)

모델 없이 룰베이스 대비 **개선됨** 을 증명해야 Phase 4 끝.

### 4.1 지표

**자동 지표 (`ml/src/gd_designer/eval/metrics.py`):**

| 지표 | 공식 / 설명 |
|---|---|
| `density_delta` | \|실제 밀도 - plan.density\| |
| `gameplay_overlap` | 데코 중 게임플레이 bbox 와 겹치는 비율 |
| `kind_diversity` | 고유 데코 id 수 / 총 op 수 (높을수록 덜 반복) |
| `spatial_fill` | bbox 의 각 grid 셀 중 데코가 있는 비율 |
| `palette_consistency` | 사용된 color channel 중 plan.palette 에 속한 비율 |
| `fid_like` | 학습된 encoder 의 출력 분포 vs GT 분포 거리 (Phase 4 후반) |

### 4.2 수동 평가

- 20개 레이아웃 선정 (다양한 길이/테마).
- 각 레이아웃에 대해:
  - GT (원본 레벨의 실제 데코)
  - Rule-based Designer 출력
  - 학습 모델 출력
- 평가자가 블라인드로 랭크. Elo 또는 Bradley-Terry.

### 4.3 End-to-end 플레이 감각

- 최종 5개 레벨에 대해 실제 에디터에 apply → 재생 → "플레이할 만한가" 주관 평가.

---

## 5. 베이스라인 (Baselines)

학습 모델을 평가하려면 비교 기준 필요:

1. **Rule-based** — 현재 mod 의 `RuleBasedStrategy`.
2. **Nearest-neighbor** — Layout summary embedding 으로 학습 데이터에서 가장 비슷한 것 검색 → 그 레벨의 deco 를 레이아웃에 맞춰 warping 하여 복사. 간단하지만 강력한 베이스라인.
3. **Random** — 균등 분포로 `plan.density` 만큼 무작위 배치.

셋 다 `models/baselines/` 에 구현.

---

## 6. 실험 관리

### 6.1 설정

Hydra configs `ml/src/gd_designer/train/configs/`:
```
configs/
├── model/
│   ├── transformer_small.yaml
│   ├── transformer_base.yaml
│   └── transformer_large.yaml
├── data/
│   ├── v1_small.yaml
│   └── v1_full.yaml
├── optim/
│   ├── default.yaml
│   └── fast_lr.yaml
├── train/
│   └── default.yaml
└── config.yaml
```

### 6.2 실행

```bash
uv run python scripts/train.py \
  model=transformer_base \
  data=v1_full \
  optim=default \
  train.max_epochs=100
```

Output: `runs/{timestamp}_{tag}/`:
```
runs/20260601_120000_base_v1/
├── config.yaml  # 머지된 전체 설정
├── checkpoints/
├── logs/
├── eval/
└── samples/
```

### 6.3 추적

- W&B 또는 로컬 CSV (Phase 4 초반: 로컬 CSV 로 시작, 후반에 W&B).
- 각 실험 태그는 `{date}_{model_size}_{data_version}_{note}`.

---

## 7. 체크포인트 관리

- `runs/*/checkpoints/` 에 epoch 마다 저장.
- 각 체크포인트에 대응하는 `config.yaml` 를 체크포인트 디렉토리에 복사 (재현성).
- "프로덕션" 체크포인트는 별도 심볼릭 링크: `checkpoints/latest`.
- FastAPI 서버는 `checkpoints/latest` 를 로드.
- 버전 태그: `checkpoints/v0.1.0/` 같은 디렉토리에 모델 + config + README (학습 조건, eval 결과).

---

## 8. 데이터 윤리 / 라이선스

- 공개 레벨은 creator 이름과 원본 링크를 데이터셋 메타에 기록.
- 대규모 수집 전 GD 커뮤니티 관례 존중 (학습 반대 명시한 creator 제외 등).
- 공식 릴리즈 전 데이터 정책 문서화 필요 (`docs/DATA_POLICY.md`).

---

## 9. 미래 방향

### 9.1 2-stage

- Stage 1: Autoregressive → 대략 op 시퀀스
- Stage 2: Diffusion refinement (저해상도 → 고해상도 좌표 보정)

### 9.2 Controllable

- Classifier-free guidance 로 "좀 더 빽빽하게" 같은 조정.
- LoRA 로 테마별 어댑터.

### 9.3 Interactive

- 사용자가 일부 op 을 고정하고 나머지를 모델이 채우도록 (in-painting 유사).

---

## 10. 리스크와 완화

| 리스크 | 완화 |
|---|---|
| 학습 데이터 부족 | 증강 + NN 베이스라인이 강해 Phase 4 MVP 목표 낮춤 |
| 학습 불안정 (긴 시퀀스 GPT) | clip grad, small lr, warm-up, 작은 batch |
| 추론 느림 | MVP 는 vocab 작게, 레이어 얕게 |
| eval 지표 부재 | 수동 평가 + NN 베이스라인 차이로 1단계 판단 |
| GD 포맷 파싱 난해 | 기존 오픈소스 툴 (Eclipse, gdShare) 참고 |

---

## 11. Phase 4 내 마일스톤 (서브)

1. **데이터 파이프라인** (1주) — 10 레벨 → 파싱 → jsonl 확인.
2. **베이스라인 (NN)** (0.5주) — NN 베이스라인이 룰베이스보다 좋은 것 확인.
3. **Tokenizer** (0.5주) — vocab 구성 + 양방향 변환 테스트.
4. **MVP 학습** (2주) — transformer_small 에 100 레벨로 overfit 확인.
5. **Scale up** (1주) — 데이터 확장, transformer_base, full 학습.
6. **평가 루프** (1주) — 수동 평가 20샷 + 자동 지표 대시보드.
7. **서빙** (0.5주) — 체크포인트 로드, `/design` 연결.
8. **iterate** — 결과 보고 가장 약한 지점 1~2개 개선.

---

## 12. 참고 / 영감

- **자동 레벨 디자인 관련 논문** (후보):
  - "Procedural Content Generation via Machine Learning" (PCGML) 서베이
  - Mario PCGML 연구들 (텍스트 기반 시퀀스 생성)
  - GANSpace for games
- **GD 내부:**
  - 공식 에디터 오브젝트 id 표 (GD 위키)
  - 유명 creator 튜토리얼 (데코의 "원칙")
- **내부 문서:** PLANNER.md, DATA_FORMAT.md
