# Data Format

이 문서는 **mod ↔ ml 사이에 오가는 모든 JSON**, 그리고 그와 1:1 매핑되는 C++ / Python 타입의 권위적 레퍼런스다. 구현이 이 문서와 달라지면 문서가 이기고 구현을 고친다.

관련:
- [INTERFACES.md](INTERFACES.md) — 계약 관점 (변경 절차, 버저닝 정책).
- [MOD_API.md](MOD_API.md) — HTTP 엔드포인트 사용처.

---

## 1. 정책

### 1.1 키 네이밍

- JSON 에서는 **`snake_case`**. 예: `game_object_id`, `schema_version`.
- C++ struct 필드는 **`camelCase`** (프로젝트 관례). 예: `gameObjectId`.
- Python pydantic 은 **`snake_case`** (JSON 과 동일).
- C++ 직렬화 시 수동 매핑 (nlohmann/json 의 `NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE_WITH_DEFAULT` 는 이름 그대로 씀 → `to_json/from_json` 수동 래퍼 필요).

### 1.2 숫자 표현

- **정수**: 모두 `int32_t`. 음수 허용 (GD 좌표 시스템 상 음수 x/y 가능).
- **실수**: 모두 `float` (32비트). double 쓰지 않음 (학습/추론에서 tensor 타입 불일치 방지).
- JSON 출력 시: 정수는 `123`, 실수는 항상 소수점 포함 `123.0` (일부 파서 뉴언스).

### 1.3 문자열

- UTF-8. ASCII 밖 문자 허용 (사용자 프롬프트엔 한국어 들어올 수 있음).
- `""` (빈 문자열) 과 `null` 을 섞지 말 것 — 항상 빈 문자열로 통일, 필드는 required로.

### 1.4 Enum

- Wire 포맷에서는 **정수** 로 (ObjectKind 등). 사람이 보기 편한 string 필드는 별도 `kind_name` (optional, 디버그용) 둘 수 있음.
- 이유: 문자열 enum 은 typo 방지 어려움 + 파서마다 case sensitivity 다름.

### 1.5 필드 추가/제거

- **추가**는 자유 (단, default 값 필수 → 구버전 파서가 무시해도 OK).
- **제거/이름변경**은 메이저 버전 상승.

### 1.6 버전 필드

모든 top-level 객체에 `schema_version: "M.m"` 필수. 예: `"1.0"`, `"1.1"`, `"2.0"`.

---

## 2. 핵심 타입

### 2.1 `ObjectKind`

플레이어 입장에서 오브젝트가 어떤 역할인지를 나타내는 enum. 실제 GD 오브젝트 id 는 수백 개지만, Designer/Planner 에게는 이 추상 수준만 노출.

| 값 | 이름 | 설명 |
|---|---|---|
| 0 | `UNKNOWN` | 미분류. `ObjectIDs` 에 없는 id는 이걸로 분류. |
| 1 | `BLOCK_SOLID` | 발 디딜 수 있는 블록 전반 |
| 2 | `BLOCK_HALF` | 반 블록 / 작은 블록 |
| 3 | `SPIKE` | 가시 (작은 거, 큰 거 포함) |
| 4 | `ORB` | 공중 점프 링 (노랑/파랑/분홍 등) |
| 5 | `PAD` | 점프 패드 (바닥) |
| 6 | `PORTAL` | 모드 변경 포털 (큐브/쉽/볼 등) |
| 7 | `SLOPE` | 경사면 |
| 8 | `DECORATION` | 장식 오브젝트 전반. Layout 입력에서 제외됨. |

**추가 규칙:** enum 값 숫자는 **영구 불변**. 새 값은 9부터 append.

### 2.2 `LayoutObject`

에디터 레벨에서 읽어낸 게임플레이 오브젝트 1개.

```json
{
  "game_object_id": 8,
  "x": 90.0,
  "y": 15.0,
  "rotation": 0.0,
  "kind": 3
}
```

| 필드 | 타입 | 단위/범위 | 설명 |
|---|---|---|---|
| `game_object_id` | int32 | 양의 정수 | GD 원본 오브젝트 id |
| `x` | float | px | GD 월드 x 좌표 |
| `y` | float | px | GD 월드 y 좌표 (위=+) |
| `rotation` | float | degrees, [-360, 360] | 반시계 양수 |
| `kind` | int32 | ObjectKind enum | 분류 |

### 2.3 `Layout`

한 레벨(또는 그 일부) 의 레이아웃 전체.

```json
{
  "schema_version": "1.0",
  "objects": [
    { "game_object_id": 8, "x": 90.0,  "y": 15.0, "rotation": 0.0, "kind": 3 },
    { "game_object_id": 1, "x": 120.0, "y": 15.0, "rotation": 0.0, "kind": 1 }
  ],
  "min_x": 0.0,
  "min_y": 0.0,
  "max_x": 510.0,
  "max_y": 240.0,
  "meta_json": "{\"theme_hint\":\"dark\",\"density\":0.5}"
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `schema_version` | string | `"1.0"` |
| `objects` | LayoutObject[] | 순서 무관, 중복 id 허용 (위치만 다르면 별개) |
| `min_x`, `min_y`, `max_x`, `max_y` | float | bbox. `objects` 비면 모두 0. |
| `meta_json` | string | 자유 형식 JSON 문자열. 사용자 힌트. |

**불변식:**
- `objects` 의 `ObjectKind` 는 `DECORATION` 이 아니어야 함.
- bbox 는 실제 objects 기준 정확해야 함 (mod 의 `LayoutReader` 가 계산 후 채움).

### 2.4 `DecorationOp`

데코 오브젝트 1개를 "여기에 놔라" 라는 명령.

```json
{
  "game_object_id": 1619,
  "x": 90.0,
  "y": -15.0,
  "rotation": 180.0,
  "z_order": -1,
  "color_channel": 0,
  "scale": 1.0
}
```

| 필드 | 타입 | 단위/범위 | 기본값 | 설명 |
|---|---|---|---|---|
| `game_object_id` | int32 | 양의 정수 | (필수) | 데코 전용 GD id |
| `x`, `y` | float | px | (필수) | 배치 좌표 |
| `rotation` | float | degrees | 0.0 | 회전 |
| `z_order` | int32 | [-100, 100] | -1 | 렌더 순서. 낮을수록 뒤. |
| `color_channel` | int32 | [0, 1010] | 0 | GD 색 채널. 0 = 기본. |
| `scale` | float | [0.1, 5.0] | 1.0 | 크기 |

### 2.5 `DesignRequest` / `DesignResponse`

mod → ml 로 가는 추론 요청/응답.

**Request:**
```json
{
  "schema_version": "1.0",
  "layout": { ... Layout ... },
  "options": {
    "theme": "dark",
    "density": 0.5,
    "seed": 42,
    "use_planner": true
  }
}
```

**Response:**
```json
{
  "schema_version": "1.0",
  "ops": [ ... DecorationOp[] ... ],
  "plan": { ... PlannerOutput (optional) ... },
  "server_version": "gd-designer/0.1.0",
  "elapsed_ms": 1234
}
```

`options.seed` — 결정성 재현용. 없으면 서버가 현재 시간 기반 생성 후 응답에 반환(`response.seed`).
`options.use_planner` — false 면 Planner 스킵, Designer 만 실행 (속도 우선 모드).

### 2.6 `PlannerOutput`

```json
{
  "schema_version": "1.0",
  "theme": "cave",
  "density": 0.6,
  "palette": [1, 2, 4],
  "segments": [
    { "min_x": 0, "max_x": 200, "style": "intro", "intensity": 0.3 },
    { "min_x": 200, "max_x": 510, "style": "climax", "intensity": 0.9 }
  ],
  "notes": "intro에 넉넉하게, climax에 붉은 컬러 강조"
}
```

`theme` 허용값 (현재): `cave | space | forest | volcano | cyber | abstract`. 새 테마 추가는 **프롬프트 + Designer 학습 데이터 + 이 문서** 셋 동시 업데이트.

### 2.7 `ErrorResponse`

HTTP 4xx/5xx 의 본문.

```json
{
  "schema_version": "1.0",
  "error": "Invalid layout: bbox negative",
  "code": "INVALID_LAYOUT",
  "request_id": "req_01HW..."
}
```

`code` 는 열거형 문자열. 카탈로그:
- `INVALID_LAYOUT` — 파싱/검증 실패
- `INVALID_OPTIONS` — options 범위 밖
- `PLANNER_FAILED` — Anthropic 호출 실패
- `DESIGNER_FAILED` — 추론 실패
- `ENCODER_FAILED` — encoder 추론 실패
- `TIMEOUT` — 서버 내부 타임아웃
- `INTERNAL` — 그 외 (스택트레이스는 서버 로그로만)

### 2.8 `SymbolicWindow` (encoder 입력/학습 데이터)

Phase 4 encoder 가 먹는 윈도우 단위 표현. 하나의 레벨 구간 `[n - c, n + c]` (x축, GD units) 의 오브젝트들을 토큰 시퀀스로.

```json
{
  "schema_version": "1.0",
  "level_id": 1234567,
  "center_x": 120.0,
  "radius_units": 30,
  "objects": [
    {
      "rel_x": -28.0,
      "y": 15.0,
      "kind": 3,
      "game_object_type": 2,
      "rotation_bucket": 0,
      "scale_bucket": 3,
      "color_bucket": 0
    }
  ]
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `level_id` | int | 원본 레벨 (creator 속성 유지용) |
| `center_x` | float | 윈도우 중심 x (units, 레벨 절대) |
| `radius_units` | int | 윈도우 반경 (기본 30, = 블록 1개) |
| `objects[].rel_x` | float | 윈도우 중심 기준 상대 x (units, `[-c, +c]`) |
| `objects[].y` | float | 절대 y (units, `[0, 32]` 가정) |
| `objects[].kind` | int | ObjectKind enum (§2.1) |
| `objects[].game_object_type` | int | GD `GameObjectType` enum (Geode Enums.hpp). MVP 토크나이저 옵션 |
| `objects[].rotation_bucket` | int | `[0, 8)` — 45° 단위 |
| `objects[].scale_bucket` | int | `[0, 8)` — log-quantized (ENCODER.md §11.2) |
| `objects[].color_bucket` | int | `[0, 33)` — 색 채널 |

**불변식:**
- `objects` 는 (rel_x, y, id) 오름차순 정렬.
- `|objects|` ≤ 128 (`N_obj_max`).
- `rel_x` 범위: `[-radius_units, +radius_units]`.
- `DECORATION` kind 는 학습 윈도우에 포함 여부를 `include_decoration` flag (encoder 설정) 로 제어 — layout only / deco only / both.

**윈도우 생성 배치:**
한 레벨 → 여러 `SymbolicWindow` (stride=5 units). 저장: `data/processed/encoder/{level_id}/window_{idx:05d}.json` (또는 tensor-packed `.pt`/`.npz`).

---

## 3. 직렬화 규칙

### 3.1 JSON 출력 포맷

- **Indent**: 서버→클라이언트 응답은 **compact** (공백 없음, 최소 크기). 테스트 fixture 는 indent 2 (가독성).
- **키 순서**: 구조체 정의 순서 그대로. 파서가 순서에 의존하면 안 되지만, fixture round-trip 테스트 편의를 위해 일관 유지.
- **Float 정밀도**: 소수점 6자리. `123.456789` 보다 긴 건 반올림.

### 3.2 예시

**Human-readable (fixture):**
```json
{
  "schema_version": "1.0",
  "objects": [
    {
      "game_object_id": 8,
      "x": 90.0,
      "y": 15.0,
      "rotation": 0.0,
      "kind": 3
    }
  ],
  "min_x": 90.0,
  "min_y": 15.0,
  "max_x": 90.0,
  "max_y": 15.0,
  "meta_json": ""
}
```

**Wire (compact):**
```json
{"schema_version":"1.0","objects":[{"game_object_id":8,"x":90.0,"y":15.0,"rotation":0.0,"kind":3}],"min_x":90.0,"min_y":15.0,"max_x":90.0,"max_y":15.0,"meta_json":""}
```

### 3.3 C++ ↔ JSON 구현

`mod/src/net/Serialization.hpp` 에 다음을 정의:
```cpp
void to_json(nlohmann::json& j, const core::Layout& l);
void from_json(const nlohmann::json& j, core::Layout& l);
// DecorationOp, DesignRequest, 등등 동일.
```

모든 `from_json` 은:
1. `schema_version` 체크. 지원 안 하는 메이저면 `throw DeserializationError`.
2. 필드 누락 시 기본값 대입 (추가 허용).
3. 타입 불일치 시 에러 throw.

### 3.4 Python ↔ JSON 구현

pydantic `BaseModel` 이 자동으로 처리. 단:
- `Field(..., alias="...")` 는 **쓰지 않음** — JSON 키와 필드 이름을 맞춤 (snake_case 통일).
- `model_validate_json(raw)` 로 파싱, `.model_dump_json()` 으로 직렬화.
- `ConfigDict(extra="ignore")` — 모르는 필드 무시 (forward compatibility).

---

## 4. 버전 테이블

| 버전 | 날짜 | 변경 | Breaking? |
|---|---|---|---|
| 1.0 | 2026-04-23 | 최초 정의 | — |

이 테이블에 **모든** 변경이 기록돼야 함. CHANGELOG.md 의 Data format 섹션과 동기화.

---

## 5. Fixtures

테스트 / 검증용 샘플 JSON 들은 모두 `docs/fixtures/` 아래에 둔다.

```
docs/fixtures/
├── layout_v1_0_empty.json        # objects []
├── layout_v1_0_single_spike.json # 최소 1 오브젝트
├── layout_v1_0_mixed.json        # 여러 kind 혼합, 대형
├── design_request_v1_0.json
├── design_response_v1_0.json
├── planner_output_v1_0.json
├── error_invalid_layout.json
└── object_ids.csv                # ObjectIDs SoT
```

양쪽 contract test 가 이 파일들을 참조. 파일 업데이트 시 PR 제목에 `[FIXTURE]` 태그.

---

## 6. 좌표 시스템 참고

- GD 월드 좌표는 **1 유닛 = 30 px**. 그리드 스냅 되는 위치는 30 배수.
- 원점(0,0) 은 레벨의 왼쪽 아래 지면.
- y=0 은 보통 플레이어가 지면에 서있는 높이. spike는 y=15 (지면 위 15px).
- x 는 진행 방향 (오른쪽 +).
- `Layout.min_x == 0` 이면 레벨 시작점부터. 중간 섹션만 보낼 땐 `min_x = 1200` 같이 나올 수 있음.

---

## 7. 크기 제약

| 항목 | 한계 | 근거 |
|---|---|---|
| `Layout.objects.length` | 10,000 | 대형 레벨 허용, 이보다 크면 청킹 필요 |
| 단일 요청 JSON 크기 | 5 MB | HTTP 바디 상한 |
| `DecorationOp[].length` | 50,000 | apply 시간 현실성 |
| `Layout.meta_json` 문자열 | 4 KB | 사용자 프롬프트 상식 |

넘으면 서버가 `INVALID_LAYOUT` 으로 거부.

---

## 8. 확장 예약 (Reserved)

현재 쓰지 않지만 미래에 추가될 수 있는 필드:

- `LayoutObject.z` — 3D 지원 가능성 (현재 모두 0 가정).
- `LayoutObject.flip_x`, `flip_y` — 좌우/상하 반전 (현재 rotation 으로 커버).
- `LayoutObject.group_ids` — GD 그룹 시스템.
- `DecorationOp.group_ids` — 트리거 연동.

이 필드들은 **새 minor 버전** (1.1, 1.2 …) 에서만 도입. 기존 1.0 파서는 `extra=ignore` 라 무시됨.
