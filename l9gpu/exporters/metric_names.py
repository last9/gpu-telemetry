# Copyright (c) Last9, Inc.
"""Mapping from l9gpu Python field names to canonical gpu.* OTel metric names.

Source of truth for metric taxonomy: docs/METRICS.md
Units follow OTel UCUM convention: Cel, W, By, 1, {error}
"""

from typing import Dict

# Maps Python dataclass field names → canonical OTel metric names
FIELD_TO_OTEL_NAME: Dict[str, str] = {
    # ---- DeviceMetrics fields ----
    "gpu_util": "gpu.utilization",
    "mem_util": "gpu.memory.utilization",
    "mem_used_percent": "gpu.memory.used.percent",
    "temperature": "gpu.temperature",
    "power_draw": "gpu.power.draw",
    "power_used_percent": "gpu.power.utilization",
    "retired_pages_count_single_bit": "gpu.row_remap.count",
    "retired_pages_count_double_bit": "gpu.row_remap.count",
    # ---- AMD-specific fields (AMDDeviceMetrics) ----
    "xgmi_link_bandwidth": "gpu.interconnect.throughput",
    "ecc_per_block": "gpu.ecc.errors",
    "junction_temperature": "gpu.temperature",
    "hbm_temperature": "gpu.temperature",
    # ---- Gaudi-specific fields (GaudiDeviceMetrics) ----
    "network_rx_bandwidth": "gpu.interconnect.throughput",
    "network_tx_bandwidth": "gpu.interconnect.throughput",
    "rows_replaced": "gpu.row_remap.count",
    "rows_pending": "gpu.row_remap.pending",
    # ---- Gap 1: absolute VRAM (bytes) ----
    "mem_used_bytes": "gpu.memory.used",
    "mem_total_bytes": "gpu.memory.total",
    "mem_free_bytes": "gpu.memory.free",
    # ---- Gap 2: clock frequencies (MHz) ----
    "clock_graphics_mhz": "gpu.clock.frequency",
    "clock_memory_mhz": "gpu.clock.frequency",
    # ---- Gap 3: NVLink bandwidth (bytes/s) ----
    "nvlink_tx_bandwidth": "gpu.interconnect.throughput",
    "nvlink_rx_bandwidth": "gpu.interconnect.throughput",
    # ---- Gap 4: ECC volatile errors ----
    "ecc_errors_volatile_correctable": "gpu.ecc.errors",
    "ecc_errors_volatile_uncorrectable": "gpu.ecc.errors",
    # ---- Gap 5: Clock throttle reasons ----
    "throttle_reason": "gpu.throttle.reason",
    # ---- Gap 6: GPU P-state ----
    "power_state": "gpu.power.state",
    # ---- Gap 7: PCIe throughput ----
    "pcie_rx_bytes": "gpu.pcie.throughput",
    "pcie_tx_bytes": "gpu.pcie.throughput",
    # ---- Gap 8: Fan speed ----
    "fan_speed_percent": "gpu.fan.speed",
    # ---- Gap 9: Encode / decode utilization ----
    "enc_util": "gpu.encode.utilization",
    "dec_util": "gpu.decode.utilization",
    # ---- Gap 10: XID errors ----
    "xid_errors": "gpu.xid.errors",
    # ---- Gap 11: PCIe replay counter ----
    "pcie_replay_count": "gpu.pcie.replay.count",
    # ---- Gap 12: Cumulative energy ----
    "total_energy_mj": "gpu.energy.consumption",
    # ---- Gap 13: Named throttle reason booleans ----
    "throttle_power_software": "gpu.throttle.reason",
    "throttle_temp_hardware": "gpu.throttle.reason",
    "throttle_temp_software": "gpu.throttle.reason",
    "throttle_syncboost": "gpu.throttle.reason",
    # ---- DcgmProfilingMetrics fields ----
    "sm_active": "gpu.sm.active",
    "dram_active": "gpu.dram.active",
    "gr_engine_active": "gpu.gr_engine.active",
    "tensor_active": "gpu.pipe.tensor.active",
    "fp64_active": "gpu.pipe.fp64.active",
    "fp32_active": "gpu.pipe.fp32.active",
    "fp16_active": "gpu.pipe.fp16.active",
    # Phase 6 — advanced DCGM profiling
    "sm_occupancy": "gpu.sm.occupancy",
    "nvlink_tx_bytes": "gpu.interconnect.throughput",
    "nvlink_rx_bytes": "gpu.interconnect.throughput",
    "prof_pcie_tx_bytes": "gpu.pcie.throughput",
    "prof_pcie_rx_bytes": "gpu.pcie.throughput",
    # ---- VllmMetrics fields ----
    "prompt_tokens_per_sec": "vllm.prompt.throughput",
    "generation_tokens_per_sec": "vllm.generation.throughput",
    "e2e_latency_p50": "vllm.request.latency",
    "e2e_latency_p95": "vllm.request.latency",
    "e2e_latency_p99": "vllm.request.latency",
    "ttft_p50": "vllm.ttft",
    "ttft_p95": "vllm.ttft",
    "gpu_cache_usage": "vllm.cache.usage",
    "cpu_cache_usage": "vllm.cache.usage",
    "requests_running": "vllm.requests.running",
    "requests_waiting": "vllm.requests.waiting",
    "requests_swapped": "vllm.requests.swapped",
    # Phase 8 — extended vLLM metrics
    "itl_p50": "vllm.itl",
    "itl_p95": "vllm.itl",
    "itl_p99": "vllm.itl",
    "prefill_duration_p50": "vllm.prefill.duration",
    "prefill_duration_p95": "vllm.prefill.duration",
    "decode_duration_p50": "vllm.decode.duration",
    "decode_duration_p95": "vllm.decode.duration",
    "cache_hit_rate": "vllm.cache.hit_rate",
    "cache_evictions_per_sec": "vllm.cache.evictions",
    "spec_decode_acceptance_rate": "vllm.spec_decode.acceptance_rate",
    "spec_decode_efficiency": "vllm.spec_decode.efficiency",
    "requests_success_per_sec": "vllm.requests.success",
    "requests_finished_stop_per_sec": "vllm.requests.finished",
    "requests_finished_length_per_sec": "vllm.requests.finished",
    "requests_finished_abort_per_sec": "vllm.requests.finished",
    "preemptions_per_sec": "vllm.scheduler.preemptions",
    "lora_active_count": "vllm.lora.active_count",
    # ---- NimMetrics fields ----
    "requests_total": "nim.requests.total",
    "requests_failed": "nim.requests.failed",
    "request_latency_p50": "nim.request.latency",
    "request_latency_p99": "nim.request.latency",
    "batch_size_avg": "nim.batch.size",
    "queue_depth": "nim.queue.depth",
    "kv_cache_usage": "nim.kv_cache.usage",
    "nim_itl_p50": "nim.itl",
    "nim_itl_p95": "nim.itl",
    # ---- Unified memory fields (Phase 17 — Grace-Hopper / Blackwell) ----
    "mem_unified_used_bytes": "gpu.memory.unified.used",
    "mem_unified_total_bytes": "gpu.memory.unified.total",
    # ---- TrainingMetrics fields (Phase 15) ----
    "mfu": "training.mfu",
    "tflops": "training.tflops",
    "step_time": "training.step_time",
    "gradient_norm": "training.gradient.norm",
    "gradient_nan_count": "training.gradient.nan_count",
    "gradient_clip_rate": "training.gradient.clip_rate",
    "training_loss": "training.loss",
    "dataloader_wait": "training.dataloader.wait",
    "checkpoint_save_duration": "training.checkpoint.save_duration",
    "checkpoint_save_bandwidth": "training.checkpoint.save_bandwidth",
    "checkpoint_restore_duration": "training.checkpoint.restore_duration",
    # ---- NCCLCollectiveMetrics fields (Phase 13) ----
    "bandwidth_bytes_per_sec": "nccl.collective.bandwidth",
    "bus_bandwidth_bytes_per_sec": "nccl.collective.bus_bandwidth",
    "duration_us": "nccl.collective.duration",
    "message_size_bytes": "nccl.collective.message_size",
    "is_straggler": "nccl.rank.straggler",
    # ---- GPUCostMetrics fields (Phase 11) ----
    "cost_per_gpu_hour": "gpu.cost.per_gpu_hour",
    "cost_rate_per_sec": "gpu.cost.rate",
    "cost_per_prompt_token": "gpu.cost.per_prompt_token",
    "cost_per_generation_token": "gpu.cost.per_generation_token",
    "tokens_per_watt": "gpu.efficiency.tokens_per_watt",
    "joules_per_token": "gpu.efficiency.joules_per_token",
    "is_idle": "gpu.idle",
    "idle_cost_rate_per_sec": "gpu.cost.idle_rate",
    "co2_grams_per_kwh": "gpu.energy.co2_intensity",
    "co2_rate_grams_per_sec": "gpu.energy.co2_rate",
    # ---- GPUFleetHealthMetrics fields (Phase 10) ----
    "xid_last_error_code": "gpu.xid.last_error_code",
    "xid_error_rate": "gpu.xid.error_rate",
    "ecc_sbe_rate": "gpu.ecc.sbe_rate",
    "ecc_dbe_total": "gpu.ecc.dbe_total",
    "row_remap_available": "gpu.row_remap.available",
    "pcie_link_gen_current": "gpu.pcie.link.gen.current",
    "pcie_link_width_current": "gpu.pcie.link.width.current",
    "pcie_link_downtraining": "gpu.pcie.link.downtraining",
    "thermal_ramp_rate": "gpu.thermal.ramp_rate",
    "health_score": "gpu.health.score",
    # ---- TritonMetrics fields (Phase 7) ----
    "triton_requests_success_per_sec": "triton.requests.success",
    "triton_requests_failed_per_sec": "triton.requests.failed",
    "triton_avg_request_latency_us": "triton.request.latency",
    "triton_avg_queue_latency_us": "triton.queue.latency",
    "triton_avg_compute_input_latency_us": "triton.compute.input_latency",
    "triton_avg_compute_infer_latency_us": "triton.compute.latency",
    "triton_avg_compute_output_latency_us": "triton.compute.output_latency",
    "triton_queue_depth": "triton.queue.depth",
    "triton_avg_batch_size": "triton.batch.size",
    # ---- SGLangMetrics fields (Phase 9) ----
    "sglang_prompt_tokens_per_sec": "sglang.prompt.throughput",
    "sglang_generation_tokens_per_sec": "sglang.generation.throughput",
    "sglang_cache_hit_rate": "sglang.cache.hit_rate",
    "sglang_itl_p50": "sglang.itl",
    "sglang_itl_p95": "sglang.itl",
    "sglang_ttft_p50": "sglang.ttft",
    "sglang_ttft_p95": "sglang.ttft",
    "sglang_e2e_latency_p50": "sglang.request.latency",
    "sglang_e2e_latency_p95": "sglang.request.latency",
    "sglang_e2e_latency_p99": "sglang.request.latency",
    "sglang_requests_running": "sglang.requests.running",
    "sglang_requests_waiting": "sglang.requests.waiting",
    # ---- TGIMetrics fields (Phase 9) ----
    "tgi_request_latency_p50": "tgi.request.latency",
    "tgi_request_latency_p95": "tgi.request.latency",
    "tgi_request_latency_p99": "tgi.request.latency",
    "tgi_queue_latency_p50": "tgi.queue.latency",
    "tgi_queue_latency_p95": "tgi.queue.latency",
    "tgi_inference_latency_p50": "tgi.inference.latency",
    "tgi_inference_latency_p95": "tgi.inference.latency",
    "tgi_tpot_p50": "tgi.tpot",
    "tgi_tpot_p95": "tgi.tpot",
    "tgi_batch_size_p50": "tgi.batch.size",
    "tgi_batch_size_p95": "tgi.batch.size",
    "tgi_batch_forward_duration_p50": "tgi.batch.forward_duration",
    "tgi_batch_forward_duration_p95": "tgi.batch.forward_duration",
    "tgi_input_tokens_p50": "tgi.request.input_tokens",
    "tgi_input_tokens_p95": "tgi.request.input_tokens",
    "tgi_output_tokens_p50": "tgi.request.output_tokens",
    "tgi_output_tokens_p95": "tgi.request.output_tokens",
    # ---- HostMetrics fields ----
    "max_gpu_util": "gpu.utilization.max",
    "min_gpu_util": "gpu.utilization.min",
    "avg_gpu_util": "gpu.utilization.avg",
    "ram_util": "host.memory.utilization",
}

# Maps Python field names → OTel UCUM units
FIELD_UNITS: Dict[str, str] = {
    "temperature": "Cel",
    "junction_temperature": "Cel",
    "hbm_temperature": "Cel",
    "power_draw": "W",
    "gpu_util": "1",
    "mem_util": "1",
    "mem_used_percent": "{percent}",
    "power_used_percent": "1",
    "max_gpu_util": "1",
    "min_gpu_util": "1",
    "avg_gpu_util": "1",
    "ram_util": "1",
    "xgmi_link_bandwidth": "By/s",
    "network_rx_bandwidth": "By/s",
    "network_tx_bandwidth": "By/s",
    "retired_pages_count_single_bit": "{row}",
    "retired_pages_count_double_bit": "{row}",
    "ecc_per_block": "{error}",
    "rows_replaced": "{row}",
    "rows_pending": "{row}",
    # Gap 1
    "mem_used_bytes": "By",
    "mem_total_bytes": "By",
    "mem_free_bytes": "By",
    # Gap 2
    "clock_graphics_mhz": "MHz",
    "clock_memory_mhz": "MHz",
    # Gap 3
    "nvlink_tx_bandwidth": "By/s",
    "nvlink_rx_bandwidth": "By/s",
    # Gap 4
    "ecc_errors_volatile_correctable": "{error}",
    "ecc_errors_volatile_uncorrectable": "{error}",
    # Gap 5
    "throttle_reason": "{bool}",
    # Gap 6
    "power_state": "{state}",
    # Gap 7
    "pcie_rx_bytes": "By/s",
    "pcie_tx_bytes": "By/s",
    # Gap 8
    "fan_speed_percent": "1",
    # Gap 9
    "enc_util": "1",
    "dec_util": "1",
    # Gap 10
    "xid_errors": "{error}",
    # Gap 11
    "pcie_replay_count": "{event}",
    # Gap 12
    "total_energy_mj": "mJ",
    # Gap 13
    "throttle_power_software": "{bool}",
    "throttle_temp_hardware": "{bool}",
    "throttle_temp_software": "{bool}",
    "throttle_syncboost": "{bool}",
    # DCGM profiling (dimensionless fractions)
    "sm_active": "1",
    "dram_active": "1",
    "gr_engine_active": "1",
    "tensor_active": "1",
    "fp64_active": "1",
    "fp32_active": "1",
    "fp16_active": "1",
    # Phase 6 — advanced DCGM profiling
    "sm_occupancy": "1",
    "nvlink_tx_bytes": "By/s",
    "nvlink_rx_bytes": "By/s",
    "prof_pcie_tx_bytes": "By/s",
    "prof_pcie_rx_bytes": "By/s",
    # vLLM
    "prompt_tokens_per_sec": "{token}/s",
    "generation_tokens_per_sec": "{token}/s",
    "e2e_latency_p50": "s",
    "e2e_latency_p95": "s",
    "e2e_latency_p99": "s",
    "ttft_p50": "s",
    "ttft_p95": "s",
    "gpu_cache_usage": "1",
    "cpu_cache_usage": "1",
    "requests_running": "{request}",
    "requests_waiting": "{request}",
    "requests_swapped": "{request}",
    # Phase 8 — extended vLLM units
    "itl_p50": "s",
    "itl_p95": "s",
    "itl_p99": "s",
    "prefill_duration_p50": "s",
    "prefill_duration_p95": "s",
    "decode_duration_p50": "s",
    "decode_duration_p95": "s",
    "cache_hit_rate": "1",
    "cache_evictions_per_sec": "{block}/s",
    "spec_decode_acceptance_rate": "1",
    "spec_decode_efficiency": "1",
    "requests_success_per_sec": "{request}/s",
    "requests_finished_stop_per_sec": "{request}/s",
    "requests_finished_length_per_sec": "{request}/s",
    "requests_finished_abort_per_sec": "{request}/s",
    "preemptions_per_sec": "{event}/s",
    "lora_active_count": "{adapter}",
    # Unified memory (GH200/GB200)
    "mem_unified_used_bytes": "By",
    "mem_unified_total_bytes": "By",
    # Training
    "mfu": "1",
    "tflops": "TFLOPS",
    "step_time": "s",
    "gradient_norm": "1",
    "gradient_nan_count": "{param}",
    "gradient_clip_rate": "1",
    "training_loss": "1",
    "dataloader_wait": "s",
    "checkpoint_save_duration": "s",
    "checkpoint_save_bandwidth": "By/s",
    "checkpoint_restore_duration": "s",
    # NCCL
    "bandwidth_bytes_per_sec": "By/s",
    "bus_bandwidth_bytes_per_sec": "By/s",
    "duration_us": "us",
    "message_size_bytes": "By",
    "is_straggler": "{bool}",
    # Cost + carbon
    "cost_per_gpu_hour": "USD/h",
    "cost_rate_per_sec": "USD/s",
    "cost_per_prompt_token": "USD/{token}",
    "cost_per_generation_token": "USD/{token}",
    "tokens_per_watt": "{token}/W",
    "joules_per_token": "J/{token}",
    "is_idle": "{bool}",
    "idle_cost_rate_per_sec": "USD/s",
    "co2_grams_per_kwh": "g/kWh",
    "co2_rate_grams_per_sec": "g/s",
    # Fleet health
    "xid_last_error_code": "{code}",
    "xid_error_rate": "{error}/h",
    "ecc_sbe_rate": "{error}/h",
    "ecc_dbe_total": "{error}",
    "row_remap_available": "{row}",
    "pcie_link_gen_current": "{gen}",
    "pcie_link_width_current": "{lanes}",
    "pcie_link_downtraining": "{bool}",
    "thermal_ramp_rate": "Cel/min",
    "health_score": "1",
    # Triton
    "triton_requests_success_per_sec": "{request}/s",
    "triton_requests_failed_per_sec": "{request}/s",
    "triton_avg_request_latency_us": "us",
    "triton_avg_queue_latency_us": "us",
    "triton_avg_compute_input_latency_us": "us",
    "triton_avg_compute_infer_latency_us": "us",
    "triton_avg_compute_output_latency_us": "us",
    "triton_queue_depth": "{request}",
    "triton_avg_batch_size": "{request}",
    # SGLang
    "sglang_prompt_tokens_per_sec": "{token}/s",
    "sglang_generation_tokens_per_sec": "{token}/s",
    "sglang_cache_hit_rate": "1",
    "sglang_itl_p50": "s",
    "sglang_itl_p95": "s",
    "sglang_ttft_p50": "s",
    "sglang_ttft_p95": "s",
    "sglang_e2e_latency_p50": "s",
    "sglang_e2e_latency_p95": "s",
    "sglang_e2e_latency_p99": "s",
    "sglang_requests_running": "{request}",
    "sglang_requests_waiting": "{request}",
    # TGI
    "tgi_request_latency_p50": "s",
    "tgi_request_latency_p95": "s",
    "tgi_request_latency_p99": "s",
    "tgi_queue_latency_p50": "s",
    "tgi_queue_latency_p95": "s",
    "tgi_inference_latency_p50": "s",
    "tgi_inference_latency_p95": "s",
    "tgi_tpot_p50": "s",
    "tgi_tpot_p95": "s",
    "tgi_batch_size_p50": "{request}",
    "tgi_batch_size_p95": "{request}",
    "tgi_batch_forward_duration_p50": "s",
    "tgi_batch_forward_duration_p95": "s",
    "tgi_input_tokens_p50": "{token}",
    "tgi_input_tokens_p95": "{token}",
    "tgi_output_tokens_p50": "{token}",
    "tgi_output_tokens_p95": "{token}",
    # NIM
    "requests_total": "{request}",
    "requests_failed": "{request}",
    "request_latency_p50": "s",
    "request_latency_p99": "s",
    "batch_size_avg": "{request}",
    "queue_depth": "{request}",
    "kv_cache_usage": "1",
    "nim_itl_p50": "s",
    "nim_itl_p95": "s",
}

# Maps Python field names → data-point attributes for disambiguation.
# These are set on individual data points (not on the OTel Resource).
FIELD_DATA_POINT_ATTRIBUTES: Dict[str, Dict[str, str]] = {
    "temperature": {"gpu.temperature.sensor": "edge"},
    "junction_temperature": {"gpu.temperature.sensor": "hotspot"},
    "hbm_temperature": {"gpu.temperature.sensor": "memory"},
    "retired_pages_count_single_bit": {"gpu.ecc.error_type": "correctable"},
    "retired_pages_count_double_bit": {"gpu.ecc.error_type": "uncorrectable"},
    "gpu_util": {"gpu.task.type": "compute"},
    "mem_util": {"gpu.task.type": "memory_controller"},
    "network_rx_bandwidth": {"gpu.interconnect.direction": "receive"},
    "network_tx_bandwidth": {"gpu.interconnect.direction": "transmit"},
    "xgmi_link_bandwidth": {"gpu.interconnect.type": "xgmi"},
    "rows_replaced": {"gpu.row_remap.state": "replaced"},
    "rows_pending": {"gpu.row_remap.state": "pending"},
    # Gap 2 — disambiguate clock type
    "clock_graphics_mhz": {"gpu.clock.type": "graphics"},
    "clock_memory_mhz": {"gpu.clock.type": "memory"},
    # Gap 3 — disambiguate NVLink direction
    "nvlink_tx_bandwidth": {
        "gpu.interconnect.type": "nvlink",
        "gpu.interconnect.direction": "transmit",
    },
    "nvlink_rx_bandwidth": {
        "gpu.interconnect.type": "nvlink",
        "gpu.interconnect.direction": "receive",
    },
    # Gap 4 — ECC volatile errors (distinguish from cumulative retired-page counts)
    "ecc_errors_volatile_correctable": {
        "gpu.ecc.error_type": "correctable",
        "gpu.ecc.count_type": "volatile",
    },
    "ecc_errors_volatile_uncorrectable": {
        "gpu.ecc.error_type": "uncorrectable",
        "gpu.ecc.count_type": "volatile",
    },
    # Gap 7 — PCIe direction
    "pcie_rx_bytes": {
        "gpu.interconnect.type": "pcie",
        "gpu.interconnect.direction": "receive",
    },
    "pcie_tx_bytes": {
        "gpu.interconnect.type": "pcie",
        "gpu.interconnect.direction": "transmit",
    },
    # Gap 9 — encode/decode task type
    "enc_util": {"gpu.task.type": "encoder"},
    "dec_util": {"gpu.task.type": "decoder"},
    # Gap 13 — named throttle reasons
    "throttle_power_software": {"gpu.throttle.cause": "power_software"},
    "throttle_temp_hardware": {"gpu.throttle.cause": "temp_hardware"},
    "throttle_temp_software": {"gpu.throttle.cause": "temp_software"},
    "throttle_syncboost": {"gpu.throttle.cause": "syncboost"},
    # Phase 6 — advanced DCGM profiling direction attributes
    "nvlink_tx_bytes": {
        "gpu.interconnect.type": "nvlink",
        "gpu.interconnect.direction": "transmit",
        "gpu.interconnect.source": "dcgm_profiling",
    },
    "nvlink_rx_bytes": {
        "gpu.interconnect.type": "nvlink",
        "gpu.interconnect.direction": "receive",
        "gpu.interconnect.source": "dcgm_profiling",
    },
    "prof_pcie_tx_bytes": {
        "gpu.interconnect.type": "pcie",
        "gpu.interconnect.direction": "transmit",
        "gpu.interconnect.source": "dcgm_profiling",
    },
    "prof_pcie_rx_bytes": {
        "gpu.interconnect.type": "pcie",
        "gpu.interconnect.direction": "receive",
        "gpu.interconnect.source": "dcgm_profiling",
    },
    # vLLM — disambiguate shared metric names
    "e2e_latency_p50": {"quantile": "p50"},
    "e2e_latency_p95": {"quantile": "p95"},
    "e2e_latency_p99": {"quantile": "p99"},
    "ttft_p50": {"quantile": "p50"},
    "ttft_p95": {"quantile": "p95"},
    "gpu_cache_usage": {"cache.type": "gpu"},
    "cpu_cache_usage": {"cache.type": "cpu"},
    # Phase 8 — extended vLLM disambiguating attributes
    "itl_p50": {"quantile": "p50"},
    "itl_p95": {"quantile": "p95"},
    "itl_p99": {"quantile": "p99"},
    "prefill_duration_p50": {"quantile": "p50"},
    "prefill_duration_p95": {"quantile": "p95"},
    "decode_duration_p50": {"quantile": "p50"},
    "decode_duration_p95": {"quantile": "p95"},
    "requests_finished_stop_per_sec": {"finish_reason": "stop"},
    "requests_finished_length_per_sec": {"finish_reason": "length"},
    "requests_finished_abort_per_sec": {"finish_reason": "abort"},
    # NIM — disambiguate shared metric names
    "request_latency_p50": {"quantile": "p50"},
    "request_latency_p99": {"quantile": "p99"},
    "nim_itl_p50": {"quantile": "p50"},
    "nim_itl_p95": {"quantile": "p95"},
    # SGLang quantile disambiguation
    "sglang_itl_p50": {"quantile": "p50"},
    "sglang_itl_p95": {"quantile": "p95"},
    "sglang_ttft_p50": {"quantile": "p50"},
    "sglang_ttft_p95": {"quantile": "p95"},
    "sglang_e2e_latency_p50": {"quantile": "p50"},
    "sglang_e2e_latency_p95": {"quantile": "p95"},
    "sglang_e2e_latency_p99": {"quantile": "p99"},
    # TGI quantile disambiguation
    "tgi_request_latency_p50": {"quantile": "p50"},
    "tgi_request_latency_p95": {"quantile": "p95"},
    "tgi_request_latency_p99": {"quantile": "p99"},
    "tgi_queue_latency_p50": {"quantile": "p50"},
    "tgi_queue_latency_p95": {"quantile": "p95"},
    "tgi_inference_latency_p50": {"quantile": "p50"},
    "tgi_inference_latency_p95": {"quantile": "p95"},
    "tgi_tpot_p50": {"quantile": "p50"},
    "tgi_tpot_p95": {"quantile": "p95"},
    "tgi_batch_size_p50": {"quantile": "p50"},
    "tgi_batch_size_p95": {"quantile": "p95"},
    "tgi_batch_forward_duration_p50": {"quantile": "p50"},
    "tgi_batch_forward_duration_p95": {"quantile": "p95"},
    "tgi_input_tokens_p50": {"quantile": "p50"},
    "tgi_input_tokens_p95": {"quantile": "p95"},
    "tgi_output_tokens_p50": {"quantile": "p50"},
    "tgi_output_tokens_p95": {"quantile": "p95"},
}


def get_otel_name(field_name: str) -> str:
    """Return the canonical OTel metric name for a l9gpu field name.

    Falls back to gpu.<field_name> if no explicit mapping exists.
    """
    return FIELD_TO_OTEL_NAME.get(field_name, f"gpu.{field_name}")


def get_unit(field_name: str) -> str:
    """Return the OTel UCUM unit for a l9gpu field name. Defaults to '1'."""
    return FIELD_UNITS.get(field_name, "1")


def get_data_point_attributes(field_name: str) -> Dict[str, str]:
    """Return data-point attributes for disambiguation of a metric field.

    Returns an empty dict if no special attributes are needed.
    """
    attrs = FIELD_DATA_POINT_ATTRIBUTES.get(field_name)
    return dict(attrs) if attrs else {}
