# Data Collection

학습 데이터 수집 설계 문서. Designer 학습에 쓸 레벨을 어떻게 모으고, 어디 저장하고, 무엇을 피할지 정한다.

관련:
- [DESIGNER.md §3.1](DESIGNER.md#31-데이터) — 학습 데이터 요구
- [ROADMAP.md Phase 4](ROADMAP.md#phase-4--learned-designer-mvp) — 데이터 수집 마일스톤
- [DATA_FORMAT.md](DATA_FORMAT.md) — 처리 후 포맷

---

## 1. 목표와 범위

### 1.1 목표

Designer 모델 학습에 쓸 (layout, decoration) 쌍을 **초반 1회** 대량 수집 후 로컬 캐시로 고정. 이후 재수집 없이 재현 가능한 파이프라인.

### 1.2 범위 (포함/제외)

**포함**
- GD 온라인 레벨 중 레이팅 등급이 붙은 것:
  - **Featured** (주황)
  - **Epic** (빨강)
  - **Legendary** (노랑/무지개)
  - **Mythic** (파랑/보라, 2.2+ 에서 추가된 최상위 등급)
- 클래식 (non-platformer) 모드만

**제외**
- Unrated / Rated-only 레벨 (품질 편차 큼)
- 플랫포머 모드 레벨 (게임플레이 구조 달라 Designer 학습에 노이즈)
- 삭제되거나 비공개 처리된 레벨
- 재업로드 / 스틸 의심 레벨 (수동 화이트리스트/블랙리스트)

### 1.3 예상 규모

- 2026년 기준 누적 featured+epic+legendary+mythic 레벨 약 **3,000~5,000** (추정).
- 다운로드 완료 후 로컬 캐시 크기 약 **300MB~1GB** (레벨 string 평균 80KB 가정, 메타 포함).

---

## 2. 수집 경로 (하이브리드)

**구현: `ml/src/gd_designer/data/fetch.py` (httpx 기반, 비동기).**

레벨 한 건을 완전히 수집하려면 *메타* 와 *레벨 string* 두 조각이 필요하다. 각각 다른 소스가 제일 실용적이라 **두 엔드포인트를 조합** 한다.

### 2.1 메타 / 검색 — GDBrowser API

`https://gdbrowser.com/api/search/*?type=<tier>&page=<n>`

- tier 값: `featured | epic | legendary | mythic` (이 프로젝트 대상 전부).
- 응답 JSON 에 `epicValue` (0~3) 와 각종 boolean flag — `_rating_from_gdbrowser` 가 가장 specific 한 tier 로 정확 분류 (Mythic > Legendary > Epic > Featured).
- `gameVersion: "2.2"` 를 내부적으로 `22` 로 변환하여 `MIN_GAME_VERSION = 21` 필터 적용.
- `uploaded: "2 years"` 같은 fuzzy 문자열을 `_parse_upload_year` 로 처리, `MIN_UPLOAD_YEAR = 2019` 필터 적용.
- **왜 여기서?** — RobTop 서버는 페이징 tier 검색이 번거롭고 레이트 리밋도 tight. GDBrowser 는 이미 이 용도로 운영 중이라 마찰 적음.

### 2.2 Level string — RobTop GD 서버 직접

`http://www.boomlings.com/database/downloadGJLevel22.php`

- POST body에 `levelID` + `secret=Wmfd2893gb7` (GD 클라이언트가 보내는 공개 상수).
- 응답은 `k:v:k:v:...#hash` 형태. `_parse_gd_kv` 로 dict 변환 후 `k4` 필드가 **gzip + base64** 압축된 레벨 스트링.
- **왜 직접?** GDBrowser 는 레벨 페이로드는 서빙하지 않음. gd.py 래퍼는 `torch`/`httpx` 외에 무거운 의존성을 끌어오고 v2.2 mythic 등 최신 플래그가 버전별로 불일치.
- User-Agent 는 비워둠 (RobTop 서버는 브라우저 UA 를 거부).

### 2.3 공식 API 는 없음

RobTop 은 공식 API 를 공개한 적 없음. 위 경로는 모두 **커뮤니티 리버스엔지니어링**. 언제든 깨질 수 있으므로:
- 수집 스크립트는 재실행 가능 (idempotent).
- 한 번 받은 raw 는 로컬 캐시 (`data/raw/`) 에 저장, 재다운로드 최소화.
- 스키마가 변하면 `schema_version` 을 bump 해서 마이그레이션.

---

## 3. 필터링

수집 시 각 레벨에 대해 다음 조건 모두 만족해야 저장:

| 조건 | 검사 |
|---|---|
| 레이팅 | `featured or epic or legendary or mythic` |
| 모드 | 클래식 (`length != platformer`). `gd.py` 의 `level.is_platformer == False` |
| 오브젝트 수 | 10 ≤ N ≤ 20,000 (너무 작거나 큰 거 제외) |
| 레벨 string 유효 | 압축 해제 성공, 최소 1개 게임플레이 오브젝트 |
| 길이 | Tiny/Short/Medium/Long/XL 모두 허용 |
| 게임 버전 | **2.1+** (`game_version >= 21`). 2.0 는 오브젝트 구성이 다르고, 1.x 는 제외 |
| 업로드 날짜 | **2019-01-01 이후**. 초기 2.1 레벨들은 데코 관례가 정립 전 |
| 최소 x 폭 | `max_x - min_x ≥ 120 units` (encoder 윈도우 ≥ 2 개 확보) |

필터를 통과하지 못한 레벨도 사유를 **rejection log** 에 기록 (수집 편향 이해용).

---

## 4. 레이트 리밋 정책

### 4.1 요청 빈도

- **기본 1 req/s** (평균). 버스트 방지 토큰 버킷.
- 페이징 호출과 레벨 상세 호출 모두 포함.
- `gd.py` 의 내부 httpx 에 `asyncio.Semaphore(1)` 로 강제.

### 4.2 동시성

- 동시 in-flight request 1개 (= 순차 처리). Designer 모델 학습 이득 대비 서버 부담 최소화 가치가 더 큼.

### 4.3 백오프

- HTTP 429/503 응답 시 지수 백오프: 10s → 30s → 60s → 120s → 포기.
- 연속 3회 실패 시 15분 sleep 후 재개.

### 4.4 야간 분산

- 수집 시간대를 저부하 시간(KST 새벽) 에 맞춰 수동 실행. 자동 크론 사용 금지.

### 4.5 사용자 에이전트

요청 헤더에 식별 가능한 UA:
```
GDDesignAI-Crawler/0.1.0 (+https://github.com/sean2474/gd-ai-designer)
```
RobTop/커뮤니티가 직접 추적 가능하게. 불이익 시 연락받을 수 있음.

---

## 5. 수집 파이프라인

### 5.1 3단계 구조

```
[API 호출] ──┐
             ├──▶ data/raw/      ← 원본 레벨 string + 메타 (JSON 1개 = 1 레벨)
             │
[압축 해제/  │
 객체 파싱] ─┼──▶ data/interim/  ← 파싱된 오브젝트 리스트 (JSON)
             │
[Layout/    │
 Decoration ├──▶ data/processed/ ← 학습 tensor-ready (jsonl)
 분리]      │
             └──▶ data/rejection_log.jsonl
```

### 5.2 단계별

**Stage 1. Fetch** — `ml/scripts/collect_raw.py`
- 검색 쿼리: `Featured`, `Epic`, `Legendary`, `Mythic` (각 4회)
- 페이징하면서 levelId 수집
- 각 levelId 에 대해 레벨 상세 요청 → 원본 압축 문자열 저장
- 저장 경로: `data/raw/{levelId}.json`
- 각 파일: `{level_id, name, creator, rating, song_id, object_count, length, platformer, level_string_raw, fetched_at, schema_version}`

**Stage 2. Parse** — `ml/scripts/parse_levels.py`
- `data/raw/*.json` → 레벨 string 압축 해제 → ";" 분할 → 각 오브젝트 key-value 파싱
- 저장: `data/interim/{levelId}.json`
- 각 파일: `{level_id, objects: [{id, x, y, rot, ...}, ...]}`
- 실패 레벨은 rejection log 에 사유 기록 (`PARSE_ERROR`)

**Stage 3. Split & Tensorize** — `ml/scripts/prepare_training.py`
- `data/interim/*.json` → `ObjectIDs` 카탈로그 참조 → layout vs decoration 분리
- `DATA_FORMAT.md` 의 `Layout` / `DecorationOp[]` 쌍으로 변환
- 저장: `data/processed/train.jsonl`, `valid.jsonl`
- train/valid 분할: 95/5, creator 기준 leak 방지 (같은 creator 가 양쪽에 안 들어가게)

### 5.3 재실행 (idempotent)

- Stage 1~3 모두 **이미 존재하는 출력은 스킵**. 중간에 죽어도 재개 가능.
- `--force` 플래그로 강제 재수집 가능.

---

## 6. 데이터 저장 정책

### 6.1 Git ignore

루트 `.gitignore` 추가:
```
data/raw/
data/interim/
data/processed/
data/rejection_log.jsonl
# 단, 샘플은 커밋 OK:
!data/samples/
```

### 6.2 공유 금지 / 가능

| 대상 | Git 커밋 | 외부 공유 |
|---|---|---|
| `data/raw/*.json` (원본 레벨 string) | ❌ | ❌ |
| `data/interim/*.json` | ❌ | ❌ |
| `data/processed/*.jsonl` | ❌ | 제한적 (연구 목적, 사전 상의) |
| `data/samples/` (10~20 레벨, 테스트용) | ✅ | ✅ |
| 체크섬 리스트 `data/manifest.csv` | ✅ | ✅ |
| 학습된 모델 weight | ✅ (체크포인트) | ✅ |
| eval 지표/리포트 | ✅ | ✅ |

**근거:** 레벨은 creator 저작물. 원본 string 을 저장소에 올리면 재배포가 되므로 피한다. 파생물(학습 weight) 은 재구성 불가능하므로 OK.

### 6.3 Manifest

`data/manifest.csv` — 어떤 레벨들이 수집됐는지의 기록. 커밋 대상.

| level_id | creator | name | rating | object_count | raw_hash |
|---|---|---|---|---|---|
| 1234567 | Creator | Name | epic | 1523 | sha256:abc... |
| ... | ... | ... | ... | ... | ... |

이 파일만 있으면 나중에 누구든 같은 크롤러로 동일 데이터셋을 재구성 가능 (재현성).

---

## 7. Creator 메타 / Opt-out

### 7.1 메타 보존

모든 저장 단계에서 `creator` (이름), `level_id` (원본 링크 역할), `fetched_at` 필드 유지.
processed jsonl 에도 `source: {creator, level_id}` 남김.

### 7.2 Opt-out

이 프로젝트가 공개된 이후:
- README 와 모드 페이지에 "특정 creator 의 레벨을 학습 데이터에서 제외해달라" 는 요청 채널 제공 (GitHub Issue `opt-out/` 라벨 또는 이메일).
- 요청 받으면:
  1. 해당 creator 의 모든 level_id 를 `data/optout.txt` 에 추가 (커밋)
  2. `ml/scripts/apply_optout.py` 로 processed 재생성
  3. 체크포인트는 다음 retrain 에서 반영 (즉시 제거는 불가능하지만 최대한 빨리)

### 7.3 공개 전 작업

- 데이터셋 사용 정책 문서 (`docs/DATA_POLICY.md`) — Phase 4 중후반 작성.
- GD 커뮤니티 포럼/Discord 에 "이런 프로젝트 돌리고 있음" 사전 고지.

---

## 8. 원본 레벨 포맷 (참고)

### 8.1 레벨 string 구조

API 에서 받는 레벨 데이터는 base64 + gzip 압축된 문자열.
압축 해제 후 형식:
```
<header>;<object1>;<object2>;...;<objectN>;
```

- `header` — kA1 ~ kS39 등 레벨 전역 설정 (백그라운드, 컬러 채널, 글로벌 트리거 등)
- 각 `<object>` 는 key-value 페어: `1,8,2,30,3,15,6,90,...`
  - `1` = object ID
  - `2` = x (units, float)
  - `3` = y
  - `6` = rotation (degrees)
  - `7` = color channel
  - `21`, `22` = secondary / tertiary color
  - ... (GD 내부 키 수백 개)

### 8.2 파서

`gd.py` 가 대부분 해결. 못 다루는 세부는 `ml/src/gd_designer/data/parser.py` 에서 보강.

참고 자료:
- https://wyliemaster.github.io/gddocs/ — 커뮤니티 위키 (object key 표)
- 오픈소스 모드들 (Eclipse, gdshare) 의 파서 구현

---

## 9. 스크립트 사용법

### 9.1 One-shot 전체 실행

```bash
cd ml
uv run python scripts/collect_all.py   # Stage 1 → 2 → 3 전부
```

### 9.2 개별 스테이지

```bash
uv run python scripts/collect_raw.py \
    --ratings featured epic legendary mythic \
    --exclude-platformer \
    --output data/raw \
    --rate 1.0

uv run python scripts/parse_levels.py --input data/raw --output data/interim

uv run python scripts/prepare_training.py \
    --input data/interim \
    --output data/processed \
    --valid-ratio 0.05
```

### 9.3 재현성

- 모든 스크립트는 시작 시 `data/manifest.csv` 가 있으면 그걸 기준으로 수집 (=재현용).
- 없으면 API 호출 후 생성.
- `--from-manifest data/manifest.csv` 로 명시적 재현 가능.

---

## 10. 리스크와 완화

| 리스크 | 완화 |
|---|---|
| GD 서버 응답 포맷 변경 | fetch.py 가 얇은 wrapper라 재작성 쉬움. 기존 `data/raw/` 캐시는 schema_version 으로 버전업 마이그레이션 |
| GDBrowser API 변경/중단 | level_string 은 RobTop 직접 호출이라 영향 제한적. 검색만 못 하게 되면 수동 level_id 목록으로 fallback |
| 레이트 리밋으로 수집이 느림 | 수 시간 여유 잡고 저녁에 시작, 백오프 준수 |
| Creator 불만 제기 | opt-out 즉시 반영, 정책 문서화 |
| 레벨 string 포맷 업데이트 (2.3 등) | 파싱 실패 로그 모니터 + 커뮤니티 문서 참조 |
| 법적 회색 지대 | 원본 재배포 안 함, 메타 보존, 연구 목적 명시 |
| 한 번 받으면 끝이라 스키마 바뀌면 재다운로드 필요 | `schema_version` 을 raw 에도 기록. 마이그레이션 스크립트로 처리 가능하게 |

---

## 11. 향후 확장

- **Creator-level opt-in** — 자발적으로 학습 데이터 제공 의사를 밝힌 creator 만 포함 (Phase 5+)
- **커뮤니티 기여 데이터셋** — 로컬 `.gmd` 파일을 유저가 업로드하는 채널 (GitHub Release asset 등)
- **Human feedback** — 모델 출력에 대한 사용자 평가를 다시 학습 데이터로

---

## 12. 체크리스트 (Phase 4 수집 시점)

- [ ] `ml/scripts/collect_raw.py` 구현 완료
- [ ] `ml/scripts/parse_levels.py` 구현 완료
- [ ] `ml/scripts/prepare_training.py` 구현 완료
- [ ] Rate limiter 단위 테스트
- [ ] 10개 샘플 레벨로 end-to-end dry-run 성공
- [ ] 저녁 시간에 full crawl 실행 (4~8시간)
- [ ] `data/manifest.csv` 생성 확인
- [ ] Rejection log 검토 (어떤 이유로 탈락했는지 분포)
- [ ] `data/samples/` 에 10~20 레벨 수동 선정해 커밋 (테스트 fixture 용)
- [ ] Phase 4 학습 시작
