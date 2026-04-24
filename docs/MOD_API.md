# Mod ↔ ML HTTP API

mod 안의 `net::DesignerClient` 와 ml 안의 `serve/api.py` 사이의 통신 규격.

**버전:** 1.0
**base URL (기본):** `http://localhost:8000`

관련:
- [DATA_FORMAT.md](DATA_FORMAT.md) — 요청/응답 바디 스키마
- [INTERFACES.md](INTERFACES.md) — 계약 변경 절차

---

## 1. 공통 규약

### 1.1 프로토콜

- HTTP/1.1 기본. HTTP/2 에도 호환되도록 (FastAPI + uvicorn 기본).
- TLS: Phase 1~3은 평문(로컬/사설망), Phase 4 공개 시 HTTPS 필수.
- 요청/응답 `Content-Type: application/json; charset=utf-8`.

### 1.2 인증

- **Phase 1~2**: 인증 없음 (localhost 만 바인드).
- **Phase 3+**: `X-API-Key` 헤더. 키는 mod 설정(`Settings.apiKey`) 에서 읽음.
  - 서버가 키 검증 실패 시 `401 Unauthorized` + `{code: "UNAUTHORIZED"}`.
  - 키는 `mod.json` 에 평문 저장 금지 (INTERFACES.md §7).

### 1.3 모든 응답의 공통 필드

| 필드 | 타입 | 설명 |
|---|---|---|
| `schema_version` | string | `"1.0"` 고정 |
| `server_version` | string | 서버 빌드 태그. 예: `"gd-designer/0.1.0"` |
| `request_id` | string | 서버가 생성. 로그 역추적용 |

### 1.4 HTTP 상태 코드

| 코드 | 의미 |
|---|---|
| 200 | 성공 |
| 202 | 비동기 accepted (Phase 3, 오래 걸리는 요청) |
| 400 | 요청 스키마/값 잘못됨 |
| 401 | 인증 실패 |
| 408 | 서버 타임아웃 (내부) |
| 429 | 레이트 리밋 |
| 500 | 서버 내부 오류 |
| 503 | 서버 일시 불능 (모델 로딩 중 등) |

4xx/5xx 본문은 항상 `ErrorResponse` ([DATA_FORMAT §2.7](DATA_FORMAT.md#27-errorresponse)).

### 1.5 타임아웃

| 단계 | 값 | 비고 |
|---|---|---|
| 클라이언트 connect | 5s | TCP 연결 |
| 클라이언트 read | 30s | 응답 대기 |
| 서버 internal | 25s | 넘으면 `TIMEOUT` 코드로 408 |

Phase 3 이후로 긴 추론이 생기면 202 + `/design/status/{request_id}` 폴링 패턴으로 전환.

### 1.6 멱등성

- `POST /design`: 같은 요청 (동일 `options.seed` + 동일 `layout`) → 같은 응답 (결정성 모델 한정).
- 네트워크 재시도 시 중복 호출 OK — 서버는 내부 상태 저장하지 않음.

### 1.7 레이트 리밋

- Phase 1~2: 없음.
- Phase 3: 클라이언트 IP 당 10 req/분. 초과 시 `429` + `Retry-After` 헤더 (초).

---

## 2. 엔드포인트

### 2.1 `POST /design`

**용도:** 한 번에 planner + designer 를 실행, 데코 op 벡터 반환.

**Request:** `DesignRequest` (DATA_FORMAT §2.5)

```http
POST /design HTTP/1.1
Content-Type: application/json

{
  "schema_version": "1.0",
  "layout": {
    "schema_version": "1.0",
    "objects": [...],
    "min_x": 0, "min_y": 0, "max_x": 510, "max_y": 240,
    "meta_json": ""
  },
  "options": {
    "theme": "dark",
    "density": 0.5,
    "seed": 42,
    "use_planner": true
  }
}
```

**Response:** `DesignResponse`

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "schema_version": "1.0",
  "server_version": "gd-designer/0.1.0",
  "request_id": "req_01HW...",
  "ops": [
    {"game_object_id": 1619, "x": 90.0, "y": -15.0,
     "rotation": 180.0, "z_order": -1, "color_channel": 0, "scale": 1.0}
  ],
  "plan": {
    "schema_version": "1.0",
    "theme": "cave",
    "density": 0.5,
    "palette": [1, 2],
    "segments": [...],
    "notes": ""
  },
  "seed": 42,
  "elapsed_ms": 1234
}
```

**실패 예:**
```http
HTTP/1.1 400 Bad Request

{
  "schema_version": "1.0",
  "server_version": "gd-designer/0.1.0",
  "request_id": "req_01HW...",
  "error": "layout.objects must not contain DECORATION kind",
  "code": "INVALID_LAYOUT"
}
```

### 2.2 `POST /plan`

**용도:** Planner(LLM) 만 실행. 디버그/개발 용도.

**Request:**
```json
{
  "schema_version": "1.0",
  "layout": { ... Layout ... },
  "user_prompt": "우주 스테이션 느낌, 보라색 팔레트"
}
```

**Response:** `PlannerOutput` (DATA_FORMAT §2.6) + 공통 필드.

Planner 결과는 Designer 로 넘기지 않고 바로 반환. UI 에서 "계획만 먼저 보기" 에 씀.

### 2.3 `POST /design-from-plan`

**용도:** 이미 받아둔 plan 을 가지고 Designer 만 재실행 (다른 seed 시도, 테마 교체 등).

**Request:**
```json
{
  "schema_version": "1.0",
  "layout": { ... },
  "plan":   { ... PlannerOutput ... },
  "options": { "seed": 7 }
}
```

**Response:** `DesignResponse` (`plan` 필드는 요청의 plan 을 echo).

### 2.4 `GET /health`

**용도:** liveness 체크. mod 가 "서버 켜져있나" 확인하는 용.

**Response:**
```json
{
  "schema_version": "1.0",
  "server_version": "gd-designer/0.1.0",
  "status": "ok",
  "uptime_s": 120,
  "models_loaded": ["designer_v0"]
}
```

`status` 가 `"degraded"` 면 Planner 또는 Designer 중 하나가 미로드 상태. mod 는 이 경우 `/design` 대신 로컬 RuleBased 폴백 사용 (설정에 따라).

### 2.5 `GET /version`

**용도:** 서버가 지원하는 스키마 버전 확인. mod 가 시작 시 1회 호출해서 미스매치 알림.

**Response:**
```json
{
  "schema_version": "1.0",
  "server_version": "gd-designer/0.1.0",
  "supported_schema_majors": [1]
}
```

mod 가 요청한 `schema_version` 의 메이저가 `supported_schema_majors` 에 없으면 → UI 에 "서버 업그레이드 필요" alert.

### 2.6 `GET /openapi.json`

FastAPI 기본 제공. 이걸 `docs/openapi.json` 에 주기적으로 커밋해서 diff 로 계약 변경 감지.

### 2.7 (Phase 3) `GET /design/status/{request_id}`

비동기 요청 상태 폴링.

```json
{
  "schema_version": "1.0",
  "status": "running" | "done" | "failed",
  "progress": 0.6,
  "result": { ... DesignResponse ... },  // status=done 일 때만
  "error": "...",                         // status=failed 일 때만
  "code": "..."
}
```

---

## 3. 클라이언트 동작 (mod 쪽)

### 3.1 `net::DesignerClient` 설계 요구

```cpp
namespace designer::net {

struct ClientOptions {
    std::string baseUrl = "http://localhost:8000";
    std::string apiKey;       // 비어있으면 헤더 안 보냄
    int connectTimeoutMs = 5000;
    int readTimeoutMs    = 30000;
    int maxRetries       = 2;
};

class DesignerClient {
public:
    explicit DesignerClient(ClientOptions opts);

    // 비동기. Future 는 Geode/arc 코루틴과 호환.
    arc::Task<core::IStrategy::Result>
    design(core::Layout layout, DesignOptions opts);

    arc::Task<core::PlannerOutput>
    plan(core::Layout layout, std::string userPrompt);

    arc::Task<HealthInfo> health();
};

}
```

### 3.2 에러 처리

- HTTP 4xx: `Result.error = body.error` 그대로 UI 에 표시.
- HTTP 5xx / 네트워크 오류: 최대 `maxRetries` 재시도 (지수 백오프: 500ms, 1s, 2s).
- `schema_version` mismatch: 재시도 없이 즉시 실패 + 알림.

### 3.3 폴백 규칙

`Settings.fallbackToLocal = true` 이면:
- 서버가 `/health` 실패 → 로컬 RuleBased 사용
- `/design` 이 408/503 → 1회 재시도 후 실패 시 RuleBased
- 서버 응답 스키마 파싱 실패 → RuleBased

폴백이 발동했음을 UI 에 notify (alert 하단 텍스트 "fallback" 뱃지).

### 3.4 동시 요청 정책

- 같은 Design 버튼 연타 → 진행 중이면 무시 (`isRequestInFlight` 플래그).
- 사용자가 에디터에서 다른 작업 하다가 재클릭 → 새 요청.

---

## 4. 서버 동작 (ml 쪽)

### 4.1 FastAPI 구조

```python
# ml/src/gd_designer/serve/api.py
from fastapi import FastAPI, HTTPException
from .schema import DesignRequest, DesignResponse, PlanRequest, PlannerOutput
from .inference import run_pipeline, run_planner

app = FastAPI(title="gd-designer", version="0.1.0")

@app.post("/design", response_model=DesignResponse)
async def design(req: DesignRequest) -> DesignResponse:
    try:
        return await run_pipeline(req)
    except InvalidLayoutError as e:
        raise HTTPException(400, detail={"error": str(e), "code": "INVALID_LAYOUT"})
    # ...

@app.post("/plan", response_model=PlannerOutput)
async def plan(req: PlanRequest) -> PlannerOutput:
    return await run_planner(req)

@app.get("/health")
async def health() -> dict:
    return {"status": "ok", ...}
```

### 4.2 에러 매핑

FastAPI 의 `HTTPException` 을 통합 `ErrorResponse` 로 래핑하는 미들웨어:
```python
@app.exception_handler(HTTPException)
async def http_exc(request, exc):
    detail = exc.detail if isinstance(exc.detail, dict) else {"error": str(exc.detail), "code": "INTERNAL"}
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "schema_version": "1.0",
            "server_version": SERVER_VERSION,
            "request_id": request.state.request_id,
            **detail,
        },
    )
```

### 4.3 로깅

- 각 요청 진입 시 `request_id` 생성 (`req_` + ULID).
- 응답 필드에 포함 + 로그 prefix.
- Anthropic 호출 실패 시 raw response 는 **서버 로그에만**, 클라이언트에는 일반화된 메시지.

### 4.4 시작 절차

1. 서버 프로세스 기동 → 모델 체크포인트 로드 (수 초).
2. 로드 완료 전까지 `/health` 는 `status: "starting"`.
3. 로드 완료 후 `"ok"`.
4. `/design` 은 로드 완료 전까진 `503`.

### 4.5 구성

환경 변수 기본:
| 키 | 기본값 | 설명 |
|---|---|---|
| `GD_DESIGNER_HOST` | `127.0.0.1` | 바인드 주소. 공개 시 `0.0.0.0`. |
| `GD_DESIGNER_PORT` | `8000` | |
| `GD_DESIGNER_CHECKPOINT` | `./checkpoints/latest` | 모델 weight 경로 |
| `ANTHROPIC_API_KEY` | (없음) | Planner 활성화에 필수 |
| `GD_DESIGNER_LOG_LEVEL` | `INFO` | |

---

## 5. Contract Test 지침

### 5.1 Fixture 페어

`docs/fixtures/api/` 아래 요청/응답 짝.

예:
```
docs/fixtures/api/
├── design_basic/
│   ├── request.json
│   └── response.json
├── design_invalid_layout/
│   ├── request.json
│   └── response.json      # 400 에러 응답
└── plan_basic/
    ├── request.json
    └── response.json
```

### 5.2 ml 쪽 테스트

```python
# ml/tests/serve/test_api_contract.py
@pytest.mark.parametrize("case", list_fixture_cases())
def test_contract(case, monkeypatch, client):
    monkeypatch.setattr("inference.run_pipeline", make_stub_for(case))
    resp = client.post("/design", json=case.request)
    assert resp.status_code == case.expected_status
    assert resp.json() == case.expected_response
```

### 5.3 mod 쪽 테스트

FastAPI 서버를 띄우기는 부담 → **fake HTTP 서버** 사용:
- `mod/tests/net/FakeServer.cpp` — 요청 받으면 미리 로드한 `response.json` 을 그대로 반환.
- `DesignerClient` 가 이 fake 에 붙어서 왕복 테스트.

---

## 6. cURL 예시 (개발용)

```bash
# 헬스
curl http://localhost:8000/health

# 설계 요청
curl -X POST http://localhost:8000/design \
  -H 'Content-Type: application/json' \
  -d @docs/fixtures/api/design_basic/request.json

# 플래너만
curl -X POST http://localhost:8000/plan \
  -H 'Content-Type: application/json' \
  -d @docs/fixtures/api/plan_basic/request.json

# Swagger UI (개발 시)
open http://localhost:8000/docs
```

---

## 7. 변경 이력

| 버전 | 날짜 | 변경 |
|---|---|---|
| 1.0 | 2026-04-23 | 초기 5개 엔드포인트 정의 |
