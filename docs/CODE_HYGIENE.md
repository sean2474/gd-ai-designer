# Code Hygiene

프로젝트가 커질수록 **쓰이지 않는 파일·함수·의존성** 이 쌓인다. 이것들은:

- 새 사람이 들어올 때 "이거 뭐지?" 혼란을 준다
- 빌드 시간을 늘린다
- 리팩토링할 때 괜히 부담스럽다
- 스키마/계약 싱크 여부를 판단하기 어렵게 한다

이 문서는 **무엇을 정리하고**, **언제 정리하고**, **누가 판단하는지** 의 규칙을 정한다.

관련:
- [INTERFACES.md](INTERFACES.md) — 계약은 보존 대상 (삭제 금지 목록)
- [COLLABORATION.md](COLLABORATION.md) — PR 정책

---

## 1. 담당자

자동 평가: `.claude/agents/code-janitor.md` 서브에이전트가 수행.
- 호출: `/janitor` 슬래시 커맨드 또는 대화 중에 "정리해줘" / "cleanup" 요청
- 출력: 구조화된 리포트 (Safe / Probably / Uncertain 3 섹션)
- **삭제는 수행하지 않음** — 제안만

최종 판단 + 실제 삭제: **사람**.

---

## 2. "필요없다" 의 7가지 기준

아래 중 하나라도 해당하면 후보. 상세는 `.claude/agents/code-janitor.md` §1.

1. **Unreferenced source** — 어떤 다른 소스에서도 include/import 하지 않는 파일
2. **Orphan directory** — CMake/pyproject/docs 어디에도 언급되지 않는 디렉토리
3. **Dead code** — 어떤 caller 에서도 호출하지 않는 함수/클래스
4. **Stale TODO** — 60일 이상 된 TODO, 또는 "X 끝나면 지워" 하고 X 이미 끝난 것
5. **Abandoned experiment** — `test.cpp`, `foo.py`, `scratch/`, `*.bak`, `.DS_Store` 등
6. **Redundant docs** — 다른 문서의 부분집합이거나, README에 링크는 있는데 파일 없음
7. **Dependency bloat** — `pyproject.toml` / CPM 에 등록했지만 아무 모듈이 쓰지 않는 것

---

## 3. 보호 목록 (삭제 금지)

어떤 경우에도 janitor 는 이 파일들을 후보로 올리지 않는다:

- `CLAUDE.md`, `README.md`
- `mod.json`, `CMakeLists.txt`, `CMakePresets.json`, `pyproject.toml`
- `.clangd`, `.gitignore`
- `docs/INTERFACES.md` §8 의 "계약 목록" 표에 있는 모든 파일
- 각 `Contract version:` 주석이 붙은 헤더

---

## 4. 실행 주기

권장:

- **Phase 경계** 마다 1회 (Phase 1 → 2 넘어갈 때 등)
- 대형 리팩토링 **직후**
- 그 외 약 **월 1회**

주기 자동화: Claude Code 의 `/schedule` 로 등록.
```
/schedule cron "0 10 * * 1" /janitor
```
(매주 월요일 오전 10시 janitor 실행)

등록은 **사용자 환경 1회** 해두면 됨.

---

## 5. 리포트 후 워크플로우

1. `/janitor` → 리포트 수신
2. 팀이 리포트 리뷰 (Discord/채팅 공유)
3. 합의된 항목들을 삭제 PR 로 묶음:
   ```
   git rm <file1> <file2> ...
   git commit -m "Chore: prune unreferenced files per janitor report"
   ```
4. PR 에 janitor 리포트 원문 첨부 (증거)
5. 상대방 approve → merge

**안전장치**
- Single PR 에 대량 삭제 넣지 말 것 (실수 복구 어려움). 10 파일 단위로 쪼개기.
- 삭제 전 반드시 빌드/테스트 통과 확인.
- 의심스러우면 그대로 두고 주석만 남기는 것도 선택지 (`// TODO(janitor 2026-05): 6개월 후 재평가`).

---

## 6. 버전 관리 & 복구

- 삭제해도 git 히스토리에 영구 남음. 필요하면 `git log --diff-filter=D --summary` 로 찾아 `git checkout <sha>^ -- <path>` 복구 가능.
- 특정 파일을 영구 보존해야 할 이유가 있으면 **이 문서 §3** 에 추가.

---

## 7. 메트릭 (선택)

장기적으로 "repo 건강" 지표를 간단히 추적하려면:

```bash
# 라인 수 총합
cloc mod/src ml/src

# 참조 안 되는 symbol 수 (heuristic)
# (Phase 3 이후 도입 검토)
```

지금은 janitor 리포트 하나로 충분. 지표 자동화는 나중.

---

## 8. 예시 리포트

```
## Code Janitor Report — 2026-06-15

### ✂️  Safe to delete (2 items)
- **mod/src/core/Geometry.hpp** — unused header.
  Evidence: `grep -rn 'Geometry.hpp'` → 0 hits outside the file itself.

- **tools/old_build.sh** — replaced by tools/build-mod.sh.
  Evidence: no references in docs, Makefile, or CI.

### 🟡  Probably deletable (1 item)
- **ml/src/gd_designer/models/baselines/nearest_neighbor.py** — imported
  nowhere, but Designer.md §5 lists it as a planned baseline.
  Uncertainty: may be WIP, consult branch `b/baselines`.

### 🤔  Uncertain / left alone (3 items)
- **mod/src/ui/EditorButton.hpp** — empty but referenced by documentation.
- **data/samples/** — empty now but reserved for fixtures (DATA_COLLECTION.md §5).
- **docs/fixtures/** — doesn't exist yet, referenced in INTERFACES.md §1.4.

Proposed: delete 2, review 1. To act, run `git rm` after confirming.
```
