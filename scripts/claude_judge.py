"""
DocentAI Benchmark - Claude LLM-as-a-Judge
responses_{timestamp}.json 을 읽어 Claude API로 Gemini vs Kanana 품질 비교 채점

설계:
  - Positional bias 제거: A=Gemini/B=Kanana, A=Kanana/B=Gemini 순으로 2회 채점 후 평균 (swap average)
  - 일관성 플래그: 두 라운드 승자가 다르면 consistent=False → 수동 검토 권장
  - 채점 항목: 정확성(0~3) + 맥락 연결성(0~3) + 자연스러움(0~2) + 문화적 뉘앙스(0~2) = 10점

Usage:
    python scripts/claude_judge.py --input results/responses_20260320_120000.json
    python scripts/claude_judge.py --input results/responses_20260320_120000.json --output results/judge_scores.csv
"""

import json
import csv
import time
import argparse
from pathlib import Path

import anthropic

BASE_DIR = Path(__file__).parent.parent
DATASET_PATH = BASE_DIR / "dataset" / "test_cases.json"

JUDGE_MODEL = "claude-sonnet-4-6"

JUDGE_PROMPT = """당신은 한국 드라마·영화 자막 설명 품질을 평가하는 전문 심사위원입니다.
두 AI 모델이 동일한 자막에 대해 작성한 설명을 아래 기준으로 채점하세요.

## 평가 대상 자막
- 출처: {source}
- 자막: {subtitle}
- 핵심 키워드: {keywords}
- 설명에 포함되어야 할 포인트:
{expected_points}

## 응답 A
{response_a}

## 응답 B
{response_b}

## 채점 기준 (총 10점)

**1. 정확성 (0~3점)**: 어휘·문법 의미가 사실적으로 올바른가
- 3: 모든 핵심 어휘 정확, 오류 없음
- 2: 대부분 정확하나 사소한 오류 1건
- 1: 일부만 정확하거나 중요한 오류 1건
- 0: 오류 많거나 핵심 의미 잘못 설명

**2. 맥락 연결성 (0~3점)**: 드라마 장면·서사 맥락과 연결되는가
- 3: 어휘+장면 맥락+서사적 의미까지 풍부하게 연결
- 2: 어휘+장면 맥락 연결
- 1: 어휘 설명만, 맥락 연결 부족
- 0: 맥락 무시 또는 엉뚱한 맥락

**3. 자연스러움 (0~2점)**: 한국어로 자연스럽고 읽기 편한가
- 2: 자연스럽고 매끄러운 한국어
- 1: 어색한 표현 일부, 이해 가능
- 0: 어색하거나 번역투

**4. 문화적 뉘앙스 (0~2점)**: 세대·지역·시대 문화 뉘앙스를 포착했는가
- 2: 해당 문화권 뉘앙스와 감성 정확히 포착
- 1: 부분적 뉘앙스 설명
- 0: 뉘앙스 누락, 사전적 의미만

## 출력 형식
반드시 아래 JSON 형식으로만 답변하세요. 추가 텍스트 없이 JSON만 출력하세요.
{{
  "A": {{
    "accuracy": <0~3 정수>,
    "context": <0~3 정수>,
    "naturalness": <0~2 정수>,
    "cultural": <0~2 정수>,
    "reason": "<A 채점 근거 1~2문장>"
  }},
  "B": {{
    "accuracy": <0~3 정수>,
    "context": <0~3 정수>,
    "naturalness": <0~2 정수>,
    "cultural": <0~2 정수>,
    "reason": "<B 채점 근거 1~2문장>"
  }}
}}"""


def load_dataset() -> dict:
    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {c["id"]: c for c in data["test_cases"]}


def call_judge(client: anthropic.Anthropic, case: dict,
               response_a: str, response_b: str) -> dict:
    """Claude에게 A/B 응답 채점 요청, 파싱된 점수 반환"""
    expected_points = "\n".join(
        f"  - {p}" for p in case.get("expected_explanation_points", [])
    )
    prompt = JUDGE_PROMPT.format(
        source=case["source"],
        subtitle=case["subtitle"],
        keywords=", ".join(case.get("keywords", [])),
        expected_points=expected_points,
        response_a=response_a or "(응답 없음)",
        response_b=response_b or "(응답 없음)",
    )

    message = client.messages.create(
        model=JUDGE_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()

    # JSON 블록 추출 (```json ... ``` 형식도 처리)
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)


def judge_case(client: anthropic.Anthropic, case: dict,
               gemini_response: str, kanana_response: str) -> dict:
    """Swap average 방식으로 채점: 2라운드 평균"""

    print(f"    라운드1 (A=gemini, B=kanana) ...", end=" ", flush=True)
    round1 = call_judge(client, case, gemini_response, kanana_response)
    print("완료")
    time.sleep(1)  # rate limit 방지

    print(f"    라운드2 (A=kanana, B=gemini) ...", end=" ", flush=True)
    round2 = call_judge(client, case, kanana_response, gemini_response)
    print("완료")

    # round1: A=gemini, B=kanana
    # round2: A=kanana, B=gemini → 역전해서 gemini/kanana 기준으로 맞춤
    gemini_scores = {
        "accuracy":    (round1["A"]["accuracy"]    + round2["B"]["accuracy"])    / 2,
        "context":     (round1["A"]["context"]      + round2["B"]["context"])      / 2,
        "naturalness": (round1["A"]["naturalness"]  + round2["B"]["naturalness"])  / 2,
        "cultural":    (round1["A"]["cultural"]      + round2["B"]["cultural"])      / 2,
        "reason_r1":   round1["A"]["reason"],
        "reason_r2":   round2["B"]["reason"],
    }
    kanana_scores = {
        "accuracy":    (round1["B"]["accuracy"]    + round2["A"]["accuracy"])    / 2,
        "context":     (round1["B"]["context"]      + round2["A"]["context"])      / 2,
        "naturalness": (round1["B"]["naturalness"]  + round2["A"]["naturalness"])  / 2,
        "cultural":    (round1["B"]["cultural"]      + round2["A"]["cultural"])      / 2,
        "reason_r1":   round1["B"]["reason"],
        "reason_r2":   round2["A"]["reason"],
    }

    # 일관성 체크: 두 라운드에서 승자가 같은가
    r1_winner = "gemini" if round1["A"]["accuracy"] + round1["A"]["context"] + round1["A"]["naturalness"] + round1["A"]["cultural"] \
                          > round1["B"]["accuracy"] + round1["B"]["context"] + round1["B"]["naturalness"] + round1["B"]["cultural"] \
                else "kanana"
    r2_winner = "kanana" if round2["A"]["accuracy"] + round2["A"]["context"] + round2["A"]["naturalness"] + round2["A"]["cultural"] \
                          > round2["B"]["accuracy"] + round2["B"]["context"] + round2["B"]["naturalness"] + round2["B"]["cultural"] \
                else "gemini"
    consistent = r1_winner == r2_winner

    return {
        "gemini": gemini_scores,
        "kanana": kanana_scores,
        "consistent": consistent,
        "r1_winner": r1_winner,
        "r2_winner": r2_winner,
    }


def run_judge(input_path: Path, output_path: Path):
    client = anthropic.Anthropic()  # ANTHROPIC_API_KEY 자동 사용

    # 응답 로드 및 case_id 기준 그룹핑
    with open(input_path, "r", encoding="utf-8") as f:
        responses = json.load(f)

    by_case: dict[str, dict] = {}
    for r in responses:
        cid = r["case_id"]
        if cid not in by_case:
            by_case[cid] = {}
        by_case[cid][r["model"]] = r

    dataset = load_dataset()
    rows = []
    inconsistent_cases = []

    print(f"\n{'='*60}")
    print(f"Claude Judge 채점 시작 ({JUDGE_MODEL})")
    print(f"케이스: {len(by_case)}개 | 입력: {input_path.name}")
    print(f"{'='*60}")

    for case_id, model_responses in by_case.items():
        if "gemini" not in model_responses or "kanana" not in model_responses:
            print(f"  [{case_id}] 스킵 - gemini/kanana 응답 중 하나 누락")
            continue

        case = dataset.get(case_id)
        if not case:
            print(f"  [{case_id}] 스킵 - test_cases.json에 케이스 없음")
            continue

        print(f"\n[{case_id}] {case['source']} - {case['category_ko']}")

        gemini_resp = model_responses["gemini"].get("response", "")
        kanana_resp = model_responses["kanana"].get("response", "")

        try:
            result = judge_case(client, case, gemini_resp, kanana_resp)
        except Exception as e:
            print(f"  ERROR: {e}")
            continue

        if not result["consistent"]:
            inconsistent_cases.append(case_id)

        for model_name in ["gemini", "kanana"]:
            s = result[model_name]
            total = s["accuracy"] + s["context"] + s["naturalness"] + s["cultural"]
            rows.append({
                "case_id": case_id,
                "category": case["category"],
                "category_ko": case["category_ko"],
                "source": case["source"],
                "model": model_name,
                "latency_ms": model_responses[model_name].get("latency_ms"),
                "score_accuracy": s["accuracy"],
                "score_context": s["context"],
                "score_naturalness": s["naturalness"],
                "score_cultural": s["cultural"],
                "score_total": round(total, 2),
                "consistent": result["consistent"],
                "reason_r1": s["reason_r1"],
                "reason_r2": s["reason_r2"],
            })

        g_total = round(result["gemini"]["accuracy"] + result["gemini"]["context"] +
                        result["gemini"]["naturalness"] + result["gemini"]["cultural"], 2)
        k_total = round(result["kanana"]["accuracy"] + result["kanana"]["context"] +
                        result["kanana"]["naturalness"] + result["kanana"]["cultural"], 2)
        consistent_mark = "✓" if result["consistent"] else "⚠ 불일치"
        print(f"    gemini {g_total}/10  kanana {k_total}/10  [{consistent_mark}]")

        time.sleep(1)  # rate limit 방지

    # 저장
    fieldnames = [
        "case_id", "category", "category_ko", "source", "model", "latency_ms",
        "score_accuracy", "score_context", "score_naturalness", "score_cultural", "score_total",
        "consistent", "reason_r1", "reason_r2",
    ]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n{'='*60}")
    print(f"채점 완료: {output_path}")
    print_summary(rows, inconsistent_cases)


def print_summary(rows: list, inconsistent_cases: list):
    from collections import defaultdict

    by_model = defaultdict(list)
    for r in rows:
        by_model[r["model"]].append(r["score_total"])

    print(f"\n모델별 평균 점수")
    print(f"{'모델':<12} {'평균':<8} {'케이스'}")
    print("-" * 30)
    for model, totals in by_model.items():
        avg = sum(totals) / len(totals) if totals else 0
        print(f"{model:<12} {avg:<8.2f} {len(totals)}")

    print(f"\n카테고리별 비교")
    by_cat = defaultdict(lambda: defaultdict(list))
    for r in rows:
        by_cat[r["category"]][r["model"]].append(r["score_total"])

    cat_names = {"slang": "속어·신조어", "classical": "사극·고어체", "dialect": "방언·사투리"}
    for cat, models in by_cat.items():
        print(f"\n  [{cat_names.get(cat, cat)}]")
        for model, totals in models.items():
            avg = sum(totals) / len(totals) if totals else 0
            print(f"    {model:<12} {avg:.2f}/10")

    if inconsistent_cases:
        print(f"\n⚠  수동 검토 필요 (두 라운드 승자 불일치): {', '.join(inconsistent_cases)}")
    else:
        print(f"\n✓  모든 케이스 일관성 통과")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DocentAI Claude Judge")
    parser.add_argument("--input", required=True, help="responses_{timestamp}.json 파일 경로")
    parser.add_argument("--output", default=None, help="결과 CSV 저장 경로 (기본: results/judge_scores.csv)")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else input_path.parent / "judge_scores.csv"

    run_judge(input_path, output_path)
