# GD Design AI

사용자가 지오메트리 대쉬 에디터에서 **레이아웃(게임플레이 오브젝트)** 을 만들면,
AI가 **데코레이션(배경 오브젝트)** 을 자동으로 채워주는 Geode 모드 + 학습 하네스.

- **Planner (LLM):** Anthropic Claude — 테마/밀도/세그먼트 같은 메타 결정
- **Designer (자체 학습):** RL 또는 Diffusion — 실제 오브젝트 배치
- **Phase 1 (현재):** 룰베이스로 end-to-end 검증. 네트워크/학습 없이 에디터 안에서만 동작.

## 디렉토리

```
.
├── mod/      # Geode C++ 모드 (에디터 훅, UI, 데코레이션 적용)
├── ml/       # Python 학습/추론 하네스 (uv)
├── docs/     # 설계 문서 — 먼저 읽기 권장
├── tools/    # 빌드/개발 스크립트
└── CLAUDE.md # AI 협업 컨텍스트
```

## 빠른 시작

### 모드 빌드 & 설치

```bash
cd mod
cmake --preset mac
cmake --build build    # 성공 시 Geode가 .geode 파일을 GD에 자동 설치
```

상세: [docs/DEV_SETUP.md](docs/DEV_SETUP.md)

### 인게임 테스트

1. GD 실행 → Create → 레벨 편집
2. 게임플레이 오브젝트 몇 개 배치
3. 좌상단 **Design** 버튼 클릭
4. 데코 자동 추가 확인, Ctrl+Z로 되돌리기 확인

## 문서

먼저 읽을 순서:

1. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — 전체 시스템 그림
2. [docs/ROADMAP.md](docs/ROADMAP.md) — Phase 1~4 마일스톤
3. [docs/DATA_FORMAT.md](docs/DATA_FORMAT.md) — Layout/DecorationOp 스키마
4. [docs/MOD_API.md](docs/MOD_API.md) — mod ↔ ML 서버 프로토콜
5. [docs/PLANNER.md](docs/PLANNER.md) — LLM planner 설계
6. [docs/DESIGNER.md](docs/DESIGNER.md) — 학습 모델 설계
7. [docs/DEV_SETUP.md](docs/DEV_SETUP.md) — 환경 세팅

## 라이선스

TBD.
