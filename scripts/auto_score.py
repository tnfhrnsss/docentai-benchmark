"""
DocentAI Benchmark - Auto Scorer
responses_{timestamp}.json 을 읽어 키워드 기반 1차 채점 수행

Usage:
    python scripts/auto_score.py --input results/responses_20260320_120000.json
    python scripts/auto_score.py --input results/responses_20260320_120000.json --output results/scores.csv
"""

import json
import csv
import argparse
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DATASET_PATH = BASE_DIR / "dataset" / "test_cases.json"


def load_dataset() -> dict:
    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {c["id"]: c for c in data["test_cases"]}


def score_accuracy(response: str, case: dict) -> int:
    """정확성: 핵심 키워드 포함 여부 기반 (0~3)"""
    if not response:
        return 0
    keywords = case.get("keywords", [])
    if not keywords:
        return 1  # 키워드 없으면 기본 1점
    matched = sum(1 for kw in keywords if kw in response)
    ratio = matched / len(keywords)
    if ratio >= 0.8:
        return 3
    elif ratio >= 0.5:
        return 2
    elif ratio >= 0.2:
        return 1
    return 0


def score_context(response: str, case: dict) -> int:
    """맥락 연결성: 출처 콘텐츠 또는 장르 관련 단어 포함 여부 (0~3) - 수동 보정 필요"""
    if not response:
        return 0
    source_words = case["source"].replace(" ", "").replace("·", "")
    genre_keywords = {
        "slang": ["예능", "연애", "서바이벌", "아이돌", "팬"],
        "classical": ["조선", "궁중", "사극", "왕", "신하", "드라마"],
        "dialect": ["방언", "사투리", "경상", "전라", "충청", "지역"],
    }
    cat_words = genre_keywords.get(case["category"], [])

    # 소스 이름 언급 시 +1, 장르 맥락 언급 시 +1
    score = 0
    if any(ch in response for ch in source_words[:4]):
        score += 1
    if any(w in response for w in cat_words):
        score += 1
    if len(response) > 150:  # 충분한 길이 = 맥락 설명 가능성 높음
        score += 1
    return min(score, 3)


def score_naturalness(response: str) -> int:
    """자연스러움: 길이 및 이상 패턴 탐지 기반 (0~2) - 수동 보정 필요"""
    if not response:
        return 0
    # 너무 짧으면 설명 부족
    if len(response) < 50:
        return 0
    # 영어 비율이 높으면 어색함
    english_chars = sum(1 for c in response if c.isascii() and c.isalpha())
    total_chars = max(len(response), 1)
    if english_chars / total_chars > 0.4:
        return 1
    return 2


def score_cultural_nuance(response: str, case: dict) -> int:
    """문화적 뉘앙스: 카테고리별 뉘앙스 키워드 (0~2) - 수동 보정 필요"""
    if not response:
        return 0

    nuance_keywords = {
        "slang": ["MZ", "세대", "유행", "밈", "인터넷", "온라인", "청년", "2030"],
        "classical": ["조선시대", "궁중", "왕조", "양반", "신분", "격식", "경어"],
        "dialect": ["지역", "억양", "방언", "정서", "감성", "충청", "경상", "전라"],
    }

    words = nuance_keywords.get(case["category"], [])
    matched = sum(1 for w in words if w in response)
    if matched >= 2:
        return 2
    elif matched == 1:
        return 1
    return 0


def auto_score(responses: list, dataset: dict) -> list:
    """전체 응답에 대해 자동 채점"""
    scores = []

    for item in responses:
        case_id = item["case_id"]
        model = item["model"]
        response = item.get("response", "")

        if case_id not in dataset:
            print(f"  경고: {case_id} 케이스를 데이터셋에서 찾을 수 없습니다.")
            continue

        case = dataset[case_id]

        s_accuracy = score_accuracy(response, case)
        s_context = score_context(response, case)
        s_naturalness = score_naturalness(response)
        s_cultural = score_cultural_nuance(response, case)
        total = s_accuracy + s_context + s_naturalness + s_cultural

        scores.append({
            "case_id": case_id,
            "category": case["category"],
            "category_ko": case["category_ko"],
            "source": case["source"],
            "model": model,
            "latency_ms": item.get("latency_ms"),
            "response_length": len(response) if response else 0,
            "score_accuracy": s_accuracy,
            "score_context": s_context,
            "score_naturalness": s_naturalness,
            "score_cultural": s_cultural,
            "score_total": total,
            "auto_scored": True,
            "manual_review_done": False,
            "manual_notes": "",
        })

        winner = "Gemini" if model == "gemini" else "Kanana"
        print(f"  [{case_id}] {model:8s} → {total}/10  (정:{s_accuracy} 맥:{s_context} 자:{s_naturalness} 문:{s_cultural})")

    return scores


def save_scores(scores: list, output_path: Path):
    if not scores:
        print("채점 결과가 없습니다.")
        return
    fieldnames = [
        "case_id", "category", "category_ko", "source", "model",
        "latency_ms", "response_length",
        "score_accuracy", "score_context", "score_naturalness", "score_cultural", "score_total",
        "auto_scored", "manual_review_done", "manual_notes",
    ]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(scores)
    print(f"\n채점 결과 저장: {output_path}")


def print_summary(scores: list):
    from collections import defaultdict

    print(f"\n{'='*60}")
    print("자동 채점 요약 (수동 검토 필요)")
    print(f"{'='*60}")

    by_model = defaultdict(list)
    for s in scores:
        by_model[s["model"]].append(s["score_total"])

    for model, totals in by_model.items():
        avg = sum(totals) / len(totals) if totals else 0
        print(f"  {model:10s}: 평균 {avg:.1f}/10 ({len(totals)}개 케이스)")

    print(f"\n카테고리별 비교")
    by_cat = defaultdict(lambda: defaultdict(list))
    for s in scores:
        by_cat[s["category"]][s["model"]].append(s["score_total"])

    cat_names = {"slang": "속어·신조어", "classical": "사극·고어체", "dialect": "방언·사투리"}
    for cat, models in by_cat.items():
        print(f"\n  [{cat_names.get(cat, cat)}]")
        for model, totals in models.items():
            avg = sum(totals) / len(totals) if totals else 0
            print(f"    {model:10s}: {avg:.1f}/10")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DocentAI Benchmark Auto Scorer")
    parser.add_argument("--input", required=True, help="responses_{timestamp}.json 파일 경로")
    parser.add_argument("--output", default=None, help="결과 CSV 저장 경로 (기본: results/scores.csv)")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else input_path.parent / "scores.csv"

    print(f"\nDocentAI 자동 채점")
    print(f"입력: {input_path}")

    with open(input_path, "r", encoding="utf-8") as f:
        responses = json.load(f)

    dataset = load_dataset()
    print(f"케이스: {len(dataset)}개 | 응답: {len(responses)}개\n")

    scores = auto_score(responses, dataset)
    save_scores(scores, output_path)
    print_summary(scores)
