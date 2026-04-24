# Interfaces — Cross-Boundary Contracts

## 이 문서의 목적

2명이 한 모노레포에서 역할 분담 없이 같이 개발한다. 즉 같은 파일/영역을 두 사람이 동시에 건드릴 수 있고, 한쪽이 몰래 시그니처/스키마를 바꾸면 머지 후 반대쪽이 깨진다.

이 문서는 **깨지면 전체 빌드가 망가지는 계약들** 을 한 곳에 모아, 각각에 대해 스펙/버저닝/변경 절차/검증 방법을 고정한다. 구현 바꾸는 건 자유롭게 해도 되지만, 여기 나온 계약을 바꾸려면 **반드시 양쪽 리뷰**.

> 용어: "계약(contract)" = 한쪽이 이렇게 행동한다고 **약속** 하고, 다른쪽이 그걸 **믿고** 코딩한 지점.

---

## 0. 계약에 적용되는 공통 규칙

### 0.1 변경 절차

1. 계약을 바꿀 필요가 생기면 **먼저 이 문서** 를 수정하는 PR을 연다 (구현 PR보다 선행).
2. PR 제목은 `[INTERFACE] ...` 로 시작.
3. **다른 공동 개발자의 approve 필수** (self-merge 금지).
4. 머지 후 양쪽 구현체 동기화 PR들을 이어간다.

### 0.2 버저닝

- 각 JSON 스키마는 `schema_version: "M.m"` 필드 필수. `M` 은 호환 깨짐(메이저), `m` 은 추가만 있음(마이너).
- C++ 인터페이스(추상 클래스)는 헤더 파일 상단에 `// Contract version: M.m` 주석.
- Breaking change 시 CHANGELOG 한 줄 추가.

### 0.3 검증

- 각 계약마다 **contract test** 가 존재해야 한다 (어느 쪽이든 한 곳에 둠).
- Contract test = "양쪽 구현이 이 계약을 지키는지" 자동 확인하는 테스트. 예: mod가 보내는 JSON을 pydantic으로 파싱해보고, ml 서버 응답을 C++ 디시리얼라이저로 파싱해보는 식.

### 0.4 어떤 게 계약이고 어떤 게 아닌가

| 계약 (이 문서에 기재) | 내부 구현 (자유롭게 수정 OK) |
|---|---|
| `Layout` / `DecorationOp` 구조 | `RuleBasedStrategy` 의 세부 규칙 |
| `IStrategy` 추상 메서드 시그니처 | `RuleBasedStrategy` 내부 헬퍼 함수 |
| HTTP 엔드포인트 경로/요청/응답 | FastAPI 라우트의 핸들러 구현 |
| Planner 출력 JSON schema | 프롬프트 내용 / 모델 온도 |
| `ObjectIDs` 카탈로그 (kind → id 목록) | 렌더링 방식 |
| `DecorationApplier` 의 "1 undo = 1 묶음" 관찰가능 동작 | 내부적으로 `editor->createObject` 를 몇 번 부르는지 |

---

## 1. 계약: `core::Layout` / `core::DecorationOp` (데이터 타입)

> 이게 **가장 중요한** 계약. mod 전체와 ml 전체가 이 타입으로 대화.

### 1.1 스펙

**C++ 정의:** `mod/src/core/Layout.hpp`
```cpp
namespace designer::core {

enum class ObjectKind : uint8_t {
    UNKNOWN = 0,
    BLOCK_SOLID,
    BLOCK_HALF,
    SPIKE,
    ORB,
    PAD,
    PORTAL,
    SLOPE,
    DECORATION,       // 이미 데코. Layout 입력에서는 제외
};

struct LayoutObject {
    int32_t gameObjectId;  // GD 원본 id
    float x, y;            // GD 월드 좌표 (px 단위)
    float rotation;        // degrees, 반시계 +
    ObjectKind kind;
};

struct Layout {
    std::vector<LayoutObject> objects;
    float minX, minY, maxX, maxY;   // bounding box
    // meta: 사용자 프롬프트/힌트. 자유 형식 JSON 문자열.
    std::string metaJson;
};

} // namespace designer::core
```

**Python mirror:** `ml/src/gd_designer/data/schema.py`
```python
from enum import IntEnum
from pydantic import BaseModel

class ObjectKind(IntEnum):
    UNKNOWN = 0
    BLOCK_SOLID = 1
    BLOCK_HALF = 2
    SPIKE = 3
    ORB = 4
    PAD = 5
    PORTAL = 6
    SLOPE = 7
    DECORATION = 8

class LayoutObject(BaseModel):
    game_object_id: int
    x: float
    y: float
    rotation: float
    kind: ObjectKind

class Layout(BaseModel):
    objects: list[LayoutObject]
    min_x: float
    min_y: float
    max_x: float
    max_y: float
    meta_json: str = ""
```

**DecorationOp:**
```cpp
struct DecorationOp {
    int32_t gameObjectId;
    float x, y;
    float rotation;
    int32_t zOrder;    // -1 (뒤) 기본. 범위: [-100, 100]
    int32_t colorChannel; // 0 기본
    float scale;       // 1.0 기본
};
```
Python mirror 동일 구조.

### 1.2 불변식 (Invariants)

- `ObjectKind` 열거값은 **추가만** — 기존 값의 숫자는 **절대 변경 금지**. 지우려면 메이저 버전 올림.
- `x, y` 는 GD 그리드 좌표 (1 유닛 = 30px). 음수 가능.
- `rotation` 범위 `[-360, 360]`. 그 외 값은 구현에서 normalize.
- `DecorationOp.gameObjectId` 는 **데코 전용 id** 만 허용 — 게임플레이 id 넣으면 `DecorationApplier` 가 거부하고 `log::warn`.
- `Layout.objects` 가 비어있으면 Strategy는 빈 벡터 반환 (에러 아님).

### 1.3 변경 절차 특별 규칙

이 타입 추가/수정 시:
1. C++ struct 수정
2. Python pydantic 수정
3. `docs/DATA_FORMAT.md` 의 "버전 테이블" 에 새 엔트리 추가
4. Contract test (`mod/tests/core/Layout_test.cpp` + `ml/tests/data/test_schema.py`) 에서 동일 값 round-trip 검증
5. `schema_version` 마이너 +1 (기존 필드 유지) 또는 메이저 +1 (기존 깨짐)

### 1.4 Contract test

**mod 쪽** (`mod/tests/core/Layout_test.cpp`):
- 주어진 JSON (리포 안 `tests/fixtures/layout_v1_0.json`) → `designer::core::Layout` 파싱 → 필드값 assert.
- 역으로 `Layout` 인스턴스 → JSON 직렬화 → 파일과 byte-identical (key 순서/공백 정책은 `docs/DATA_FORMAT.md`).

**ml 쪽** (`ml/tests/data/test_schema.py`):
- 동일 fixture → pydantic 파싱 → 동일 assertion.
- `Layout(...).model_dump_json()` → 파일과 round-trip.

Fixture 파일은 **한 곳** 에서 관리: `docs/fixtures/layout_v1_0.json`. 양쪽 테스트가 이 파일을 읽는다.

---

## 2. 계약: `IStrategy` (mod 내부 경계)

### 2.1 스펙

`mod/src/core/Strategy.hpp`
```cpp
// Contract version: 1.0
namespace designer::core {

class IStrategy {
public:
    virtual ~IStrategy() = default;

    // 입력은 수정 금지 (const&), 출력은 새 벡터.
    // 예외 던지지 않음 (noexcept는 아니지만 관례).
    // 실패해도 빈 벡터 반환, 에러는 result 파라미터로.
    struct Result {
        std::vector<DecorationOp> ops;
        std::string error;  // empty → 성공
    };

    virtual Result design(const Layout& input) = 0;

    // 이 Strategy의 식별자 (로그/UI용).
    virtual std::string_view name() const = 0;
};

} // namespace designer::core
```

### 2.2 불변식

- `design()` 은 입력을 **절대 수정하지 않음**.
- 결과 `ops` 내 좌표는 `Layout` 의 bbox 내부 근처 (대략 외부 200px 이내).
- 같은 입력 → 같은 출력 (결정적), 단 `RandomStrategy` 예외 (시드로 제어).
- 호출자 스레드에서 동기 실행. 장시간이면 호출자가 백그라운드 스레드로 감싸야 함.

### 2.3 Contract test

- `mod/tests/strategies/IStrategy_conformance_test.cpp`:
  - 여러 Strategy 구현을 parametrize.
  - 빈 Layout → 빈 Result.
  - bbox 엄격 준수 (모든 op이 bbox 확장 영역 안).
  - 같은 입력 두 번 → 같은 출력 (결정성 Strategy 한정).

---

## 3. 계약: HTTP API (mod ↔ ml)

### 3.1 엔드포인트

| Method | Path | 요청 | 응답 |
|---|---|---|---|
| POST | `/design` | `DesignRequest` | `DesignResponse` |
| POST | `/plan` | `PlanRequest` | `PlanResponse` |
| GET | `/health` | (없음) | `{status: "ok", version: "..."}` |
| GET | `/version` | (없음) | `{schema_version: "1.0", server: "gd-designer/0.1.0"}` |

자세한 스키마는 [MOD_API.md](MOD_API.md). 여기서는 계약 규칙만.

### 3.2 불변식

- **경로는 불변**. 버전 바꾸려면 `/v2/design` 같은 prefix 신규.
- 응답은 항상 JSON. 에러도 JSON (HTTP 4xx/5xx + `{error: "...", code: "..."}`).
- 모든 요청/응답은 `schema_version` 필드 필수.
- 타임아웃: 클라이언트 쪽 기본 30s. 서버는 25s 안에 응답하거나 202 + 폴링 토큰 (Phase 3).

### 3.3 Contract test

두 방식:

**a) 골든 파일 기반** — `docs/fixtures/api/` 아래 `design_request_*.json`, `design_response_*.json` 쌍. mod 쪽 mock 서버가 응답을 반환하도록 주입, ml 쪽은 요청을 파일과 비교.

**b) 스키마 비교** — FastAPI 의 OpenAPI 출력 JSON 을 `docs/openapi.json` 과 비교. 차이 생기면 PR 에서 `docs/openapi.json` 을 같이 커밋하도록 CI 훅.

---

## 4. 계약: `ObjectIDs` 카탈로그

### 4.1 스펙

**C++ 정의:** `mod/src/core/ObjectIDs.hpp`
```cpp
namespace designer::core::ids {

struct Entry {
    int32_t gdId;
    ObjectKind kind;
    const char* name;  // 디버그용
};

// 전체 카탈로그. 길이는 런타임 결정이 아닌 컴파일타임 상수.
extern const std::span<const Entry> kCatalog;

// 조회
ObjectKind kindOf(int32_t gdId);  // 못 찾으면 UNKNOWN
bool isGameplay(int32_t gdId);
bool isDecoration(int32_t gdId);

} // namespace
```

**Python mirror:** `ml/src/gd_designer/data/object_ids.py`
- 같은 내용을 Python dict/테이블로.

### 4.2 불변식

- **한쪽만 갱신 금지**. ID 추가/변경은 반드시 양쪽 동시 PR.
- 둘이 서로 다르면 contract test 가 실패해야 함.
- 카탈로그의 소스는 `docs/fixtures/object_ids.csv` (단일 SoT). C++/Python 은 이 CSV 에서 **codegen** 으로 생성하는 게 이상적 — Phase 2 에 도입.

### 4.3 Contract test

- `mod/tests/core/ObjectIDs_test.cpp`: 카탈로그 길이 N.
- `ml/tests/data/test_object_ids.py`: 길이 N.
- 추가로 CI 에 스크립트 (`tools/check-ids-sync.sh`): CSV ↔ C++ ↔ Python 비교.

---

## 5. 계약: `DecorationApplier` 의 관찰가능 동작

### 5.1 스펙

파일 위치: `mod/src/gd/DecorationApplier.{hpp,cpp}`

```cpp
namespace designer::gd {

class DecorationApplier {
public:
    // 성공 시 실제 배치된 오브젝트 개수 반환.
    // 호출 한 번 = GD undo 스택 1 엔트리 (트랜잭션).
    // 사용자가 Ctrl+Z 한 번 눌러서 모든 op이 취소됨을 보장.
    int apply(LevelEditorLayer* editor,
              const std::vector<core::DecorationOp>& ops);
};

} // namespace
```

### 5.2 불변식

- Apply 중간 실패 시 부분 상태로 남기지 말 것 (rollback).
- `apply({})` 는 0 반환, 에디터 상태 변경 없음.
- 알 수 없는 `gameObjectId` 는 스킵 + `log::warn`, 전체 실패로 처리하지 않음.

### 5.3 Contract test

- 통합 테스트 (GD 에디터 띄워야 해서 자동화 어려움) → 수동 체크리스트:
  - [ ] Design 누르고 Ctrl+Z 한 번 → 데코 전부 사라짐
  - [ ] Design 후 다른 작업 (블록 추가) 후 Ctrl+Z 2번 → 2단계로 각각 취소
  - [ ] 빈 레벨에 Design → 0 placed, 크래시 없음

---

## 6. 계약: Planner 출력 JSON Schema

### 6.1 스펙

Planner (LLM) 는 자유 텍스트가 아닌 **구조화된 JSON** 을 반환. Anthropic tool_use 로 스키마 강제.

```python
class PlannerOutput(BaseModel):
    schema_version: str = "1.0"
    theme: Literal["cave", "space", "forest", "volcano", "cyber", "abstract"]
    density: float  # 0.0 ~ 1.0
    palette: list[int]  # GD color channel ids, 1~4개
    segments: list["Segment"]
    notes: str = ""  # 디자이너가 보는 자유 텍스트

class Segment(BaseModel):
    min_x: float
    max_x: float
    style: str
    intensity: float  # 0.0 ~ 1.0
```

### 6.2 불변식

- `theme` 은 고정 enum. 새 테마 추가 시 이 문서 + 프롬프트 + Designer 학습 데이터 모두 업데이트.
- `density` 같은 float은 항상 범위 검사 (planner LLM이 잘못 내면 clamp + warn).
- `segments` 는 min_x 오름차순 정렬.

### 6.3 Contract test

- `ml/tests/planner/test_output_schema.py`: 과거 응답 샘플 (`tests/fixtures/planner/`) 들을 전부 pydantic 파싱.
- **샘플 갱신**: 실제 planner 응답 중 대표적인 것을 주기적으로 fixture 로 커밋.

---

## 7. 계약: Settings (mod 사용자 설정)

### 7.1 스펙

`mod/mod.json` 의 `settings` 섹션이 SoT. C++ 은 `designer::config::Settings` 가 이걸 read-only 로 노출.

```json
{
  "settings": {
    "strategy": {
      "type": "string",
      "default": "rule_based",
      "options": ["rule_based", "random", "remote"]
    },
    "server_url": {
      "type": "string",
      "default": "http://localhost:8000"
    },
    "fallback_to_local": { "type": "bool", "default": true },
    "density": { "type": "float", "default": 0.5, "min": 0.0, "max": 1.0 }
  }
}
```

### 7.2 불변식

- 기존 키를 지우거나 이름 바꾸지 말 것 (사용자 저장값 증발). deprecated 주석만.
- `default` 를 바꿀 때는 CHANGELOG 에 기록.

---

## 8. 계약 목록 (요약)

| # | 계약 | 위치 | 버전 | Contract test |
|---|---|---|---|---|
| 1 | Layout / DecorationOp | `core/Layout.hpp` + `ml/data/schema.py` | 1.0 | Round-trip JSON fixture |
| 2 | IStrategy | `core/Strategy.hpp` | 1.0 | Conformance suite |
| 3 | HTTP API | `MOD_API.md` + OpenAPI | 1.0 | 골든 파일 |
| 4 | ObjectIDs | `core/ObjectIDs.hpp` + `ml/data/object_ids.py` | 1.0 | CSV 싱크 체크 |
| 5 | DecorationApplier 동작 | `gd/DecorationApplier.cpp` | 1.0 | 수동 체크리스트 |
| 6 | Planner 출력 | `ml/planner/schema.py` | 1.0 | pydantic 파싱 |
| 7 | Settings | `mod.json` + `config/Settings.hpp` | 1.0 | 필드 존재 체크 |

---

## 9. "계약 먼저, 구현 나중" 워크플로우

2명이 같이 일할 때 가장 안전한 순서:

1. **한 사람이 계약 PR 올림** — 이 문서(`INTERFACES.md`, `DATA_FORMAT.md`, `MOD_API.md`)와 스텁 타입/함수만 포함. 구현 본체는 비워둠 (return {}).
2. **다른 사람 리뷰 & approve** — 계약만 검토. 구현은 안 봄.
3. **머지 후 두 사람이 병렬로 구현** — 각자 다른 파일을 건드림:
   - 사람 A: `RuleBasedStrategy.cpp` 구현
   - 사람 B: `ml/serve/api.py` 구현
4. **통합 지점** — contract test 가 통과하면 양쪽 구현이 서로 맞음.

---

## 10. 자주 하는 실수 (피하기 위한 체크리스트)

- [ ] "작은 변경" 이라고 계약 먼저 안 바꾸고 구현부터 고쳤다 → **되돌리기**.
- [ ] JSON 키에 snake_case/camelCase 섞였다 → DATA_FORMAT.md 의 정책 따르기 (snake_case 통일).
- [ ] 새 ObjectKind 추가했는데 Python 안 고쳤다 → contract test 가 잡음. 잡기 전에 혼자 머지 금지.
- [ ] `IStrategy::design()` 이 던진 예외가 UI까지 올라간다 → `Result.error` 에 문자열로 담기.
- [ ] 에러 응답에 `schema_version` 빼먹는다 → 파서가 그 대신 500 로그 남김.

---

## 부록 A. 계약 디프 예시 (bad / good)

### Bad

```diff
// 한 사람이 혼자 머지
 struct LayoutObject {
     int32_t gameObjectId;
-    float x, y;
+    float x, y, z;   // 3D 지원 추가
     float rotation;
     ObjectKind kind;
 };
```
→ Python 쪽 `LayoutObject` 가 `z` 모르고 파싱 실패. 전체 서비스 다운.

### Good

PR 1 (`[INTERFACE] Add Z to LayoutObject`):
- `docs/INTERFACES.md` 에 z 필드 추가 + version 1.0 → 1.1 명시
- `docs/DATA_FORMAT.md` JSON 샘플 갱신
- `docs/fixtures/layout_v1_1.json` 추가
- 리뷰 + approve

PR 2 (양쪽 동시, 혹은 직후):
- `mod/src/core/Layout.hpp` 에 `z` 추가, 기본값 0
- `ml/src/gd_designer/data/schema.py` 에 `z` 추가, 기본값 0
- Contract test 에 1.0 fixture 는 호환 (z 누락 → 기본 0), 1.1 fixture 는 새로 통과
