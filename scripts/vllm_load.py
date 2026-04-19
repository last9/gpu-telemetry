#!/usr/bin/env python3
"""
vLLM load generator — drives concurrent completions to populate GPU telemetry.

Usage:
    python3 scripts/vllm_load.py                        # defaults
    python3 scripts/vllm_load.py --concurrency 4 --duration 120
    python3 scripts/vllm_load.py --endpoint http://localhost:8000 --max-tokens 200

Requires: pip install aiohttp
"""
import argparse
import asyncio
import json
import time
import sys
from itertools import cycle

try:
    import aiohttp
except ImportError:
    sys.exit("Missing dependency: pip install aiohttp")

PROMPTS = [
    "Explain how a GPU executes CUDA kernels in parallel.",
    "What is the difference between HBM and GDDR memory in GPUs?",
    "Describe the attention mechanism in transformer models.",
    "How does gradient checkpointing reduce GPU memory usage during training?",
    "What is tensor parallelism and when should you use it?",
    "Explain the roofline model for GPU performance analysis.",
    "What causes GPU memory fragmentation and how can it be avoided?",
    "How does flash attention improve upon standard scaled dot-product attention?",
    "Describe the role of the GPU L2 cache in deep learning workloads.",
    "What is the difference between model parallelism and data parallelism?",
    "Explain how KV caching works in autoregressive LLM inference.",
    "What metrics indicate a GPU is compute-bound vs memory-bandwidth-bound?",
    "How does continuous batching improve LLM serving throughput?",
    "What is PCIe bandwidth and why does it matter for multi-GPU training?",
    "Explain the difference between FP16, BF16, and INT8 quantization for inference.",
]


async def single_request(session, endpoint, model, prompt, max_tokens, temperature, stats):
    url = f"{endpoint}/v1/completions"
    payload = {
        "model": model,
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }
    t0 = time.perf_counter()
    try:
        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as resp:
            data = await resp.json()
            latency_ms = (time.perf_counter() - t0) * 1000
            completion_tokens = data.get("usage", {}).get("completion_tokens", 0)
            prompt_tokens = data.get("usage", {}).get("prompt_tokens", 0)
            stats["ok"] += 1
            stats["completion_tokens"] += completion_tokens
            stats["prompt_tokens"] += prompt_tokens
            stats["latency_sum_ms"] += latency_ms
            stats["latency_count"] += 1
    except Exception as e:
        stats["errors"] += 1
        stats["last_error"] = str(e)


async def worker(endpoint, model, max_tokens, temperature, prompt_iter, stats, stop_event):
    connector = aiohttp.TCPConnector(limit=1)
    async with aiohttp.ClientSession(connector=connector) as session:
        while not stop_event.is_set():
            prompt = next(prompt_iter)
            await single_request(session, endpoint, model, prompt, max_tokens, temperature, stats)


async def run(args):
    # Probe for model name
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{args.endpoint}/v1/models", timeout=aiohttp.ClientTimeout(total=5)) as r:
                data = await r.json()
                model = data["data"][0]["id"]
        except Exception as e:
            sys.exit(f"Cannot reach {args.endpoint}/v1/models: {e}")

    print(f"Model : {model}")
    print(f"Endpoint   : {args.endpoint}")
    print(f"Concurrency: {args.concurrency}")
    print(f"Duration   : {args.duration}s")
    print(f"Max tokens : {args.max_tokens}")
    print()

    stats = {"ok": 0, "errors": 0, "completion_tokens": 0, "prompt_tokens": 0,
             "latency_sum_ms": 0.0, "latency_count": 0, "last_error": ""}
    stop_event = asyncio.Event()
    prompt_iter = cycle(PROMPTS)

    workers = [
        asyncio.create_task(worker(args.endpoint, model, args.max_tokens, args.temperature, prompt_iter, stats, stop_event))
        for _ in range(args.concurrency)
    ]

    t_start = time.perf_counter()
    try:
        while True:
            elapsed = time.perf_counter() - t_start
            if elapsed >= args.duration:
                break
            remaining = args.duration - elapsed
            avg_lat = (stats["latency_sum_ms"] / stats["latency_count"]) if stats["latency_count"] else 0
            gen_tps = stats["completion_tokens"] / elapsed if elapsed > 0 else 0
            print(
                f"\r[{elapsed:5.0f}s/{args.duration}s] "
                f"reqs={stats['ok']:4d}  errors={stats['errors']}  "
                f"gen={gen_tps:5.1f} tok/s  avg_lat={avg_lat:6.0f}ms  "
                f"remaining={remaining:.0f}s   ",
                end="", flush=True
            )
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    finally:
        stop_event.set()
        await asyncio.gather(*workers, return_exceptions=True)

    elapsed = time.perf_counter() - t_start
    avg_lat = (stats["latency_sum_ms"] / stats["latency_count"]) if stats["latency_count"] else 0
    gen_tps = stats["completion_tokens"] / elapsed if elapsed > 0 else 0
    total_tokens = stats["completion_tokens"] + stats["prompt_tokens"]

    print(f"\n\n{'─'*55}")
    print(f"  Duration        : {elapsed:.1f}s")
    print(f"  Requests OK     : {stats['ok']}")
    print(f"  Errors          : {stats['errors']}")
    print(f"  Prompt tokens   : {stats['prompt_tokens']}")
    print(f"  Completion tok  : {stats['completion_tokens']}")
    print(f"  Throughput      : {gen_tps:.1f} gen tok/s")
    print(f"  Avg latency     : {avg_lat:.0f}ms")
    print(f"  Req/s           : {stats['ok']/elapsed:.2f}")
    if stats["last_error"]:
        print(f"  Last error      : {stats['last_error']}")
    print(f"{'─'*55}")


def main():
    parser = argparse.ArgumentParser(description="vLLM load generator")
    parser.add_argument("--endpoint", default="http://localhost:8000")
    parser.add_argument("--concurrency", type=int, default=2,
                        help="number of parallel workers (default: 2)")
    parser.add_argument("--duration", type=int, default=60,
                        help="run duration in seconds (default: 60)")
    parser.add_argument("--max-tokens", type=int, default=150,
                        help="max completion tokens per request (default: 150)")
    parser.add_argument("--temperature", type=float, default=0.8)
    args = parser.parse_args()

    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\nInterrupted.")


if __name__ == "__main__":
    main()
