# Architecture

## 한 줄 요약

**Geometry Dash 에디터 안의 사용자 레이아웃 → LLM 플래너의 메타 결정 → 학습된 디자이너의 데코 배치 → 에디터에 돌려쓰기**, 이 파이프라인을 네 개의 엄격히 분리된 계층(C++ 모드 · 순수 로직 코어 · Python 추론 서버 · LLM API)으로 구현한다.

---

## 1. 설계 원칙 (Design Tenets)

이 프로젝트는 아래 5가지 원칙 위에 세워졌다. 이 원칙들은 모든 하위 결정을 정당화한다.

### 1.1 관심사 분리 (Separation of Concerns)

코드는 세 축을 따라 쪼갠다.
- **순수(pure) vs 비순수(impure)**: Geode/cocos2d API에 의존하는 코드와 아닌 코드를 섞지 않는다.
- **로컬(in-process) vs 원격(out-of-process)**: C++에 학습된 모델을 묶지 않는다. ML은 별도 프로세스.
- **동기(synchronous) vs 비동기(asynchronous)**: 사용자 조작은 비동기, 순수 로직은 동기.

이 분리는 *편의*가 아닌 *필수*다. 섞으면 테스트 불가능해지고 Geode/GD 업데이트마다 ML 코드까지 회귀 테스트해야 한다.

### 1.2 순수 코어 (Pure Core)

`mod/src/core/` 와 `mod/src/strategies/` 는 cocos2d, Geode, GD 바인딩을 **전혀** include하지 않는다. 오직 `std::` 와 프로젝트 내 헤더만.

효과:
- 데스크톱에서 단위 테스트 가능 (GD 띄울 필요 없음).
- 컴파일 오류가 로직 버그인지 바인딩 미스매치인지 바로 구분.
- 향후 Wasm/네이티브 CLI로 같은 로직 돌릴 수 있음.

### 1.3 전략 교체 (Pluggable Strategy)

`Strategy` 인터페이스 하나만 만족하면 교체 가능:
```cpp
class IStrategy {
public:
    virtual ~IStrategy() = default;
    virtual std::vector<DecorationOp> design(const Layout& in) = 0;
};
```
구현:
- `RuleBasedStrategy` — Phase 1, 네트워크 없음, 테스트 가능
- `RandomStrategy` — 디버그/fuzz 테스트용
- `RemoteStrategy` — Phase 2+, ML 서버에 HTTP 호출

UI와 에디터 코드는 `IStrategy` 만 안다. 구현 교체는 `config/Settings` 에서 플래그 한 줄로.

### 1.4 트랜잭션 적용 (Transactional Apply)

사용자가 **Design** 을 누른 결과는 GD undo 스택에 **1 묶음** 으로 등록. Ctrl+Z 한 번으로 모든 데코가 사라진다. 이건 UX 필수 + 테스트 용이성 (상태 리셋 쉬움).

### 1.5 실패 격리 (Fault Isolation)

네트워크 타임아웃, 모델 OOM, JSON 파싱 실패 — 이 셋 중 어떤 것도 GD 프로세스를 크래시시키면 안 된다. 원격 Strategy는 모든 실패를 `Result<T, Error>` 로 감싸서 UI가 alert으로 표시. 로컬 RuleBased로 자동 폴백 옵션도 제공.

---

## 2. 시스템 구성 (System Components)

### 2.1 Block Diagram

```
┌─────────────────────────────────────────────────────────────┐
│  User (Editor)                                              │
└──────────────────────────┬──────────────────────────────────┘
                           │ click "Design"
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  mod/ — Geode C++ shared library (.geode)                   │
│  ┌──────────────────┐   ┌────────────────────────────────┐  │
│  │ ui/              │──▶│ gd/                            │  │
│  │  EditorButton    │   │  LayoutReader                  │  │
│  │  DesignerPanel   │◀──│  DecorationApplier             │  │
│  │  ProgressPopup   │   │  EditorContext                 │  │
│  └─────────┬────────┘   └─────────┬──────────────────────┘  │
│            │                      │                         │
│            │            ┌─────────▼──────────┐              │
│            │            │ core/              │              │
│            │            │  Layout            │              │
│            │            │  DecorationOp      │              │
│            │            │  ObjectIDs         │              │
│            │            │  Geometry          │              │
│            │            └─────────▲──────────┘              │
│            │                      │                         │
│            │            ┌─────────┴──────────┐              │
│            └───────────▶│ strategies/        │              │
│                         │  RuleBasedStrategy │              │
│                         │  RandomStrategy    │              │
│                         │  RemoteStrategy ───┼──────┐       │
│                         └────────────────────┘      │       │
│                                                     │       │
│                         ┌────────────────────┐      │       │
│                         │ net/               │◀─────┘       │
│                         │  DesignerClient    │              │
│                         └─────────┬──────────┘              │
└───────────────────────────────────┼─────────────────────────┘
                                    │ HTTP/JSON (localhost by default)
                                    ▼
┌─────────────────────────────────────────────────────────────┐
│  ml/ — Python FastAPI service                               │
│  ┌────────────────────┐    ┌────────────────────────────┐   │
│  │ serve/api.py       │───▶│ planner/                   │   │
│  │  POST /design      │    │  client.py (Anthropic)     │   │
│  │  POST /plan        │    │  prompts/                  │   │
│  └────────────────────┘    └────────────┬───────────────┘   │
│           │                             │                   │
│           ▼                             ▼                   │
│  ┌────────────────────┐         ┌────────────────────┐      │
│  │ models/            │         │ Anthropic API      │──┐   │
│  │  diffusion/        │         │ (Claude Sonnet)    │  │   │
│  │  rl/               │         └────────────────────┘  │   │
│  │  baselines/        │                                 │   │
│  └────────────────────┘                                 │   │
└─────────────────────────────────────────────────────────┼───┘
                                                          │
                                                          ▼
                                                  External service
```

### 2.2 프로세스 경계

| 경계 | 통신 | 근거 |
|---|---|---|
| UI ↔ Core | 함수 호출 | 같은 프로세스, 동기 OK |
| mod ↔ ml | HTTP/JSON over localhost | 언어/런타임 분리, ML 재시작이 GD 재시작과 독립 |
| ml ↔ Anthropic | HTTPS + API key | 표준 SaaS 호출 |

**왜 IPC 대신 HTTP?** — 언어 경계 (C++↔Python) 넘는 표준화된 직렬화 + 언제든 ML 서버를 다른 머신(GPU 서버)으로 옮길 수 있음 + FastAPI 디버깅 도구(Swagger UI) 활용 가능.

### 2.3 배포 토폴로지

| 시나리오 | mod 위치 | ml 위치 |
|---|---|---|
| Phase 1 (현재) | 사용자 GD | 없음 — 룰베이스만 in-process |
| Phase 2 로컬 개발 | 사용자 GD | 동일 머신 localhost:8000 |
| Phase 3 베타 | 사용자 GD | 개발자 GPU 서버 (또는 Modal/RunPod) |
| Phase 4 릴리즈 | 사용자 GD | 공개 엔드포인트 + 레이트 리밋 |

---

## 3. 데이터 플로우 (Data Flow)

### 3.1 사용자가 Design을 누른 순간 (Happy Path, Phase 2+)

```
[t=0ms]  ui::EditorButton::onClick
           │
[t=1]    ui → gd::EditorContext::getCurrentEditor()
           │ (즉시, 캐시됨)
           │
[t=2]    gd::LayoutReader::readLayout(editor)
           │ GD의 m_objects iterate → core::LayoutObject 벡터 생성
           │ 게임플레이만 필터 (ObjectKind::DECORATION 제외)
           │
[t=5]    core::Layout { objects, bbox, metadata }
           │
[t=6]    strategies::RemoteStrategy::design(layout)
           │  → net::DesignerClient::request(...)
           │       JSON 직렬화 (schema: docs/DATA_FORMAT.md)
           │       HTTP POST localhost:8000/design
           │
[t=7]    ui::ProgressPopup::show() — 타이머 시작
           │ (메인스레드 블로킹 방지: net::DesignerClient는 async)
           │
         ┌─ 다른 스레드 또는 Geode 코루틴 ─────────────────────┐
         │                                                     │
         │ ml/serve::POST /design                              │
         │   planner::run(layout) → 플랜 (테마/밀도/섹션)       │
         │     → Anthropic API (tool_use 구조화 출력)          │
         │   models::designer.infer(layout, plan) → 오브젝트들  │
         │   응답 JSON 반환                                     │
         │                                                     │
         └─────────────────────────────────────────────────────┘
           │
[t=2~30s] (플랜 200ms + 추론 수 초)
           │
           │ net::DesignerClient 콜백
           │   JSON 역직렬화 → core::DecorationOp 벡터
           │
[t=後]   gd::DecorationApplier::apply(editor, ops)
           │ Undo 스택 begin
           │ for op in ops: editor->createObject(op.id, op.pos, ...)
           │ Undo 스택 end
           │
[t=後+1] ui::ProgressPopup::close()
           │ ui::alert("Placed N decorations")
           │
[t=後+2] 사용자가 에디터에서 결과 즉시 확인
```

### 3.2 실패 경로

| 실패 지점 | 감지 | 복구 |
|---|---|---|
| 레이아웃 빈 | `layout.objects.empty()` | Alert "No gameplay objects" |
| HTTP 타임아웃 (30s) | `net::DesignerClient::timeout` | Alert + `settings.fallbackToLocal` 이면 RuleBased로 재시도 |
| 스키마 검증 실패 | `json::parse` 또는 pydantic | Alert "Server returned invalid response", 로그에 raw 응답 |
| 오브젝트 ID 미지원 | `ObjectIDs::isKnown(id) == false` | 스킵 + `log::warn` |
| Apply 중 GD 크래시 | (불가 영역) | 방어할 수 없음; 스모크 테스트로 사전 방지 |

### 3.3 동시성 모델

- **메인 스레드 (Cocos2d UI)** — 입력/렌더링. 블로킹 금지.
- **백그라운드 스레드** — `net::DesignerClient` 가 소유. libcurl 콜백을 스케줄링.
- **메인 스레드 복귀** — 응답은 `geode::Loader::get()->queueInMainThread(...)` 로 UI 업데이트.
- **재진입 금지** — 사용자가 Design을 두 번 빠르게 누르면 두 번째는 무시 (`isRequestInFlight` 플래그).

---

## 4. 레이어 책임 (Layer Responsibilities)

### 4.1 `mod/src/core/`

*순수 데이터 타입과 도메인 불변식.*

| 파일 | 역할 |
|---|---|
| `Layout.hpp` | `LayoutObject` 구조체, `Layout` 컨테이너 (objects + bbox + meta) |
| `DecorationOp.hpp` | `DecorationOp` 구조체 (target objectId, pos, rot, zOrder, color) |
| `Strategy.hpp` | `IStrategy` 추상 인터페이스 |
| `ObjectIDs.hpp` | GD object id → `ObjectKind` 매핑 테이블 + kind 열거형 |
| `Geometry.hpp` | `Vec2`, `Rect`, `AABB` — cocos2d와 독립된 최소 기하 타입 |

**제약:** 이 디렉토리의 어떤 파일도 `#include <Geode/...>` 나 `#include "cocos2d.h"` 금지. 컴파일 타임에 CI로 검증 (grep 기반 가드).

### 4.2 `mod/src/strategies/`

*`IStrategy` 의 구체 구현.*

| 파일 | 역할 |
|---|---|
| `RuleBasedStrategy.{hpp,cpp}` | 하드코딩 규칙 (예: 모든 스파이크 아래에 블록 데코 배치) |
| `RandomStrategy.{hpp,cpp}` | 난수로 데코 뿌림. fuzz 테스트 입력 생성용 |
| `RemoteStrategy.{hpp,cpp}` | `net::DesignerClient` 호출 (Phase 2+) |

**제약:** core만 의존. `gd/` 나 `ui/` 불러오지 않음.

### 4.3 `mod/src/gd/`

*GD/Geode 타입과 `core` 사이의 어댑터.*

| 파일 | 역할 |
|---|---|
| `LayoutReader.{hpp,cpp}` | `LevelEditorLayer* → core::Layout` 변환 |
| `DecorationApplier.{hpp,cpp}` | `vector<DecorationOp> → editor->createObject(...)` + undo 래핑 |
| `EditorContext.{hpp,cpp}` | 현재 에디터 포인터 획득, 플레이어 시점, 그리드 스냅 등 헬퍼 |

**제약:** core에 의존. `ui/`, `strategies/` 에 의존 안 함 (역참조 금지).

### 4.4 `mod/src/ui/`

*에디터 위 UI 위젯.*

| 파일 | 역할 |
|---|---|
| `EditorButton.{hpp,cpp}` | `$modify(EditorUI)` 훅으로 "Design" 버튼 추가 |
| `DesignerPanel.{hpp,cpp}` | 옵션 패널 (밀도 슬라이더, 스타일 드롭다운, 재생성 버튼) |
| `ProgressPopup.{hpp,cpp}` | 비동기 호출 시 로딩 스피너 + 취소 |

**의존:** `gd/`, `strategies/`, `config/`. 로직은 최소화, 순수 발표 (presentation).

### 4.5 `mod/src/net/`

*HTTP 클라이언트. Phase 2 이전엔 비어있거나 존재하지 않음.*

| 파일 | 역할 |
|---|---|
| `DesignerClient.{hpp,cpp}` | `request(Layout) → Future<DecorationOp[]>`. libcurl 래퍼. 타임아웃/재시도. |
| `Serialization.{hpp,cpp}` | `core::Layout ↔ JSON`, `core::DecorationOp ↔ JSON`. nlohmann/json. |

**의존:** core만. `ui/` 에게는 `Future<T>` 로만 노출.

### 4.6 `mod/src/config/`

*사용자 설정.*

| 파일 | 역할 |
|---|---|
| `Settings.{hpp,cpp}` | `mod.json` settings 스키마와 1:1 대응하는 타입드 래퍼 |

Phase 1 시점의 설정 후보:
- `strategy`: `rule_based | random | remote`
- `server_url`: `http://localhost:8000`
- `fallback_to_local`: `bool`
- `density`: `0.0 ~ 1.0`
- `theme`: string
- `api_key`: secret (UI에서 직접 입력, `mod.json` 에는 저장 금지)

### 4.7 `mod/src/util/`

*모든 레이어가 공유하는 유틸. 최소화.*

| 파일 | 역할 |
|---|---|
| `Log.hpp` | `LOG_INFO(...)`, `LOG_WARN(...)`, `LOG_ERROR(...)` — 로그 포맷 통일 |

---

## 5. 확장 포인트 (Extension Points)

새 기능을 추가할 때 **어느 레이어에 어떤 형태로 들어가는지** 가 결정돼있어야 한다. 다음은 예상되는 확장과 그 정답 레이어.

| 확장 | 레이어 | 형태 |
|---|---|---|
| 새 Strategy (예: 템플릿 매칭) | `strategies/` | `IStrategy` 상속 클래스 |
| 새 `ObjectKind` (예: "saw") | `core/ObjectIDs.hpp` | 매핑 테이블 row + enum 값 |
| 새 UI 버튼 (예: "Explain") | `ui/` | 새 `.cpp`, `EditorUI::init`에서 addChild |
| 새 API 엔드포인트 (예: `/style`) | `net/` + `ml/serve/` | `DesignerClient` 메서드 + FastAPI 라우트 |
| 새 Planner 프롬프트 | `ml/src/gd_designer/planner/prompts/` | 텍스트 파일 + 로더 |
| 새 Designer 모델 | `ml/src/gd_designer/models/` | 패키지 추가, `serve/inference.py` 에서 라우팅 |

---

## 6. 비기능 요구사항 (Non-Functional Requirements)

### 6.1 성능 예산 (Performance Budget)

| 동작 | 목표 | 이유 |
|---|---|---|
| RuleBased end-to-end | < 100ms | 사용자가 "즉시" 라고 느끼는 한계 |
| Planner 호출 | < 2s | Anthropic 표준 응답 시간 |
| Designer 추론 (MVP) | < 10s | 기다릴 수 있되 커피 안 갖다오는 한계 |
| Design → 화면 반영 | 누적 < 15s | 위 3개의 합 상한 |
| 오브젝트 1000개 읽기 | < 30ms | 대형 레벨 허용 |
| 오브젝트 500개 apply | < 200ms | GD 내부 createObject 한계 |

### 6.2 메모리

- mod 상주: < 10MB 추가 RSS (GD 위에서)
- `net::DesignerClient` 직렬화 버퍼: 오브젝트 N개당 O(N), 상수 < 1KB/오브젝트

### 6.3 신뢰성

- ML 서버 다운 시에도 mod는 정상 로드 (원격 호출 시점에만 실패)
- 사용자 네트워크 없음 → `strategy=rule_based` 로 여전히 동작
- API 키 유출 방지: `mod.json` 에 넣지 않음. Geode 내장 설정 시스템의 암호화 저장소 이용 (Phase 2 설계 시 확정)

### 6.4 호환성

- Geode SDK 5.6.x
- GD 2.2081 (현재). 2.2082 같은 마이너 업데이트 시 바인딩만 재생성하면 충분하도록 설계.
- macOS 11.0+, Windows/Linux는 현재 빌드 대상 외 (향후 확장 가능).

---

## 7. 기술 선택 (Technology Decisions)

각 결정에 대해 **대안 + 선택 이유** 를 남긴다. 나중에 바꿀 때 근거를 알 수 있게.

### 7.1 C++20 on mod, Python on ml

- **대안 1:** 전부 C++ (학습도 libtorch). 거부 — PyTorch 학습 생태계 포기.
- **대안 2:** 전부 Python (mod도 Python 바인딩). 거부 — Geode는 C++ 전용.
- **선택:** C++/Python 분리. 경계는 HTTP.

### 7.2 HTTP/JSON, not gRPC/protobuf

- **대안:** gRPC. 거부 — Geode에서 C++ gRPC 클라이언트 링크 복잡, 스키마 변경 비용 큼.
- **선택:** HTTP/JSON (nlohmann/json + FastAPI/pydantic). 스키마 소스 = `docs/DATA_FORMAT.md`.

### 7.3 FastAPI, not Flask

- FastAPI는 pydantic 기반 자동 검증 + OpenAPI 문서 + async 기본. 선택.

### 7.4 uv, not poetry

- `uv` 는 `pyproject.toml` 호환 + Rust 기반 10~100x 빠름. 2025년 이후 사실상 표준.

### 7.5 Anthropic Claude, not OpenAI

- 프로젝트 소유자의 친숙도 + prompt caching + tool use 구조화 출력이 성숙.

### 7.6 Catch2, not GoogleTest

- Catch2 v3는 헤더 온리 + CPM으로 쉬운 통합. Geode 생태계에서도 일부 모드가 사용.

### 7.7 nlohmann/json, not rapidjson

- 가독성 우선 (아직 파싱 성능이 병목 아님). 나중에 성능 필요하면 simdjson으로 갈아낄 수 있게 `net/Serialization.cpp` 로 캡슐화.

---

## 8. 저장소 레이아웃 (Repo Layout, 재참조)

```
gd-design-ai/
├── mod/                          # C++ Geode mod
│   ├── CMakeLists.txt
│   ├── CMakePresets.json
│   ├── mod.json
│   ├── about.md, changelog.md    # Geode 메타
│   ├── resources/                # 아이콘/사운드
│   ├── src/
│   │   ├── main.cpp              # 와이어업만
│   │   ├── core/
│   │   ├── strategies/
│   │   ├── gd/
│   │   ├── ui/
│   │   ├── net/
│   │   ├── config/
│   │   └── util/
│   └── tests/                    # Catch2
├── ml/                           # Python 하네스
│   ├── pyproject.toml
│   ├── src/gd_designer/
│   │   ├── data/                 # schema, dataset, collect
│   │   ├── models/               # diffusion, rl, baselines
│   │   ├── planner/              # Anthropic client, prompts
│   │   ├── train/                # trainer, configs
│   │   ├── eval/                 # metrics, render
│   │   └── serve/                # FastAPI
│   ├── scripts/                  # train.py, eval.py, serve.py, collect_data.py
│   └── tests/
├── docs/                         # 본 문서들
├── data/                         # (gitignored) 원본 / 학습 데이터
├── checkpoints/                  # (gitignored) 모델
├── runs/                         # (gitignored) 실험 로그
├── tools/                        # build-mod.sh, dev-serve.sh 등
├── README.md
└── CLAUDE.md
```

---

## 9. 용어집 보강 (Glossary, inline)

- **ObjectKind** — `BLOCK_SOLID | BLOCK_HALF | SPIKE | ORB_YELLOW | PAD_YELLOW | PORTAL_CUBE | ... | DECORATION_GENERIC`. `core/ObjectIDs.hpp` 에 정의. Designer 입력은 `DECORATION_*` 이 아닌 오브젝트만.
- **Layout.meta** — 사용자 의도를 담는 자유 형식 힌트. 예: `{"theme": "dark", "density": 0.7, "text": "space station"}`. Planner의 추가 입력.
- **DecorationOp.zOrder** — 기본 −1 (게임플레이 뒤). Planner가 `−5` (더 멀리) 또는 `+5` (플레이 앞 파티클) 로 오버라이드 가능.

---

## 10. 열린 질문 (Open Questions)

아직 결정되지 않은 것들. ROADMAP과 연동해서 Phase 진입 전 확정 필요.

1. **오브젝트 ID 커버리지** — GD 2.2081엔 수백 개 ID. 어디까지 "decoration" 후보로 삼을지 (`ObjectIDs.hpp`의 decoration set). 초기엔 10~20개로 시작하고 점진 확장.
2. **사용자 프롬프트 UI** — DesignerPanel에 자유 텍스트 입력 넣을지. Planner가 이걸 받을지.
3. **Undo의 세분화** — 1 Design = 1 undo가 기본. 사용자가 "일부만 undo" 하고 싶으면? (Phase 4 이후 결정)
4. **로컬 모델 번들링** — 작은 모델은 mod 안에 내장할 가능성. ONNX Runtime C++ 링크 타당성 조사 필요.
5. **멀티 유저 레이턴시** — 공개 서버 단계에서 per-request 비용 vs 큐잉 전략.
6. **데이터 수집 합법성** — 다른 사용자 레벨을 학습 데이터로 쓸 때 라이선스/동의 정책.

---

## 11. 참고

- **Geode 문서:** https://docs.geode-sdk.org/
- **GD 오브젝트 ID 참고:** [Pourbaix's GD Resources]에서 업데이트 (링크는 `DEV_SETUP.md` 참고)
- **내부 문서 링크:**
  - [DATA_FORMAT.md](DATA_FORMAT.md) — 직렬화 스키마
  - [MOD_API.md](MOD_API.md) — HTTP API 규격
  - [PLANNER.md](PLANNER.md) — LLM 역할 상세
  - [DESIGNER.md](DESIGNER.md) — 학습 모델 상세
  - [ROADMAP.md](ROADMAP.md) — 단계별 계획
  - [DEV_SETUP.md](DEV_SETUP.md) — 환경 세팅
