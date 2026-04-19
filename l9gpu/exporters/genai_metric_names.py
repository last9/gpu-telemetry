# Copyright (c) Last9, Inc.
"""OpenTelemetry GenAI semantic convention mappings for l9gpu inference metrics.

Maps l9gpu field names to the gen_ai.* OTel namespace defined in:
https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-metrics/

Usage: enable with --emit-genai-namespace on inference monitor CLIs.
Emits gen_ai.* names IN ADDITION TO the existing vllm.*/sglang.*/tgi.* names
so that existing dashboards continue to work.

Notes (March 2026):
- gen_ai.system is deprecated in OTel GenAI 1.36+; use gen_ai.provider.name.
  We emit both for backward compatibility.
- OTel has NO official gpu.* semantic conventions; our gpu.* namespace is
  ahead of the spec and represents l9gpu's proposed contribution.
"""

from typing import Dict

# Maps l9gpu field names → gen_ai.* OTel metric names.
# Only inference-layer fields are mapped here; hardware fields (gpu.*) are
# already defined in metric_names.py.
FIELD_TO_GENAI_NAME: Dict[str, str] = {
    # --- Throughput (token usage) ---
    "prompt_tokens_per_sec": "gen_ai.client.token.usage",
    "generation_tokens_per_sec": "gen_ai.client.token.usage",
    "sglang_prompt_tokens_per_sec": "gen_ai.client.token.usage",
    "sglang_generation_tokens_per_sec": "gen_ai.client.token.usage",
    # --- Request duration (end-to-end latency) ---
    "e2e_latency_p50": "gen_ai.server.request.duration",
    "e2e_latency_p95": "gen_ai.server.request.duration",
    "e2e_latency_p99": "gen_ai.server.request.duration",
    "sglang_e2e_latency_p50": "gen_ai.server.request.duration",
    "sglang_e2e_latency_p95": "gen_ai.server.request.duration",
    "sglang_e2e_latency_p99": "gen_ai.server.request.duration",
    "tgi_request_latency_p50": "gen_ai.server.request.duration",
    "tgi_request_latency_p95": "gen_ai.server.request.duration",
    "tgi_request_latency_p99": "gen_ai.server.request.duration",
    # --- Time to first token ---
    "ttft_p50": "gen_ai.server.time_to_first_token",
    "ttft_p95": "gen_ai.server.time_to_first_token",
    "sglang_ttft_p50": "gen_ai.server.time_to_first_token",
    "sglang_ttft_p95": "gen_ai.server.time_to_first_token",
    # --- Time per output token (inter-token latency) ---
    "itl_p50": "gen_ai.server.time_per_output_token",
    "itl_p95": "gen_ai.server.time_per_output_token",
    "itl_p99": "gen_ai.server.time_per_output_token",
    "sglang_itl_p50": "gen_ai.server.time_per_output_token",
    "sglang_itl_p95": "gen_ai.server.time_per_output_token",
    "tgi_tpot_p50": "gen_ai.server.time_per_output_token",
    "tgi_tpot_p95": "gen_ai.server.time_per_output_token",
    # --- Cache ---
    "gpu_cache_usage": "gen_ai.server.cache.utilization",
    "cpu_cache_usage": "gen_ai.server.cache.utilization",
    "cache_hit_rate": "gen_ai.server.cache.hit_rate",
    "sglang_cache_hit_rate": "gen_ai.server.cache.hit_rate",
}

# Data-point attributes that accompany the gen_ai.* names.
GENAI_DATA_POINT_ATTRIBUTES: Dict[str, Dict[str, str]] = {
    # Token type disambiguation
    "prompt_tokens_per_sec": {"gen_ai.token.type": "input"},
    "generation_tokens_per_sec": {"gen_ai.token.type": "output"},
    "sglang_prompt_tokens_per_sec": {"gen_ai.token.type": "input"},
    "sglang_generation_tokens_per_sec": {"gen_ai.token.type": "output"},
    # Quantile disambiguation (mirrors metric_names.py pattern)
    "e2e_latency_p50": {"quantile": "p50"},
    "e2e_latency_p95": {"quantile": "p95"},
    "e2e_latency_p99": {"quantile": "p99"},
    "sglang_e2e_latency_p50": {"quantile": "p50"},
    "sglang_e2e_latency_p95": {"quantile": "p95"},
    "sglang_e2e_latency_p99": {"quantile": "p99"},
    "tgi_request_latency_p50": {"quantile": "p50"},
    "tgi_request_latency_p95": {"quantile": "p95"},
    "tgi_request_latency_p99": {"quantile": "p99"},
    "ttft_p50": {"quantile": "p50"},
    "ttft_p95": {"quantile": "p95"},
    "sglang_ttft_p50": {"quantile": "p50"},
    "sglang_ttft_p95": {"quantile": "p95"},
    "itl_p50": {"quantile": "p50"},
    "itl_p95": {"quantile": "p95"},
    "itl_p99": {"quantile": "p99"},
    "sglang_itl_p50": {"quantile": "p50"},
    "sglang_itl_p95": {"quantile": "p95"},
    "tgi_tpot_p50": {"quantile": "p50"},
    "tgi_tpot_p95": {"quantile": "p95"},
    # Cache type
    "gpu_cache_usage": {"gen_ai.cache.type": "gpu"},
    "cpu_cache_usage": {"gen_ai.cache.type": "cpu"},
}

# Resource attributes added to the OTel Resource when emit_genai_namespace=True.
# gen_ai.system is deprecated in OTel GenAI 1.36+; use gen_ai.provider.name.
# We emit both for maximum backend compatibility.
PROVIDER_RESOURCE_ATTRS: Dict[str, Dict[str, str]] = {
    "vllm": {
        "gen_ai.provider.name": "vllm",
        "gen_ai.system": "vllm",  # deprecated alias
    },
    "nim": {
        "gen_ai.provider.name": "nvidia_nim",
        "gen_ai.system": "nvidia_nim",
    },
    "triton": {
        "gen_ai.provider.name": "triton",
        "gen_ai.system": "triton",
    },
    "sglang": {
        "gen_ai.provider.name": "sglang",
        "gen_ai.system": "sglang",
    },
    "tgi": {
        "gen_ai.provider.name": "huggingface_tgi",
        "gen_ai.system": "huggingface_tgi",
    },
}
