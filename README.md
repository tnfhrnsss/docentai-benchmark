# docentai-benchmark

**Gemini vs Kanana — 한국어 자막 설명 품질 벤치마크**

[![DocentAI](https://img.shields.io/badge/Project-DocentAI-blue)](https://github.com/tnfhrnsss/docentai-core)
[![Dataset](https://img.shields.io/badge/Dataset-15_cases-green)]()
[![License](https://img.shields.io/badge/License-MIT-yellow)]()

한국 드라마·영화 자막 설명 태스크에서 Google Gemini와 카카오 Kanana를 실증 비교한 벤치마크 리포지토리입니다.  
[DocentAI](https://github.com/tnfhrnsss/docentai-core) 서비스의 멀티 LLM 아키텍처 도입 과정에서 수행한 실험입니다.

---

## 배경

DocentAI는 Netflix·YouTube 자막을 AI로 해설하는 서비스입니다. 한국어 콘텐츠 특화 모델인 Kanana의 베타테스터 활동을 계기로, 실제 서비스 워크로드(속어·신조어·사극·방언)에서 두 모델을 비교했습니다.

## 데이터셋

총 **15개 테스트 케이스**, 3개 카테고리:

| 카테고리 | 케이스 | 대표 출처 |
|----------|--------|-----------|
| A. 속어·신조어 | 5개 | 환승연애3, 나는 솔로, 스우파2 등 |
| B. 사극·고어체 | 5개 | 태종 이방원, 킹덤, 옷소매 붉은 끝동 등 |
| C. 방언·사투리 | 5개 | 이상한 변호사 우영우, 수리남, 나의 아저씨 등 |

→ [`dataset/test_cases.json`](dataset/test_cases.json)

## 평가 기준

10점 만점 · 4개 항목:

- **정확성** (0~3점): 어휘·문법 의미의 사실 정확도
- **맥락 연결성** (0~3점): 드라마·영화 서사 맥락과의 연결
- **자연스러움** (0~2점): 한국어 답변의 자연스러움
- **문화적 뉘앙스** (0~2점): 세대·지역·시대 뉘앙스 포착

→ [`dataset/scoring_rubric.md`](dataset/scoring_rubric.md)

## 리포지토리 구조

```
docentai-benchmark/
├── README.md
├── dataset/
│   ├── test_cases.json       # 15개 테스트 케이스
│   └── scoring_rubric.md     # 채점 기준 상세
├── results/
│   ├── scores_template.csv   # 채점 기록 템플릿
│   ├── raw_results_*.csv     # 실험 측정 데이터 (실험 후 추가)
│   ├── responses_*.json      # 모델 응답 전문 (실험 후 추가)
│   └── scores.csv            # 최종 채점 결과 (실험 후 추가)
├── scripts/
│   ├── run_benchmark.py      # 벤치마크 실행 스크립트
│   └── auto_score.py         # 키워드 기반 자동 채점
└── report/
    └── report_template.md    # 최종 보고서 템플릿
```

## 실행 방법

```bash
git clone https://github.com/tnfhrnsss/docentai-benchmark
cd docentai-benchmark

pip install google-generativeai requests

export GEMINI_API_KEY=your_gemini_key
export KANANA_API_KEY=your_kanana_key

# 전체 실험
python scripts/run_benchmark.py --model all

# 카테고리별 실험
python scripts/run_benchmark.py --model all --category slang

# 단일 케이스 테스트
python scripts/run_benchmark.py --model all --case-id A-01

# 자동 채점
python scripts/auto_score.py --input results/responses_YYYYMMDD_HHMMSS.json
```


바로 테스트하려면:
export DOCENTAI_LOCAL_URL=http://localhost:7777
python scripts/run_benchmark.py --model kanana --case-id A-01 --repeat 1


## 결과

> 실험 진행 중 — 결과는 순차적으로 업데이트됩니다.

## 관련 리포지토리

| 리포지토리 | 설명 |
|------------|------|
| [docentai-core](https://github.com/tnfhrnsss/docentai-core) | AI 백엔드 (FastAPI + 멀티 LLM) |
| [docentai](https://github.com/tnfhrnsss/docentai) | Chrome Extension |

## License

MIT
