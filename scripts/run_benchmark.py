"""
DocentAI Benchmark Runner
Gemini vs Kanana - Korean subtitle explanation quality benchmark

두 DocentAI 서버(로컬=Kanana, GCP=Gemini)를 직접 호출해 동일 자막에 대한 응답을 비교합니다.

Usage:
    python scripts/run_benchmark.py --model all
    python scripts/run_benchmark.py --model gemini
    python scripts/run_benchmark.py --model kanana
    python scripts/run_benchmark.py --model all --category slang
    python scripts/run_benchmark.py --model all --case-id A-01

환경변수:
    DOCENTAI_LOCAL_URL   로컬 DocentAI 서버 URL (Kanana, 기본: http://localhost:7777)
    DOCENTAI_GCP_URL     GCP DocentAI 서버 URL (Gemini)
    DOCENTAI_PROFILE_ID  인증용 프로필 ID (기본: benchmark)
"""

import json
import time
import csv
import argparse
import os
from datetime import datetime
from pathlib import Path

import requests

# ── 설정 ──────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent.parent
DATASET_PATH = BASE_DIR / "dataset" / "test_cases.json"
RESULTS_DIR = BASE_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# 모델명 → 서버 URL 매핑
def get_server_urls() -> dict:
    local_url = os.environ.get("DOCENTAI_LOCAL_URL", "http://localhost:7777")
    gcp_url = os.environ.get("DOCENTAI_GCP_URL", "")
    return {
        "kanana": local_url,
        "gemini": gcp_url,
    }


# ── 인증 ──────────────────────────────────────────────────────────────────────

_token_cache: dict[str, str] = {}  # base_url → token


def get_auth_token(base_url: str) -> str:
    """JWT 토큰 발급 (캐시 우선)"""
    if base_url in _token_cache:
        return _token_cache[base_url]

    profile_id = os.environ.get("DOCENTAI_PROFILE_ID", "benchmark")
    resp = requests.post(
        f"{base_url}/api/auth/token",
        headers={"X-Profile-ID": profile_id},
        timeout=10,
    )
    resp.raise_for_status()
    token = resp.json()["token"]
    _token_cache[base_url] = token
    return token


# ── DocentAI API 호출 ─────────────────────────────────────────────────────────

def build_context(case: dict) -> list:
    """test_cases.json의 context_before/after를 DocentAI SubtitleContext 형식으로 변환"""
    context = []
    before = case.get("context_before", [])
    after = case.get("context_after", [])
    for i, text in enumerate(before):
        context.append({"text": text, "timestamp": -(len(before) - i) * 3})
    for i, text in enumerate(after):
        context.append({"text": text, "timestamp": (i + 1) * 3})
    return context


def call_docentai(base_url: str, model_name: str, case: dict) -> dict:
    """DocentAI /api/explanations/videos/{video_id} 호출"""
    token = get_auth_token(base_url)

    payload = {
        "selectedText": case["subtitle"],
        "timestamp": 0,
        "title": case["source"],
        "language": "ko",
        "platform": case.get("platform"),
        "context": build_context(case),
        "currentSubtitle": {
            "text": case["subtitle"],
            "timestamp": 0,
        },
    }

    def _post():
        return requests.post(
            f"{base_url}/api/explanations/videos/benchmark-{case['id']}",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60,
        )

    start = time.time()
    resp = _post()
    latency_ms = int((time.time() - start) * 1000)

    # 401 → 토큰 만료, 재발급 후 1회 재시도
    if resp.status_code == 401:
        _token_cache.pop(base_url, None)
        token = get_auth_token(base_url)
        payload["Authorization"] = f"Bearer {token}"
        start = time.time()
        resp = _post()
        latency_ms = int((time.time() - start) * 1000)

    resp.raise_for_status()
    data = resp.json()

    explanation_text = data["data"]["explanation"]["text"]
    api_response_time = data["data"].get("responseTime")

    return {
        "text": explanation_text,
        "latency_ms": latency_ms,
        "api_response_time_ms": api_response_time,
        "model": model_name,
        "input_tokens": None,
        "output_tokens": None,
    }


# ── 실험 실행 ─────────────────────────────────────────────────────────────────

def run_single(case: dict, model: str, base_url: str, repeat: int = 3) -> list[dict]:
    """단일 케이스를 지정 횟수 반복 실행"""
    results = []

    for i in range(repeat):
        print(f"  [{model}] {case['id']} - 시도 {i+1}/{repeat}", end=" ")
        try:
            result = call_docentai(base_url, model, case)
            result.update({
                "case_id": case["id"],
                "category": case["category"],
                "source": case["source"],
                "subtitle": case["subtitle"],
                "attempt": i + 1,
                "error": None,
                "response_length": len(result["text"]),
            })
            print(f"✓  ({result['latency_ms']}ms)")
        except Exception as e:
            result = {
                "case_id": case["id"],
                "category": case["category"],
                "source": case["source"],
                "subtitle": case["subtitle"],
                "model": model,
                "attempt": i + 1,
                "text": None,
                "latency_ms": None,
                "api_response_time_ms": None,
                "input_tokens": None,
                "output_tokens": None,
                "response_length": None,
                "error": str(e),
            }
            print(f"✗ ERROR: {e}")

        results.append(result)

        if i < repeat - 1:
            time.sleep(1)

    return results


def run_benchmark(model: str = "all", category: str = None, case_id: str = None, repeat: int = 3):
    """전체 벤치마크 실행"""
    server_urls = get_server_urls()

    # 실행할 모델 목록 결정
    if model == "all":
        models = ["kanana", "gemini"]
    else:
        models = [model]

    # 서버 URL 유효성 확인
    for m in models:
        url = server_urls.get(m, "")
        if not url:
            raise ValueError(f"{m.upper()} 서버 URL이 설정되지 않았습니다. "
                             f"환경변수 DOCENTAI_{'LOCAL' if m == 'kanana' else 'GCP'}_URL을 설정하세요.")

    # 데이터셋 로드
    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    cases = dataset["test_cases"]

    if category:
        cases = [c for c in cases if c["category"] == category]
    if case_id:
        cases = [c for c in cases if c["id"] == case_id]

    print(f"\n{'='*60}")
    print(f"DocentAI Benchmark")
    print(f"모델: {models} | 케이스: {len(cases)}개 | 반복: {repeat}회")
    for m in models:
        print(f"  {m}: {server_urls[m]}")
    print(f"{'='*60}\n")

    all_results = []
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    for case in cases:
        print(f"\n[{case['id']}] {case['source']} - {case['category_ko']}")
        print(f"  자막: {case['subtitle'][:50]}...")

        for m in models:
            results = run_single(case, m, server_urls[m], repeat)
            all_results.extend(results)

    # 결과 저장
    output_path = RESULTS_DIR / f"raw_results_{timestamp}.csv"
    save_csv(all_results, output_path)

    text_path = RESULTS_DIR / f"responses_{timestamp}.json"
    save_responses(all_results, text_path)

    print(f"\n{'='*60}")
    print(f"완료! 결과 저장:")
    print(f"  - {output_path}")
    print(f"  - {text_path}")
    print_summary(all_results)


def save_csv(results: list, path: Path):
    """측정 데이터를 CSV로 저장"""
    if not results:
        return
    fieldnames = [
        "case_id", "category", "source", "model", "attempt",
        "latency_ms", "api_response_time_ms", "response_length", "error"
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)


def save_responses(results: list, path: Path):
    """응답 텍스트를 JSON으로 저장 (Claude Judge용)"""
    responses = [
        {
            "case_id": r["case_id"],
            "model": r["model"],
            "subtitle": r["subtitle"],
            "response": r.get("text"),
            "source": r.get("source"),
            "latency_ms": r.get("latency_ms"),
        }
        for r in results if r.get("attempt") == 1  # 첫 번째 시도만 저장 (claude_judge.py 입력용)
    ]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(responses, f, ensure_ascii=False, indent=2)


def print_summary(results: list):
    """실행 결과 요약 출력"""
    from collections import defaultdict

    stats = defaultdict(lambda: {"count": 0, "latencies": []})

    for r in results:
        key = r["model"]
        if r.get("attempt") == 1:
            stats[key]["count"] += 1
        if not r.get("error") and r.get("latency_ms"):
            stats[key]["latencies"].append(r["latency_ms"])

    print(f"\n{'='*60}")
    print("요약")
    print(f"{'모델':<15} {'케이스':<10} {'평균응답(ms)'}")
    print("-" * 40)
    for m, s in stats.items():
        avg = int(sum(s["latencies"]) / len(s["latencies"])) if s["latencies"] else "-"
        print(f"{m:<15} {s['count']:<10} {avg}")


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DocentAI LLM Benchmark Runner")
    parser.add_argument("--model", choices=["gemini", "kanana", "all"], default="all")
    parser.add_argument("--category", choices=["slang", "classical", "dialect"], default=None)
    parser.add_argument("--case-id", default=None, help="특정 케이스만 실행 (예: A-01)")
    parser.add_argument("--repeat", type=int, default=3, help="반복 횟수 (기본: 3)")
    args = parser.parse_args()

    run_benchmark(
        model=args.model,
        category=args.category,
        case_id=args.case_id,
        repeat=args.repeat,
    )
