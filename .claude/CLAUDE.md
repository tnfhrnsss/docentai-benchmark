# docentai-benchmark

Gemini vs Kanana 한국어 자막 설명 품질 벤치마크 프로젝트.
DocentAI 서비스의 멀티 LLM 아키텍처 도입을 위한 실증 비교 실험.

## 프로젝트 구조

```
docentai-benchmark/
├── dataset/
│   ├── test_cases.json       # 테스트 케이스 (15개, 속어/사극/방언)
│   └── scoring_rubric.md     # 채점 기준
├── scripts/
│   ├── run_benchmark.py      # 두 서버 순차 호출 → responses_*.json 저장
│   ├── claude_judge.py       # LLM-as-a-Judge (Claude API, swap average)
│   └── auto_score.py         # 키워드 기반 빠른 사전 점검
└── results/
    ├── responses_*.json      # 모델 응답 전문
    └── judge_scores.csv      # 최종 채점 결과
```

## 환경 변수

```bash
DOCENTAI_LOCAL_URL=http://localhost:8001       # 로컬 DocentAI (Kanana)
DOCENTAI_GCP_URL=https://docentai-api-xxx.run.app  # GCP DocentAI (Gemini)
ANTHROPIC_API_KEY=sk-ant-...                   # Claude Judge용
```

## 실행 순서

```bash
# 1. 로컬 DocentAI 서버 먼저 실행 (docentai-core 디렉터리에서)
uvicorn app.main:app --reload --port 8001

# 2. 벤치마크 실행 (로컬 Kanana → GCP Gemini 순차 호출)
python scripts/run_benchmark.py --model all --repeat 3

# 3. Claude Judge 채점
python scripts/claude_judge.py --input results/responses_YYYYMMDD_HHMMSS.json

# 4. 결과 커밋
git add results/judge_scores.csv results/responses_*.json
git commit -m "feat: add benchmark results"
```

## responses_*.json 형태

`run_benchmark.py`가 DocentAI `/api/explanations/videos/{id}` 응답을 아래 형식으로 변환 저장함.
Claude Judge는 `response` 필드 텍스트만 채점하므로 DocentAI 원본 응답 구조를 바꿀 필요 없음.

```json
{
  "case_id": "A-01",
  "model": "kanana",
  "subtitle": "TMI인데 나 걔한테 솔직히 어장이었잖아...",
  "response": "어장은 낚시에 비유한 연애 신조어로...",
  "source": "환승연애3"
}
```

## Claude Judge 설계

- **Judge 모델**: Claude (Anthropic) — Gemini·Kanana 어느 쪽과도 이해관계 없는 제3자
- **Positional bias 제거**: A=Gemini/B=Kanana, A=Kanana/B=Gemini 순으로 2회 채점 후 평균 (swap average)
- **일관성 플래그**: 두 라운드 승자가 다르면 `consistent=False` → 수동 검토
- **채점 항목**: 정확성(0~3) + 맥락 연결성(0~3) + 자연스러움(0~2) + 문화적 뉘앙스(0~2) = 10점

## 테스트 케이스 카테고리

| ID | 카테고리 | 대표 출처 |
|----|----------|-----------|
| A-01~05 | 속어·신조어 | 환승연애3, 나는 솔로, 스우파2, 유퀴즈, 케데헌 |
| B-01~05 | 사극·고어체 | 태종 이방원, 옷소매 붉은 끝동, 킹덤, 연모, 조선 변호사 |
| C-01~05 | 방언·사투리 | 이상한 변호사 우영우, 수리남, D.P., 나의 아저씨, 오징어 게임 |

자막 추가 시 `dataset/test_cases.json`에 항목 추가. ID 규칙: `CUSTOM-01`, `CUSTOM-02` ...

## 관련 리포지토리

- `docentai-core` — AI 백엔드 (FastAPI, 멀티 LLM 클라이언트)
- `docentai` — Chrome Extension
