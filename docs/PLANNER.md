# Planner — LLM as Meta Decision Maker

Planner 는 LLM(Anthropic Claude) 이 담당하는 컴포넌트로, **실제 오브젝트 배치를 직접 결정하지 않는다**. 대신 Designer 가 사용할 **메타 결정** (테마, 밀도, 세그먼트 분할, 스타일 힌트) 을 반환한다.

이 설계의 근거: LLM 은 *추상적 의도 이해* 와 *구조화 선택* 에 강하지만, 정확한 좌표/수치 회귀에는 약하다. 그러니까 LLM 은 "이 레벨의 intro 는 어두운 동굴, climax 는 붉은 용암" 같은 결정을 하고, 그걸 받은 Designer(학습 모델)가 픽셀 정확도로 오브젝트를 배치한다.

관련:
- [DATA_FORMAT.md §2.6](DATA_FORMAT.md#26-planneroutput) — PlannerOutput 스키마
- [MOD_API.md §2.2](MOD_API.md#22-post-plan) — HTTP 엔드포인트
- [DESIGNER.md](DESIGNER.md) — 이 계획을 받는 쪽

---

## 1. 역할 경계

| Planner 담당 | Designer 담당 |
|---|---|
| 테마 선택 (cave, space 등) | 어떤 데코 id 를 쓸지 |
| 전역 밀도 (0.0 ~ 1.0) | 개별 오브젝트 좌표 |
| 세그먼트 분할 (x 구간) | 구간 내 구체 패턴 |
| 컬러 팔레트 (채널 ids) | 색 적용 대상 |
| 자유 텍스트 노트 | (참고만) |
| 사용자 프롬프트 해석 | (참고만) |

**불변식:** Planner 는 `DecorationOp` 를 하나도 반환하지 않는다. 그 타입 자체를 LLM 에게 노출하지 않음.

---

## 2. 모델 선택

| 모델 | 용도 | 근거 |
|---|---|---|
| **Claude Sonnet 4.6** (기본) | 프로덕션 | tool_use 구조화 출력, prompt caching, 충분한 품질/가격비 |
| Claude Haiku 4.5 | 미래 고속 모드 | 짧은 세그먼트 계획, 저비용 |
| Claude Opus 4.7 | 어려운 케이스 | 현재 기본 아님 — 비용 과함, 필요 시 escalation |

기본은 Sonnet. `ml/src/gd_designer/planner/client.py` 에서 env 로 오버라이드.

---

## 3. 구조화 출력 (Tool Use)

LLM 이 자유 텍스트로 답하면 파싱이 불안정 → **tool_use** 로 스키마 강제.

```python
PLANNER_TOOL = {
    "name": "submit_plan",
    "description": "Submit the design plan for the given level layout.",
    "input_schema": {
        "type": "object",
        "properties": {
            "theme": {
                "type": "string",
                "enum": ["cave", "space", "forest", "volcano", "cyber", "abstract"],
            },
            "density": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "palette": {
                "type": "array",
                "items": {"type": "integer", "minimum": 1, "maximum": 1010},
                "minItems": 1, "maxItems": 4,
            },
            "segments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "min_x": {"type": "number"},
                        "max_x": {"type": "number"},
                        "style": {"type": "string"},
                        "intensity": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    },
                    "required": ["min_x", "max_x", "style", "intensity"],
                },
                "minItems": 1,
            },
            "notes": {"type": "string"},
        },
        "required": ["theme", "density", "palette", "segments"],
    },
}
```

클라이언트는 `tool_choice={"type": "tool", "name": "submit_plan"}` 로 강제 호출.

---

## 4. 프롬프트 구성

### 4.1 시스템 프롬프트 (cacheable)

- 프로젝트 맥락 설명
- 테마별 스타일 가이드 (각 테마마다 대표 오브젝트/팔레트 예시)
- ObjectKind 설명
- 좋은/나쁜 plan 예시 (few-shot)

길이 ~2000 tokens. **`cache_control: {"type": "ephemeral"}`** 으로 캐싱.

예시 구조 (의사 코드):
```
<role>
You are a design planner for Geometry Dash levels...
</role>

<themes>
<theme name="cave">
  palette: dark browns, oranges
  typical decorations: rocks, stalactites, ambient dust
  ...
</theme>
...
</themes>

<object_kinds>
BLOCK_SOLID (1): 발 디딜 수 있는 표면...
SPIKE (3): 가시, 아래/위/좌/우 방향 존재...
...
</object_kinds>

<examples>
  <example>
    <layout_summary>x=[0,510], 15 blocks, 8 spikes, 2 orbs</layout_summary>
    <user_prompt>어두운 동굴</user_prompt>
    <submitted_plan>{...}</submitted_plan>
  </example>
  ...
</examples>
```

### 4.2 사용자 메시지 (per-request, non-cached)

- Layout 요약 (아래 §5)
- 선택: 사용자 자유 텍스트 (`user_prompt`)

```
<layout>
bbox: x=[0, 510], y=[0, 120]
objects: 23
  - 15x BLOCK_SOLID (x in [90, 450], y=0)
  - 6x SPIKE (x in [180, 420], y=15)
  - 2x ORB (x=[210, 360], y=[75, 90])
kind_distribution: block=65%, spike=26%, orb=9%
density: 0.18 (23 / (510*120 / 900))
</layout>

<user_hint>
우주 스테이션 느낌, 보라 계열
</user_hint>

<instruction>
Submit a plan via the submit_plan tool.
</instruction>
```

### 4.3 Layout 요약 전략

LLM 에 `Layout.objects` **원본 배열을 통째로 주지 않는다**. 이유:
- 1000 오브젝트 레벨이면 토큰 폭발.
- LLM 은 좌표 숫자보다 *패턴/분포* 를 알면 충분.

요약 방법 (Python):
```python
def summarize_layout(layout: Layout) -> str:
    kinds = Counter(o.kind for o in layout.objects)
    density = len(layout.objects) / max(1, (layout.max_x - layout.min_x) * (layout.max_y - layout.min_y) / 900)
    # 구간 분할 (x 기준 4~6 세그먼트) 로 각 구간별 kind 분포
    segments = split_and_summarize(layout, n=5)
    return render_to_xml(kinds, density, segments, bbox=...)
```

경험적 크기: 1000 오브젝트 레벨이 ~800 tokens 로 요약됨.

---

## 5. Prompt Caching 전략

### 5.1 캐시 레이아웃

시스템 프롬프트의 각 블록에 `cache_control` 배치:

```python
system = [
    {"type": "text", "text": ROLE, "cache_control": {"type": "ephemeral"}},
    {"type": "text", "text": THEMES_GUIDE, "cache_control": {"type": "ephemeral"}},
    {"type": "text", "text": OBJECT_KINDS, "cache_control": {"type": "ephemeral"}},
    {"type": "text", "text": FEW_SHOT_EXAMPLES, "cache_control": {"type": "ephemeral"}},
]
```

**효과:** 시스템 프롬프트 ~2000 tokens 가 요청마다 캐시에서 재사용 → 첫 호출만 full cost, 이후 90% 비용 절감.

### 5.2 캐시 무효화

- 시스템 프롬프트 수정 시 캐시 무효화 (자동).
- 버전 관리: `PLANNER_PROMPT_VERSION = "2026-04-23-v1"` 상수. 로그에 항상 찍기.

### 5.3 캐시 히트 모니터링

응답의 `usage.cache_read_input_tokens` / `usage.cache_creation_input_tokens` 로 히트율 추적. Phase 3 종료 기준에 "히트율 > 80%" 포함.

---

## 6. 재시도 / 검증

### 6.1 검증 파이프라인

1. Anthropic 응답 받음 → `tool_use` 블록 추출.
2. `PlannerOutput.model_validate(...)` — pydantic.
3. 비즈니스 검증:
   - `segments` 의 min_x/max_x 가 Layout bbox 안에 있나
   - segments 가 x 축으로 중첩 없이 정렬 가능한가
   - palette 의 color_channel id 가 유효한가 (허용 범위)
4. 실패 시 §6.2.

### 6.2 재시도

최대 2회 재시도. 프롬프트에 "이전 시도가 왜 실패했는지" 를 추가 메시지로 삽입:
```
Your previous plan was rejected: density out of range (got 1.5, expected 0.0~1.0). Please submit a corrected plan.
```

2회 모두 실패 → `PLANNER_FAILED` 로 400 반환, mod 는 Planner 건너뛰고 Designer 호출 (기본 theme/density 사용).

### 6.3 결정성

- Temperature = 0.3 기본. 사용자가 "다른 느낌 한 번 더" 를 원하면 재호출 시 temperature = 0.7.
- `seed` 파라미터: Anthropic API 에는 없음. 완전 결정성은 불가. 로깅으로 보완.

---

## 7. 비용 제어

### 7.1 토큰 예산

- System prompt: ~2000 tokens (cached)
- User prompt (layout summary + hint): ~500~1500 tokens
- Tool output: ~200 tokens
- **요청당** : 캐시 히트 시 ~100 cached read + ~2000 fresh + ~200 output ≈ $0.005 (Sonnet 4.6 기준)
- 캐시 미스 시 ~$0.03

### 7.2 요청 제한

- 사용자당 분당 10회 (Phase 3).
- 동일 Layout 해시 → 5분간 결과 캐시 (서버 사이드 LRU 100엔트리).

### 7.3 긴 Layout 요약 절약

1만 오브젝트 넘는 레벨 → Layout 전체 요약 대신 bbox 를 여러 청크로 나눠 각각 plan. 전체 plan은 합성.

---

## 8. 로깅 / 관측

매 호출마다 기록 (서버 로그):
- `request_id`, `PLANNER_PROMPT_VERSION`, `model`, `temperature`
- Input: Layout 요약의 해시, user_prompt 원문 (민감 정보 아님 전제)
- Usage: input_tokens, cache_read, cache_create, output_tokens
- Output: `PlannerOutput` 전체 + 검증 결과
- Latency: API 호출 시간, 검증 시간

`ml/src/gd_designer/planner/logging.py` 에서 구조화 JSON 로그.

---

## 9. 디버깅

### 9.1 `/plan` 엔드포인트 단독 호출

개발 중에는 `/design` 전체 파이프라인 말고 `/plan` 만 치면 됨. Swagger UI (`/docs`) 에서 바로.

### 9.2 프롬프트 덤프

환경 변수 `GD_DESIGNER_PLANNER_DUMP=1` 이면 각 호출의 full system/user prompt 와 응답을 `runs/planner-dumps/{timestamp}.json` 에 저장. 오프라인 재현 가능.

### 9.3 오프라인 평가

`ml/scripts/eval_planner.py`:
- 입력: 레이아웃 fixture 폴더
- 처리: 각 레이아웃에 대해 plan 생성, 수동 평가 + 자동 지표 (다양성, valid 비율)
- 출력: 비교표 (예전 프롬프트 버전 vs 새 버전)

---

## 10. 확장 가능성

### 10.1 도메인 특화 fine-tuning

Anthropic 의 fine-tuning 아직 구조 한정적. 단기 비계획. 필요 시 OpenAI 계열로 교차 검증.

### 10.2 멀티턴

사용자가 "다시, 좀 더 밝게" 같은 수정 요청 → 현재 plan 을 컨텍스트에 넣고 재호출. UI 로 채팅처럼.

### 10.3 Tools 확장

- `query_similar_levels` — Designer 학습 데이터에서 비슷한 레이아웃 검색해 참고.
- `sample_palette` — 컬러 팔레트 추천 서비스 연동.

이건 Phase 5+.

---

## 11. 실패 모드 체크리스트

Phase 3 개발 중 확인:
- [ ] API 키 없음 → 명확한 에러 메시지, 서버 기동은 OK (Planner 비활성)
- [ ] 네트워크 끊김 → 재시도 → 실패 → `PLANNER_FAILED`
- [ ] tool_use 응답 안 옴 (모델이 tool 안 호출) → 프롬프트에 "You MUST call submit_plan" 강조
- [ ] Invalid enum 값 → pydantic 에러 → 재시도
- [ ] 너무 긴 segments 배열 → maxItems 제한
- [ ] 한글 사용자 프롬프트 → 정상 처리되는지 (UTF-8)

---

## 12. 참고

- [Anthropic API docs: Tool use](https://docs.anthropic.com/claude/docs/tool-use)
- [Anthropic: Prompt caching](https://docs.anthropic.com/claude/docs/prompt-caching)
- 내부: `ml/src/gd_designer/planner/` 구현 + 테스트
