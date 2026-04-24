# Collaboration

2명이 같은 모노레포를 역할 분담 없이 공유 개발한다. 이 문서는 서로 안 깨뜨리고 효율적으로 일하기 위한 **프로세스 규칙**을 정의한다.

관련:
- [INTERFACES.md](INTERFACES.md) — 경계 계약의 변경 절차.

---

## 1. 브랜치 전략

### 1.1 기본: trunk-based + feature branch

- `main` 은 **항상 빌드/테스트 통과 상태**. 직접 푸시 금지.
- 새 작업은 feature 브랜치에서.
- 브랜치 네이밍: `<initial>/<짧은-설명>`, 예: `s/refactor-core`, `k/ml-trainer`.
- 머지는 **squash merge** 기본 (히스토리 깨끗하게).

### 1.2 수명

- 브랜치는 **1일~3일** 이내 머지 목표. 그 이상은 `main` rebase 자주.
- 장기 실험 (예: 새 diffusion 모델 PoC) 은 별도 브랜치에서 오래 갈 수 있지만, 최소 주 1회 `main` 에서 rebase.

### 1.3 직접 `main` 푸시

- 금지. 단, 예외: 오타 수정, 문서 typo 등 "명백히 머지 의견 불필요한 1줄" 은 pre-approval 로 OK (커밋 메시지에 `[skip-review]` 명시).

---

## 2. PR 정책

### 2.1 PR 필수

- 모든 코드 변경은 PR 을 거친다.
- PR 본문에: *무엇을*, *왜*, *어떻게 테스트했는지*.

### 2.2 리뷰 요구

- 일반 변경: 상대방 1명의 approve.
- **계약 변경 (INTERFACES.md 목록)**: 상대방 approve + PR 제목에 `[INTERFACE]` 태그.
- 자체 approve 금지.

### 2.3 PR 크기

- 가능하면 **300 LoC 이하**. 커지면 리뷰 품질 급락.
- 커질 것 같으면: (a) 계약 PR 먼저, 구현 PR 쪼개서 여러 개, (b) 스텁 PR + 실구현 PR.

### 2.4 셀프 체크리스트 (PR 본문에 복붙)

```
- [ ] 빌드 통과 (mod: `cd mod && cmake --build build`)
- [ ] 기존 테스트 통과 (mod: Catch2 / ml: pytest)
- [ ] 새 기능이면 테스트 추가
- [ ] 계약 (INTERFACES.md) 변경하면 문서 먼저 업데이트
- [ ] CHANGELOG 필요한 변경이면 항목 추가
```

---

## 3. 충돌 방지

### 3.1 같은 파일 동시 수정 회피

- 큰 변경 시작 전 **짧은 공지** (메신저/이슈): "나 `DecorationApplier.cpp` 건드릴게".
- 겹친다 싶으면 한 사람이 먼저 머지하고 다른 사람이 rebase.

### 3.2 CHANGELOG 머지 충돌

각자 PR 에서 CHANGELOG 상단에 한 줄씩 추가하면 충돌이 잦다. 해결:
- CHANGELOG 는 `## [Unreleased]` 섹션 아래에 계속 append-only.
- 충돌 나면 두 줄 다 남기기만 하면 됨.

### 3.3 대규모 리팩토링

- 리팩토링 시작 전 **별도 PR 로 공지** (RFC 스타일): "X 를 Y 로 바꾸려 함, 근거 Z".
- 상대방 의견 하루 대기 후 착수.

---

## 4. 커밋 메시지

### 4.1 제목

- 영어, imperative 50자 이내.
- 예: `Add ObjectIDs catalog`, `Fix crash in LayoutReader`, `Refactor strategies dir`.

### 4.2 본문 (선택)

- 한국어/영어 자유.
- *왜* 바꿨는지 (what 은 diff 로 보임).

### 4.3 태그

- `[INTERFACE]` — 계약 변경
- `[FIXTURE]` — fixture 업데이트
- `[DOCS]` — 문서만 변경
- `[SKIP-REVIEW]` — 1줄 타이포

### 4.4 Co-author

Claude 가 작성한 코드는 커밋 trailer:
```
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

---

## 5. 역할 유동성

공식 분담은 없지만 **최근 맥락** 은 자연스럽게 누가 뭐 건드렸는지에서 나온다.

- 누가 지금 `ml/serve/` 를 주로 만지고 있다면, 그 쪽 PR 리뷰는 상대방이 먼저. 거꾸로도 같음.
- "내가 처음 보는 파일이라 리뷰 어려움" → PR 본문에 간단한 맥락 덧붙여달라 요청.

---

## 6. 버그/작업 트래킹

### 6.1 GitHub Issues 사용

- 이슈 필수 태그 (라벨):
  - `type/bug`, `type/feature`, `type/refactor`, `type/docs`, `type/interface`
  - `area/mod`, `area/ml`, `area/docs`, `area/build`
  - `priority/p0` (막히는 것), `p1` (중요), `p2` (언젠가)
- 모든 PR 은 이슈 번호 참조 (`fixes #12`).

### 6.2 Roadmap 연결

- `docs/ROADMAP.md` 의 Phase 체크리스트를 GitHub Projects 보드와 동기화.
- Phase 끝나면 회고 이슈 하나 (`retrospective/phaseN`).

---

## 7. 스텁 퍼스트 (Stub-First)

INTERFACES.md 의 §9 패턴을 반복:

```
1. 계약 PR (타입 + 문서)        ← 양쪽 리뷰, 머지
2. 빈 스텁 PR (return {} 같은)   ← 빌드만 통과
3. 실제 구현 PR (양쪽 병렬 가능)
```

이 패턴의 이점:
- 두 사람이 **2번 머지 직후부터 병렬 작업** 가능.
- 한 쪽 구현이 늦어도 다른 쪽은 mock/fake 로 진행.

---

## 8. 코드 리뷰 문화

### 8.1 무엇을 볼 것인가

- **계약** 침범 여부 (INTERFACES.md)
- **레이어 경계** 침범 (예: `core/` 에서 `Geode/` include 했나)
- 테스트 누락
- 큰 설계 문제

구현 세부(스타일, 네이밍) 는 가능하면 리뷰에서 힘 빼지 말 것. 필요하면 linter 로.

### 8.2 리뷰 완료 기준

- "Approve" 는 "머지해도 괜찮다" 의 뜻.
- 작은 제안은 `nit:` prefix 로 (선택사항임을 명확히).
- 반드시 고쳐야 할 건 `blocking:` prefix.

### 8.3 응답 속도 기대

- PR 오픈 후 **24시간 내** 첫 리뷰 (가능하면).
- 넘어가면 핑.

---

## 9. 릴리즈 / 버전

### 9.1 모드 버전

`mod/mod.json` 의 `version` 필드. 시맨틱 버저닝:
- PATCH: 버그 수정
- MINOR: 기능 추가 (계약 호환)
- MAJOR: 계약 breaking

### 9.2 ml 서버 버전

`ml/pyproject.toml` 의 `version`.

### 9.3 Schema 버전

독립적. DATA_FORMAT 의 §4 테이블 참고.

### 9.4 태깅

- mod 릴리즈: `mod-v0.1.0`
- ml 릴리즈: `ml-v0.1.0`
- 스키마 릴리즈: `schema-v1.0`

---

## 10. 의사소통 채널 (팀이 정할 것)

- 짧은 조율: _(Slack/Discord/카톡 — 아직 미정)_
- 길게 문서화할 것: GitHub Issue
- 아키텍처 합의: docs/ PR 로 (글로 남겨야 기억됨)

---

## 11. 협업 안티패턴

과거에 흔한 실수들. 이 리스트는 같이 채워나감.

- ❌ "빨리 필요해서 혼자 머지" — 리뷰 루프가 있어야 양쪽 컨텍스트 싱크.
- ❌ PR 10개 동시 오픈 → 리뷰 대기열만 쌓임. 한 번에 2~3개 max.
- ❌ 의미 없는 formatting 변경을 실제 변경과 섞기 → diff 읽기 어려움. 별도 PR.
- ❌ 머지 직전에 `main` rebase 안 함 → CI 통과해도 실제론 깨져있음.
