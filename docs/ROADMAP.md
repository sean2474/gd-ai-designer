# Roadmap

이 문서는 프로젝트를 **6개 Phase** 로 나눠, 각 단계의 목표·산출물·종료 기준·예상 기간을 기술한다. Phase 종료는 체크리스트가 모두 체크됐을 때로 정의한다.

큰 그림: **룰베이스 → 구조 분리 + LLM 플래너 → 스타일 인코더 학습 → 학습된 디자이너 → 릴리즈.**

## 마일스톤 요약

| Phase | 주제 | 종료 기준 한 줄 | 예상 |
|---|---|---|---|
| 1 | Rule-based end-to-end in-process | 에디터에서 Design 누르면 데코 배치 | ✅ 완료 (2026-04-23) |
| 2 | Architecture refactor + test harness + ml stub | mod/core 분리, Catch2/pytest, ml 서버 스텁 | 1~2주 |
| 3 | LLM Planner integration | Anthropic 호출로 테마/밀도 자동 결정 | 1~2주 |
| **4** | **Self-supervised Style Encoder** | **Bootstrap encoder 가 IoU ≥ 0.9 수렴, silhouette > 0.3** | **3~5주** |
| 5 | Learned Designer (MVP) | 지도학습 / 확산 모델이 룰베이스보다 나은 데코 (인코더 조건화) | 4~8주 |
| 6 | Beta release | 외부 사용자가 공개 GD 모드로 사용 | +N |

Phase 4 는 Designer 학습 전에 **레벨의 스타일 표현(임베딩)** 을 먼저 확보하기 위해 신설. 자세한 설계는 [ENCODER.md](ENCODER.md).

아래 각 Phase 상세.

---

## Phase 1 — Rule-Based End-to-End ✅

**완료: 2026-04-23**

### 목표

GD 에디터 안에서 사용자가 버튼 한 번 누르면 데코가 추가되는 **파이프라인 전체** 를 최소 구현으로 검증.

### 산출물

- [x] Geode 모드 스켈레톤 (`mod.json`, CMakeLists, main.cpp)
- [x] `MenuLayer` 대신 `EditorUI` 훅 + "Design" 버튼
- [x] `LayoutReader` — 에디터의 `m_objects` 이터레이트 → 좌표/id 수집
- [x] `RuleBasedStrategy` — 하드코딩 규칙으로 데코 op 생성
- [x] `DecorationApplier` — `createObject` 로 데코 배치
- [x] GD 2.2081 / Geode 5.6.1 / macOS 빌드 성공

### 종료 기준

- [x] 에디터에서 Design 버튼 클릭 시 데코 생성 관찰
- [x] Ctrl+Z 로 되돌리기 가능 (단일 undo)
- [x] GD 크래시 없음

### 교훈 / 남은 숙제 (Phase 2 로 인계)

- `Designer.cpp` 에 모든 책임이 섞여있음 → 레이어 분리 필요.
- `ObjectKind` 개념 없음 → 현재 하드코딩된 id 체크. 카탈로그 도입 필요.
- 테스트 없음 → Catch2 도입.
- CMake deployment target 이슈 경고 없앰 (11.0 으로).

---

## Phase 2 — Refactor + Test Harness + ML Stub

**예상 1~2주. 병렬 진행 가능.**

### 목표

Phase 1 의 검증된 파이프라인을 **유지하면서**, 2인 협업이 가능한 구조로 재편 + ML 서버 쪽 스텁까지 준비해서 Phase 3 시작 즉시 붙이기 가능하게.

### 산출물

**mod 리팩토링**
- [ ] `mod/src/core/` — Layout, DecorationOp, Strategy, ObjectIDs, Geometry (Geode 무의존)
- [ ] `mod/src/strategies/RuleBasedStrategy` — 기존 로직 이전
- [ ] `mod/src/gd/` — LayoutReader, DecorationApplier, EditorContext
- [ ] `mod/src/ui/EditorButton` — 버튼만 별도 파일
- [ ] `mod/src/config/Settings` — mod.json settings 스키마 정의 + C++ 래퍼
- [ ] `mod/src/util/Log` — 로그 매크로

**테스트**
- [ ] Catch2 통합 (CPM 으로)
- [ ] `mod/tests/core/Layout_test.cpp` — 빈 layout, 단일, 다수
- [ ] `mod/tests/strategies/RuleBasedStrategy_test.cpp` — bbox 불변식, 결정성
- [ ] `mod/tests/core/ObjectIDs_test.cpp` — 카탈로그 완전성
- [ ] CI (GitHub Actions macOS) — 빌드 + 테스트 자동 실행

**ml 스켈레톤**
- [ ] `ml/pyproject.toml` (uv)
- [ ] `ml/src/gd_designer/data/schema.py` — LayoutObject, Layout, DecorationOp (pydantic)
- [ ] `ml/src/gd_designer/data/object_ids.py` — 카탈로그
- [ ] `ml/src/gd_designer/serve/api.py` — FastAPI `/design` (스텁: 룰 비슷하게 뿌리기)
- [ ] `ml/src/gd_designer/serve/inference.py` — placeholder
- [ ] `ml/tests/` — pydantic round-trip, API smoke

**mod ↔ ml 연결**
- [ ] `mod/src/net/DesignerClient` — libcurl 래퍼 (Geode arc/Future 기반)
- [ ] `mod/src/strategies/RemoteStrategy` — DesignerClient 사용
- [ ] `mod/src/config/Settings` 에 `strategy` 옵션 노출 (rule_based | remote)
- [ ] Fixture 기반 contract test (양쪽)

**문서/프로세스**
- [x] docs/ 1차 초안 (INTERFACES, DATA_FORMAT, MOD_API, ARCHITECTURE 등)
- [ ] GitHub Actions CI
- [ ] PR 템플릿 (COLLABORATION §2.4)

### 종료 기준

- [ ] mod 빌드 + 테스트 자동화 통과
- [ ] ml 서버 로컬 기동 + /design 스텁 응답
- [ ] mod 에서 `strategy=remote` 설정 시 서버 호출 → 데코 배치 작동
- [ ] Contract test 양쪽 통과
- [ ] Phase 3 진입 합의 (회고 이슈)

### 리스크 / 해결책

| 리스크 | 완화 |
|---|---|
| libcurl Geode 통합 복잡 | Geode 내장 HTTP (`web::WebRequest`) 우선 검토 |
| arc::Task 사용 미숙 | Geode 공식 예제 모드 참조 (gdshare 등) |
| 빌드시간 증가 | ccache 재도입 시도 |

---

## Phase 3 — LLM Planner Integration

**예상 1~2주.**

### 목표

Designer 는 여전히 룰베이스지만, "어떤 테마/밀도/구간으로 갈지" 는 LLM 이 결정. 이미 `/design` 파이프라인이 돌아가는 상태라 Planner 가 `options` 를 채우는 역할.

### 산출물

- [ ] `ml/src/gd_designer/planner/client.py` — Anthropic SDK 래퍼
- [ ] `ml/src/gd_designer/planner/prompts/` — 시스템 프롬프트 + 예시 Layout 요약 함수
- [ ] `ml/src/gd_designer/planner/schema.py` — `PlannerOutput` pydantic (DATA_FORMAT §2.6)
- [ ] Anthropic tool_use 로 구조화 출력 강제
- [ ] Prompt caching (시스템 프롬프트 + ObjectIDs 카탈로그 요약)
- [ ] `/plan` 엔드포인트 활성화
- [ ] `/design` 이 `use_planner=true` 면 planner→designer 체인
- [ ] UI: `DesignerPanel` — theme/density 사용자 힌트 입력
- [ ] `Layout.meta_json` 에 사용자 힌트 전달

### 종료 기준

- [ ] 실제 Anthropic 키로 `/plan` 호출 시 valid `PlannerOutput` 반환
- [ ] 캐시 히트율 > 80% (system prompt 재사용)
- [ ] 사용자 자유 텍스트 입력 ("우주 느낌") 이 plan 결과에 반영됨을 수동 확인
- [ ] 타임아웃/실패 시 룰베이스 옵션으로 폴백

### 리스크

| 리스크 | 완화 |
|---|---|
| LLM 비결정성 → 스키마 검증 실패 | tool_use + pydantic 재시도 (2회) |
| 비용 폭증 | prompt caching + max_tokens 제한 + 사용자 요청 간격 제한 |
| 프롬프트 엔지니어링 시간 소요 | 오프라인 eval 셋 (20개 레이아웃) 로 A/B |

---

## Phase 4 — Self-Supervised Style Encoder

**예상 3~5주. Designer 학습의 선행 조건.** 설계 상세: [ENCODER.md](ENCODER.md).

### 목표

라벨 없이 GD 레벨의 **스타일 표현 (임베딩)** 을 학습. Bootstrap + iterative refinement 로 v1 → v2 (필요 시 v3). 출력 임베딩은:
- **Planner** 가 참고 레벨 nearest neighbor 에 활용 (retrieval-augmented).
- **Designer** 의 conditioning 신호 `z_ref` (classifier-free guidance).
- 학습 데이터에서 **전환 영역** 을 자동 마킹해 제외 (mix-sample noise 제거).

### 산출물

**데이터 파이프라인 (Stage 2 + 3)**
- [ ] `ml/src/gd_designer/data/parse.py` — 레벨 string 압축 해제 + 오브젝트 리스트 → `data/interim/{level_id}.json`
- [ ] `ml/src/gd_designer/data/tokenize.py` — `SymbolicWindow` 생성 (ENCODER.md §11)
- [ ] `ml/src/gd_designer/data/windowize.py` — x축 stride 기반 윈도우 추출
- [ ] 필터 강화: `game_version >= 21`, 업로드 날짜 `>= 2019-01-01`

**Encoder 모델 / 학습**
- [ ] `encoder/tokenizer.py`, `encoder/windowizer.py`
- [ ] `encoder/model.py` — Transformer + DINO head (§13)
- [ ] `encoder/trainer.py` — DINO + aux recon, EMA, centering (§10)
- [ ] `encoder/prototypes.py` — KMeans + soft membership (§2, §4)
- [ ] `encoder/boundary.py` — entropy + LR ensemble, peak detection (§5, §6)
- [ ] `encoder/refine.py` — bootstrap 루프, IoU 수렴 체크 (§9, §15)
- [ ] `encoder/metrics.py` — silhouette, IoU, collapse detector

**학습 운영**
- [ ] `scripts/train_encoder.py` — 1 iteration 학습
- [ ] `scripts/bootstrap_encoder.py` — 전체 v1 → v2 → (v3) 파이프라인
- [ ] `scripts/evaluate_encoder.py` — silhouette, boundary 시각화
- [ ] 20개 레벨 수동 라벨링 (스타일 전환 대강 마킹) — sanity check

**체크포인트 / 서빙**
- [ ] `checkpoints/encoder/` 에 최종 v2 or v3 저장
- [ ] `/encode` 내부 API (Planner / Designer 가 호출) — FastAPI 라우트

### 종료 기준

- [ ] Bootstrap v2 또는 v3 에서 `IoU_boundary ≥ 0.9`
- [ ] 최종 encoder 의 `mean silhouette > 0.3` (collapse 없음)
- [ ] 20 수동 라벨 중 ≥ 15 개에 대해 자동 탐지한 transition 영역이 `±10 units` 이내에 일치
- [ ] 학습 데이터에서 Buffer_Transition 비율 측정 (20% 이하 예상, 넘으면 튜닝)
- [ ] 추론 레이턴시: 윈도우 1개당 < 50ms (GPU)

### 리스크

| 리스크 | 완화 |
|---|---|
| DINO collapse | centering + aux recon + warm-up lr |
| Cluster k 설정 민감 | k=4 고정 시작, elbow 는 v3 |
| 수렴 안 함 (v3 도 IoU < 0.9) | augmentation 재설계, temperature 튜닝, N_obj_max 상향 |
| 짧은 레벨 학습 샘플 부족 | N < 120 units 제외 |
| 수동 라벨링 시간 | 20개만, 1 레벨 당 ~5분이면 충분 |

---

## Phase 5 — Learned Designer (MVP)

**예상 4~8주. 프로젝트의 핵심 산출물.**

### 목표

룰베이스 Designer 를 학습된 모델로 교체. 두 후보 경로 중 하나 (또는 병행 비교):

1. **지도학습 (MVP 권장 시작점)** — 오픈 레벨의 (layout, decoration) 쌍으로 직접 회귀/생성 학습.
2. **Diffusion** — 2D 그리드 표현 위에 conditional denoising.
3. **RL** — policy 가 op 하나씩 배치, reward = 미적 스코어 + 플랜 일치도.

자세한 선택 근거는 [DESIGNER.md](DESIGNER.md). **Phase 4 에서 학습된 encoder 의 `z_ref` 를 condition 으로 받는다** (classifier-free guidance).

### 산출물

**데이터 준비** (Phase 4 가 이미 처리)
- [x] Phase 4 의 `data/processed/` (Pure 구간으로 정제된 윈도우들) 재사용
- [ ] Layout/Decoration 분리 규칙 확정 (ObjectKind::DECORATION 기반)
- [ ] 학습 쌍 `(layout_window, deco_window, z_ref)` 생성

**모델**
- [ ] `ml/src/gd_designer/models/baselines/nearest_neighbor.py` — 인코더 임베딩으로 검색, baseline
- [ ] `ml/src/gd_designer/models/<chosen>/` — 선택한 접근 구현 (encoder conditioning 내장)
- [ ] 학습 스크립트 + Hydra configs
- [ ] 체크포인트 관리

**평가**
- [ ] `ml/src/gd_designer/eval/metrics.py` — 밀도, 겹침률, FID-like 분포 거리
- [ ] `ml/src/gd_designer/eval/render.py` — 레벨 이미지 렌더 (비교용)
- [ ] 오프라인 eval suite: 10~20 레이아웃, 모델 vs 룰베이스 vs GT

**서빙**
- [ ] `/design` 이 체크포인트 로드 후 추론 (현재 룰 대체)
- [ ] GPU 가용성 검출 + CPU 폴백
- [ ] 콜드 스타트 시간 < 30s

**통합**
- [ ] Phase 3 Planner 와 붙여서 end-to-end 사용자 경험 재확인

### 종료 기준

- [ ] eval 에서 학습 모델이 룰베이스보다 **최소 1개 지표** 에서 유의미하게 우수
- [ ] 수동 A/B 10개 레이아웃 중 6개 이상 학습 모델 선호 (블라인드)
- [ ] 추론 레이턴시 <= 10s (GPU) / <= 30s (CPU)
- [ ] 실사용자 2~3명 (개발자 포함) 이 "쓸 만하다" 평가

### 리스크

| 리스크 | 완화 |
|---|---|
| 데이터 수집의 어려움 (파싱 포맷) | 오픈소스 GD 툴 (Eclipse, gdShare) 참고 |
| 학습 데이터 부족 | 데이터 증강 (스케일, 플립, 셔플), 프리트레인 없음이라 지도학습부터 |
| 평가 지표 부재 | 일단 수동 평가 중심, metric 은 점진 도입 |
| 모델 사이즈 vs 속도 | MVP 는 작게 (< 50M 파라미터), iterate |

---

## Phase 6 — Beta Release

**미정. Phase 5 안정화 후.**

### 목표

Geode 공식 인덱스에 공개, 제한된 베타 사용자 모집.

### 산출물 (가상)

- [ ] Geode 모드 페이지 (about.md, 스크린샷)
- [ ] 공개 ML 서버 배포 (Modal / Fly / 자체 서버)
- [ ] 인증 / API 키 발급 흐름
- [ ] 레이트 리밋, 로깅, 모니터링
- [ ] 개인정보 정책, 사용약관
- [ ] 피드백 수집 채널

### 종료 기준

- [ ] 공개 1주일 간 가동 (uptime > 95%)
- [ ] 최소 10명 외부 사용자 사용

---

## 부록 A — 전체 산출물 의존 그래프

```
P1 ✅ mod skeleton + rule-based
        │
        ▼
P2: refactor ─────────┬──── test harness ──── ml stub ──── mod↔ml wiring
                      │
                      ▼
                 ObjectIDs / DATA_FORMAT contracts fixed
                      │
                      ▼
P3: planner (LLM) ─── UI hints ─── prompt caching
                      │
                      ▼
P4: data collection ── parse/tokenize ── self-sup encoder v1 → v2 (IoU≥0.9)
                      │                                 │
                      │                                 ▼
                      │                          z_ref embeddings available
                      ▼
P5: designer training ── encoder conditioning ── eval ── checkpoint serving
                      │
                      ▼
P6: public release
```

---

## 부록 B — 주간 운영 템플릿

매주 월요일 시작 시 짧게 (문서화 안 해도 됨, 공유 채널 메시지로도 충분):
- 지난주 머지된 PR 요약
- 이번주 작업 희망 영역 (겹침 체크)
- 막힌 지점 / 도움 필요한 부분
- 현재 Phase 체크리스트 진행률
