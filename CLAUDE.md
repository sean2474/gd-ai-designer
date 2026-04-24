# Claude Collaboration Context

이 파일은 Claude Code에게 프로젝트 컨벤션과 컨텍스트를 전달합니다.
새 대화 시작할 때 자동으로 읽힘.

## 프로젝트 한 줄

GD 레벨의 게임플레이 레이아웃을 사용자가 만들면, LLM planner + 학습된 designer가 데코를 자동 배치하는 Geode 모드 + ML 하네스.

## 용어집

- **Layout** — 사용자가 에디터에 배치한 *게임플레이* 오브젝트 집합 (블록, 스파이크, 링, 패드, 포털 등). Designer의 입력.
- **Decoration** — 플레이에 영향 안 주는 배경 오브젝트 (3D 블록, 플랜트, 별 등). Designer의 출력.
- **DecorationOp** — "이 좌표에 이 오브젝트 놔라" 같은 출력 명령. Strategy의 반환 타입.
- **Strategy** — `Layout → vector<DecorationOp>` 순수 함수처럼 동작하는 인터페이스. RuleBased / Remote 구현.
- **Planner** — 메타 결정만 하는 LLM (Anthropic). 테마, 밀도, 스타일, 세그먼트 경계.
- **Designer** — 실제 오브젝트 배치를 내놓는 학습 모델 (RL 또는 Diffusion). 자체 학습.
- **Phase N** — 현재 N=1 (룰베이스 only). Roadmap 참고.

## 디렉토리 책임 (엄격히)

| 디렉토리 | Geode/cocos2d 의존? | 책임 |
|---|---|---|
| `mod/src/core/` | **NO** | 순수 데이터 타입. C++로 쓰되 cocos2d 타입 금지. 테스트 대상. |
| `mod/src/strategies/` | **NO** | Layout → DecorationOp 변환 로직. 순수. 테스트 대상. |
| `mod/src/gd/` | YES | GD GameObject ↔ core 어댑터. LayoutReader / DecorationApplier. |
| `mod/src/ui/` | YES | 에디터 버튼, 패널. cocos2d UI. |
| `mod/src/net/` | YES | ML 서버 HTTP 클라이언트 (Phase 2+). |
| `mod/src/config/` | YES | mod.json settings 래퍼. |
| `mod/tests/` | **NO** | Catch2. core/strategies만 테스트. |
| `ml/src/gd_designer/` | — | Python. 학습/추론/서빙. |
| `docs/` | — | 설계 문서. 코드 바꾸면 여기도 갱신. |

## 빌드/실행 명령

```bash
# mod 빌드 + Geode가 GD에 자동 설치
cd mod && cmake --build build

# GD 실행 (Steam 프로필 기준)
geode profile run
# 또는: open "/Users/sean2474/Library/Application Support/Steam/steamapps/common/Geometry Dash/Geometry Dash.app"

# Python 테스트 (ml/ 작업할 때)
cd ml && uv run pytest
```

## 컨벤션

- **C++ 스타일:** C++20. `using namespace geode::prelude;` 는 `gd/`, `ui/`에서만. `core/`, `strategies/`는 `std::`만.
- **파일명:** 헤더 `PascalCase.hpp`, 소스 `PascalCase.cpp`. 테스트는 `Xxx_test.cpp`.
- **네임스페이스:** 최상위 `designer::`. 레이어별 서브: `designer::core::`, `designer::gd::` 등.
- **로그:** `log::info`, `log::warn`. 에러 경로는 alert 띄우지 말고 `log::error` + 사용자 친화 alert는 `ui/` 레이어에서만.
- **커밋 메시지:** 제목은 영어 imperative ("Add X", "Fix Y"). 본문은 한국어/영어 혼용 OK.
- **스크립트 설정:** argparse/CLI flag 지양. 기본은 `config.py` 모듈 상수 또는 설정 파일. 값 변경은 config 편집, 꼭 필요한 override만 최소 arg.

## Never / Always

- **NEVER** `core/`, `strategies/`에서 `Geode/`나 `cocos2d.h`를 include.
- **NEVER** `mod.json`의 `id`, `geode` 버전을 이유 없이 바꾸지 말 것.
- **ALWAYS** DecorationApplier는 GD undo 스택에 한 묶음으로 등록 (사용자 Ctrl+Z 1번으로 전체 되돌리기).
- **ALWAYS** 새 Strategy 구현 후 단위 테스트 최소 1개.
- **ALWAYS** `docs/DATA_FORMAT.md` 와 `ml/src/gd_designer/data/schema.py` 는 싱크 유지.

## 현재 Phase

**Phase 1** — 룰베이스 end-to-end 동작 확인됨 (2026-04-23).
다음 단계는 `docs/ROADMAP.md` 참고.

## 환경

- macOS (darwin 25.x), Apple Silicon
- AppleClang 21+ (C++23 deducing this 필요)
- Geode SDK 5.6.1 @ `/Users/Shared/Geode/sdk` (env `GEODE_SDK`)
- GD 2.2081 (Steam)
