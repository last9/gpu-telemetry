# Copyright (c) Last9, Inc.
"""L9GPU training observability library.

Lightweight instrumentation for PyTorch training jobs that exports metrics
(MFU, gradient health, checkpoint I/O, DataLoader wait) via OTLP.

Quick start:
    from l9gpu.training import L9GPUTrainingMonitor

    monitor = L9GPUTrainingMonitor(
        otlp_endpoint="http://otel-collector:4317",
        num_params=7_000_000_000,     # model parameter count
        tokens_per_step=4096,          # batch_size × seq_len
        gpu_count=8,
        peak_tflops_per_gpu=989.0,    # H100 BF16
    )
    monitor.wrap_dataloader(train_dataloader)

    # In training loop:
    for batch in monitor.dataloader:
        t0 = time.perf_counter()
        loss = model(batch)
        loss.backward()
        monitor.gradients.record_step(model, max_norm=1.0)
        optimizer.step()
        step_time = time.perf_counter() - t0
        monitor.emit_step(loss=loss.item(), step_time=step_time)

    # Around checkpoint saves:
    size = os.path.getsize(checkpoint_path)
    with monitor.checkpoint.time_save(size):
        torch.save(state_dict, checkpoint_path)
"""

import logging
from typing import Any, Optional

from l9gpu.schemas.training_metrics import TrainingMetrics
from l9gpu.training.hooks import CheckpointTimer, DataLoaderTimer, GradientTracker
from l9gpu.training.mfu import compute_mfu, compute_tflops

logger = logging.getLogger(__name__)


class L9GPUTrainingMonitor:
    """Collects and exports training observability metrics.

    Metrics are exported via OTLP using the opentelemetry-sdk.
    Falls back to debug logging if OTLP is unavailable.
    """

    def __init__(
        self,
        *,
        otlp_endpoint: str,
        num_params: int,
        tokens_per_step: int,
        gpu_count: int,
        peak_tflops_per_gpu: float,
        gradient_checkpointing: bool = False,
        service_name: str = "l9gpu-training",
    ) -> None:
        self._num_params = num_params
        self._tokens_per_step = tokens_per_step
        self._gpu_count = gpu_count
        self._peak_tflops = peak_tflops_per_gpu
        self._grad_ckpt = gradient_checkpointing

        self.gradients = GradientTracker()
        self.checkpoint = CheckpointTimer()
        self.dataloader: Optional[DataLoaderTimer] = None

        # Set up OTLP exporter
        self._meter = self._init_meter(otlp_endpoint, service_name)

    def _init_meter(self, endpoint: str, service_name: str):
        try:
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
            from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
                OTLPMetricExporter,
            )
            from opentelemetry.sdk.resources import Resource, SERVICE_NAME

            resource = Resource({SERVICE_NAME: service_name})
            exporter = OTLPMetricExporter(endpoint=endpoint, insecure=True)
            reader = PeriodicExportingMetricReader(
                exporter, export_interval_millis=30_000, export_timeout_millis=5_000
            )
            provider = MeterProvider(resource=resource, metric_readers=[reader])
            meter = provider.get_meter("l9gpu-training")
            logger.info("Training monitor OTLP export to %s", endpoint)
            return meter
        except Exception as exc:
            logger.warning(
                "OTLP meter init failed (%s); metrics will only be logged", exc
            )
            return None

    def wrap_dataloader(self, dataloader: Any) -> "DataLoaderTimer":
        """Wrap a DataLoader with timing instrumentation and return it."""
        self.dataloader = DataLoaderTimer(dataloader)
        return self.dataloader

    def collect(
        self, loss: Optional[float] = None, step_time: Optional[float] = None
    ) -> TrainingMetrics:
        """Collect a TrainingMetrics snapshot for the current step."""
        mfu_val: Optional[float] = None
        tflops_val: Optional[float] = None
        if step_time and step_time > 0 and self._peak_tflops > 0:
            mfu_val = compute_mfu(
                self._num_params,
                self._tokens_per_step,
                step_time,
                self._gpu_count,
                self._peak_tflops,
                self._grad_ckpt,
            )
            tflops_val = compute_tflops(
                self._num_params, self._tokens_per_step, step_time, self._grad_ckpt
            )

        return TrainingMetrics(
            mfu=mfu_val,
            tflops=tflops_val,
            step_time=step_time,
            gradient_norm=self.gradients.gradient_norm,
            gradient_nan_count=self.gradients.gradient_nan_count,
            gradient_clip_rate=self.gradients.gradient_clip_rate,
            training_loss=loss,
            dataloader_wait=(
                self.dataloader.last_wait_seconds if self.dataloader else None
            ),
            checkpoint_save_duration=self.checkpoint.last_save_duration,
            checkpoint_save_bandwidth=self.checkpoint.last_save_bandwidth,
            checkpoint_restore_duration=self.checkpoint.last_restore_duration,
        )

    def emit_step(
        self, loss: Optional[float] = None, step_time: Optional[float] = None
    ) -> TrainingMetrics:
        """Collect metrics for the current step and emit via OTLP (if configured)."""
        metrics = self.collect(loss=loss, step_time=step_time)

        if self._meter is not None:
            self._emit_to_meter(metrics)
        else:
            logger.debug(
                "training step: mfu=%.3f tflops=%.1f loss=%s",
                metrics.mfu or 0,
                metrics.tflops or 0,
                loss,
            )
        return metrics

    def _emit_to_meter(self, m: TrainingMetrics) -> None:
        """Emit TrainingMetrics fields as OTel gauges."""
        from dataclasses import fields as dc_fields
        from l9gpu.exporters.metric_names import get_otel_name, get_unit

        for f in dc_fields(m):
            val = getattr(m, f.name)
            if val is None or not isinstance(val, (int, float)):
                continue
            otel_name = get_otel_name(f.name)
            try:
                gauge = self._meter.create_gauge(otel_name, unit=get_unit(f.name))
                gauge.set(val)
            except Exception as exc:
                logger.debug("Failed to emit %s: %s", otel_name, exc)
