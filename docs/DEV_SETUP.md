# Development Setup

이 문서는 **영점에서** 프로젝트를 받아 빌드/실행까지 가는 모든 단계를 기술한다. Phase 2 이후에 ml 파트 추가.

대상 OS: macOS (Apple Silicon). Windows/Linux 는 추후.

관련:
- [README.md](../README.md) — 빠른 시작 요약본
- [ROADMAP.md](ROADMAP.md) — 각 Phase 별 필요 도구

---

## 1. 요구 사항

### 1.1 macOS

- macOS 11.0+ (Big Sur 이상)
- Apple Silicon 권장 (x86_64 도 빌드는 가능)

### 1.2 필수 도구

| 도구 | 최소 버전 | 설치 확인 |
|---|---|---|
| Xcode Command Line Tools | 26.x+ (Clang 21+) | `clang --version` |
| Homebrew | 최신 | `brew --version` |
| CMake | 3.21+ | `cmake --version` |
| Ninja | 1.11+ | `ninja --version` |
| Git | 2.30+ | `git --version` |
| Geode CLI | 3.7+ | `geode --version` |
| Geode SDK | 5.6.1+ | `ls $GEODE_SDK` |
| Geometry Dash | 2.2081 | (Steam 또는 공식) |

Phase 2+ 추가:
| 도구 | 최소 버전 | 설치 확인 |
|---|---|---|
| Python | 3.11+ | `python3 --version` |
| uv | 0.5+ | `uv --version` |

---

## 2. macOS 초기 세팅

### 2.1 Xcode Command Line Tools

Clang 21+ 필요 (C++23 deducing-this 문법 때문). Apple Clang 16 (구식) 에서는 Geode 빌드 실패.

1. `clang --version` 결과가 17 미만이면:
2. https://developer.apple.com/download/all/ 접속 → Apple ID 로그인
3. "Command Line Tools for Xcode 26.x" 다운로드 (.dmg)
4. `.pkg` 실행 → 설치
5. `clang --version` 재확인 → `Apple clang version 21+` 이어야 함

> 팁: `xcode-select --install` 은 구버전이 다시 깔릴 수 있음. developer.apple.com 수동 다운로드가 가장 확실.

### 2.2 Homebrew

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### 2.3 CMake + Ninja

```bash
brew install cmake ninja
```

---

## 3. Geode SDK / CLI

### 3.1 CLI 설치

```bash
brew install geode-sdk/geode/geode-cli
geode --version    # 3.7+ 확인
```

### 3.2 SDK 설치

```bash
geode sdk install              # 기본 경로: /Users/Shared/Geode/sdk
geode sdk install-binaries     # 플랫폼 바인딩 다운로드
```

### 3.3 환경변수 `GEODE_SDK`

SDK 설치 후 `~/.zshrc` 에:
```bash
export GEODE_SDK="/Users/Shared/Geode/sdk"
```

그리고:
```bash
source ~/.zshrc
echo $GEODE_SDK && ls $GEODE_SDK
```

`bindings/`, `loader/`, `cmake/` 등의 디렉토리가 보이면 OK.

### 3.4 GD 설치

공식 경로 둘 중 하나:
- Steam: `~/Library/Application Support/Steam/steamapps/common/Geometry Dash/Geometry Dash.app`
- 단독: `/Applications/Geometry Dash.app`

둘 다 있을 수 있음. 실제 **플레이 가능한 본체** 가 어느 쪽인지 확인.

### 3.5 Geode 프로필 등록

```bash
geode profile add -n steam "/Users/sean2474/Library/Application Support/Steam/steamapps/common/Geometry Dash/Geometry Dash.app"
geode profile switch steam
geode profile list   # * steam 표시 확인
```

잘못된 프로필 있으면:
```bash
geode profile remove <이름>
```

---

## 4. 저장소 클론 + 빌드

### 4.1 클론

```bash
cd ~/Desktop/project   # 원하는 위치
git clone https://github.com/sean2474/gd-ai-designer.git
cd gd-ai-designer
```

### 4.2 mod 빌드

```bash
cd mod
cmake --preset mac
cmake --build build
```

성공 시 `mod/build/sean.gd-design-ai.geode` 파일 생성 + Geode 가 GD 모드 폴더에 자동 설치.

### 4.3 초기 빌드 시간

첫 빌드는 의존성 다운로드/빌드로 **5~15분** 소요:
- Geode SDK 컴파일
- bindings 빌드
- fmt, nlohmann/json, arc, asp, TulipHook 등 CPM 패키지

두 번째 빌드부터는 증분으로 수십 초 내.

### 4.4 경고 처리

- `built for newer 'macOS' version (11.0) than being linked (10.15)` → `CMAKE_OSX_DEPLOYMENT_TARGET` 을 `11.0` 으로 설정해뒀으니 사라져야 함. 나면 CMake cache 문제 → `rm -rf build && cmake --preset mac` 재실행.

---

## 5. GD 에서 모드 실행

### 5.1 실행

Steam 프로필이면 Steam 에서 GD 실행, 아니면:
```bash
open "/Users/sean2474/Library/Application Support/Steam/steamapps/common/Geometry Dash/Geometry Dash.app"
```

### 5.2 모드 확인

1. 메인메뉴 좌하단 **Geode 로고 버튼** 클릭
2. 설치된 모드 목록에 `GD Design AI` 표시 확인
3. Create (+) → 레벨 편집 진입 → 좌상단 `Design` 버튼 보이는지

### 5.3 인게임 스모크 테스트

1. 블록, 스파이크, 점프링 몇 개 배치
2. Design 클릭
3. Alert 에 `Read N / Placed M` 표시 확인
4. Ctrl+Z → 데코만 사라지는지

---

## 6. 개발 사이클

### 6.1 편집 → 빌드 → 테스트 루프

```bash
# 편집: mod/src/...
cd mod
cmake --build build   # 증분 빌드 + 자동 재설치
# GD 재시작 (에디터 진입 필요)
```

### 6.2 로그 확인

Geode 는 자동 로깅. macOS 에서 로그 위치:
```
~/Library/Application Support/Steam/steamapps/common/Geometry Dash/Geometry Dash.app/Contents/geode/logs/
```
마지막 로그 파일 tail:
```bash
tail -f ~/Library/Application\ Support/Steam/steamapps/common/Geometry\ Dash/Geometry\ Dash.app/Contents/geode/logs/*.log
```

### 6.3 `log::info` 사용

C++ 에서:
```cpp
log::info("Designer: layout={}, ops={}", layout.size(), ops.size());
log::warn("Unknown object id: {}", id);
log::error("Failed to apply: {}", err);
```

---

## 7. 테스트

### 7.1 mod (Catch2) — Phase 2+

```bash
cd mod
cmake --preset mac -DGDDESIGNAI_BUILD_TESTS=ON
cmake --build build --target GDDesignAI_tests
./build/tests/GDDesignAI_tests
```

### 7.2 ml (pytest) — Phase 2+

```bash
cd ml
uv sync        # 의존성 설치
uv run pytest
```

### 7.3 Contract tests

```bash
# mod 쪽 fixture 기반
./build/tests/GDDesignAI_tests "[contract]"

# ml 쪽
cd ml && uv run pytest tests/ -m contract

# 크로스 체크 스크립트 (ObjectIDs CSV 싱크)
./tools/check-ids-sync.sh
```

---

## 8. Python (ml) 환경 — Phase 2 이후

### 8.1 uv 설치

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
# 또는: brew install uv
uv --version
```

### 8.2 가상환경 + 의존성

```bash
cd ml
uv sync              # pyproject.toml 기반, .venv 자동 생성
uv run python --version   # Python 3.11+ 확인
```

### 8.3 dev 서버 기동

```bash
uv run uvicorn gd_designer.serve.api:app --reload --port 8000
# 또는: ./tools/dev-serve.sh
```

### 8.4 환경변수

`ml/.env` (gitignore 대상):
```
ANTHROPIC_API_KEY=sk-ant-...
GD_DESIGNER_CHECKPOINT=./checkpoints/latest
GD_DESIGNER_LOG_LEVEL=DEBUG
```

uv 가 자동으로 읽지 않으므로 `ml/src/gd_designer/config.py` 에서 `python-dotenv` 로 로드.

---

## 9. IDE 설정

### 9.1 VS Code 권장

확장:
- C/C++ (Microsoft)
- CMake Tools
- Python (Microsoft)
- Pylance

작업 공간 `.vscode/settings.json` (gitignore 됨, 개인별):
```json
{
  "cmake.configureOnOpen": false,
  "cmake.sourceDirectory": "${workspaceFolder}/mod",
  "cmake.buildDirectory": "${workspaceFolder}/mod/build",
  "cmake.configurePreset": "mac",
  "python.defaultInterpreterPath": "${workspaceFolder}/ml/.venv/bin/python"
}
```

### 9.2 CLion / Xcode

CLion 은 `mod/CMakePresets.json` 을 바로 인식. Xcode 는 CMake 가 `-G Xcode` 프로젝트를 생성하게 할 수 있지만, 본 프로젝트는 Ninja 우선.

---

## 10. 자주 겪는 문제

### 10.1 "Cannot find Geode SDK"

환경 변수 미설정. §3.3 확인. 새 터미널 세션에서 테스트.

### 10.2 `setup_geode_mod` 미존재

`$GEODE_SDK` 가 잘못된 경로. `ls $GEODE_SDK/cmake/GeodeFile.cmake` 확인.

### 10.3 "built for newer macOS" 경고

`CMakeLists.txt` 의 `CMAKE_OSX_DEPLOYMENT_TARGET` 을 11.0 으로. 그래도 나면 `rm -rf build`.

### 10.4 Clang deducing-this 에러

Xcode CLT 가 구식. §2.1 에서 최신 CLT (26.x) 수동 설치.

### 10.5 "Mod sean.gd-design-ai is made for Geode version X but you have Y"

`mod/mod.json` 의 `geode` 필드를 설치된 SDK 버전과 맞춤. `$GEODE_SDK/VERSION` 확인.

### 10.6 GD 실행 시 모드 로드 안 됨

- `geode profile list` 에서 GD 경로가 정확한지
- `geode install mod/build/*.geode` 수동으로 한 번 더 시도
- GD 의 Geode 버튼에서 에러 메시지 확인

### 10.7 Steam GD 와 Standalone GD 혼동

Steam 에 있다면 Applications 폴더 쪽은 껍데기일 가능성. Steam 경로를 프로필로 사용. 데이터:
- Steam: `~/Library/Application Support/Steam/steamapps/common/Geometry Dash/Geometry Dash.app`

### 10.8 ml 서버가 연결 거부

- `curl http://localhost:8000/health` 확인
- 포트 충돌: `lsof -i :8000`
- mod 설정 `server_url` 이 맞는지

---

## 11. 업데이트 절차

### 11.1 Geode SDK 업그레이드

```bash
cd $GEODE_SDK
git pull
cd -
geode sdk install-binaries
# mod/mod.json 의 geode 버전 업데이트
# 재빌드
rm -rf mod/build && cd mod && cmake --preset mac && cmake --build build
```

### 11.2 GD 자체 업그레이드 (2.2082 등)

- Steam 자동 업데이트 후 GD 실행 시 Geode 가 바인딩 자동 재다운로드.
- `mod/mod.json` 의 `gd.*` 버전 필드 업데이트 필요.
- 대개 재빌드 필수.

### 11.3 Python 의존성

```bash
cd ml
uv sync --upgrade      # 잠금 재생성
uv run pytest          # 회귀 확인
```

---

## 12. 체크리스트 — 첫날 온보딩

처음 참여하는 개발자가 하루 안에 다음을 완료해야 Phase 2+ 개발에 진입.

- [ ] `clang --version` 21+ 확인
- [ ] `cmake --version` 3.21+
- [ ] `geode --version` 3.7+, `$GEODE_SDK` 정상
- [ ] `geode profile list` 에서 GD 경로 맞음
- [ ] 저장소 클론
- [ ] `cd mod && cmake --preset mac && cmake --build build` 성공
- [ ] GD 실행 시 Design 버튼 동작 (인게임 스모크)
- [ ] `uv --version` 0.5+ (Phase 2+)
- [ ] `cd ml && uv sync` 성공 (Phase 2+)
- [ ] `docs/ARCHITECTURE.md`, `INTERFACES.md` 읽음
- [ ] GitHub repo access OK, 테스트 PR 1건 열어봄

---

## 13. 참고 링크

- Geode: https://docs.geode-sdk.org/
- Geode CLI reference: https://docs.geode-sdk.org/tutorials/cli
- GD 공식: Steam / https://www.robtopgames.com/
- uv: https://docs.astral.sh/uv/
- Catch2: https://github.com/catchorg/Catch2
- FastAPI: https://fastapi.tiangolo.com/
