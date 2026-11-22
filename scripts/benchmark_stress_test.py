#!/usr/bin/env python3
"""
Stand-Alone High-Volume Load & Stress Benchmark Tool for PW GATE Predictor.
Simulates burst exam-day submissions and measures throughput and p50/p95/p99 latencies.

Usage:
    python scripts/benchmark_stress_test.py --total 200 --workers 10
"""

import argparse
import concurrent.futures
import json
import statistics
import time
import requests

DEFAULT_URL = "http://127.0.0.1:8000"


def run_benchmark(base_url: str, total_requests: int, max_workers: int):
    print(f"============================================================")
    print(f"  Physics Wallah GATE Predictor Concurrency Benchmark")
    print(f"============================================================")
    print(f"Target URL:         {base_url}")
    print(f"Total Requests:     {total_requests}")
    print(f"Concurrent Workers: {max_workers}")
    print(f"Starting benchmark...")

    latencies = []
    status_codes = {}

    def submit_one(idx: int):
        phone = f"887766{idx:04d}"
        payload = {
            "student_phone": phone,
            "student_name": f"Perf Student {idx}",
            "student_email": f"student{idx}@pwbenchmark.com",
            "student_category": "GEN" if idx % 2 == 0 else "OBC_NCL",
            "paper_code": "CS",
            "session_id": 1,
            "responses": [
                {
                    "question_id": f"STRESS-CS-Q{i:02d}",
                    "status": "ATTEMPTED",
                    "marked_options": ["B"],
                }
                for i in range(1, 11)
            ],
        }

        t0 = time.perf_counter()
        try:
            resp = requests.post(f"{base_url}/api/v1/submissions", json=payload, timeout=10.0)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return resp.status_code, elapsed_ms, None
        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return 500, elapsed_ms, str(e)

    bench_start = time.perf_counter()

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(submit_one, i) for i in range(total_requests)]
        for f in concurrent.futures.as_completed(futures):
            code, ms, err = f.result()
            latencies.append(ms)
            status_codes[code] = status_codes.get(code, 0) + 1

    total_time = time.perf_counter() - bench_start
    throughput = total_requests / total_time if total_time > 0 else 0.0

    latencies.sort()
    p50 = statistics.median(latencies)
    p90 = latencies[int(len(latencies) * 0.90)]
    p95 = latencies[int(len(latencies) * 0.95)]
    p99 = latencies[int(len(latencies) * 0.99)]
    avg = statistics.mean(latencies)
    min_lat = min(latencies)
    max_lat = max(latencies)

    print(f"\n---------------- Benchmark Results ----------------")
    print(f"Total Completed:    {total_requests} in {total_time:.2f}s")
    print(f"Throughput:         {throughput:.2f} requests/second")
    print(f"Status Breakdown:   {status_codes}")
    print(f"Min Latency:        {min_lat:.1f} ms")
    print(f"Mean Latency:       {avg:.1f} ms")
    print(f"Median (P50):       {p50:.1f} ms")
    print(f"P90 Latency:        {p90:.1f} ms")
    print(f"P95 Latency:        {p95:.1f} ms")
    print(f"P99 Latency:        {max_lat:.1f} ms")
    print(f"---------------------------------------------------\n")

    return {
        "total": total_requests,
        "elapsed_seconds": total_time,
        "throughput_rps": throughput,
        "p50_ms": p50,
        "p95_ms": p95,
        "p99_ms": p99,
        "status_codes": status_codes,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GATE Predictor Concurrency Benchmark")
    parser.add_argument("--url", default=DEFAULT_URL, help="Base API URL")
    parser.add_argument("--total", type=int, default=100, help="Total student submissions")
    parser.add_argument("--workers", type=int, default=10, help="Concurrent worker threads")
    args = parser.parse_args()

    run_benchmark(args.url, args.total, args.workers)
