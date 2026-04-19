# Copyright (c) Last9, Inc.
"""PyTorch training hooks for l9gpu observability.

Attaches lightweight hooks to model, optimizer, and DataLoader to capture
gradient health, step timing, DataLoader wait, and checkpoint I/O metrics.
"""

import time
import logging
from typing import Any, Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    import torch

logger = logging.getLogger(__name__)


class GradientTracker:
    """Tracks gradient norm, NaN counts, and clipping rate across steps."""

    def __init__(self) -> None:
        self._clip_count = 0
        self._step_count = 0
        self._last_norm: Optional[float] = None
        self._last_nan_count: Optional[int] = None

    def record_step(
        self,
        model: "torch.nn.Module",
        max_norm: Optional[float] = None,
    ) -> None:
        """Call after loss.backward() and before optimizer.step()."""
        try:
            total_norm = 0.0
            nan_count = 0
            for p in model.parameters():
                if p.grad is not None:
                    param_norm = p.grad.data.norm(2).item()
                    if param_norm != param_norm:  # NaN check
                        nan_count += 1
                    else:
                        total_norm += param_norm**2
            self._last_norm = total_norm**0.5
            self._last_nan_count = nan_count

            if max_norm is not None and self._last_norm > max_norm:
                self._clip_count += 1
        except Exception as exc:
            logger.debug("Gradient tracking error: %s", exc)
        finally:
            self._step_count += 1

    @property
    def gradient_norm(self) -> Optional[float]:
        return self._last_norm

    @property
    def gradient_nan_count(self) -> Optional[int]:
        return self._last_nan_count

    @property
    def gradient_clip_rate(self) -> Optional[float]:
        if self._step_count == 0:
            return None
        return self._clip_count / self._step_count


class DataLoaderTimer:
    """Wraps a DataLoader to measure per-batch wait time."""

    def __init__(self, dataloader: Any) -> None:
        self._dl = dataloader
        self._last_wait: Optional[float] = None

    def __iter__(self):
        it = iter(self._dl)
        while True:
            t0 = time.perf_counter()
            try:
                batch = next(it)
            except StopIteration:
                break
            self._last_wait = time.perf_counter() - t0
            yield batch

    def __len__(self):
        return len(self._dl)

    @property
    def last_wait_seconds(self) -> Optional[float]:
        return self._last_wait


class CheckpointTimer:
    """Context managers for timing checkpoint save/restore operations."""

    def __init__(self) -> None:
        self.last_save_duration: Optional[float] = None
        self.last_save_bandwidth: Optional[float] = None
        self.last_restore_duration: Optional[float] = None

    def time_save(self, checkpoint_size_bytes: Optional[int] = None):
        """Use as: with monitor.checkpoint.time_save(size_bytes): model.save(...)"""
        return _TimedBlock(
            on_exit=lambda elapsed: self._record_save(elapsed, checkpoint_size_bytes)
        )

    def time_restore(self):
        """Use as: with monitor.checkpoint.time_restore(): model.load(...)"""
        return _TimedBlock(
            on_exit=lambda elapsed: setattr(self, "last_restore_duration", elapsed)
        )

    def _record_save(self, elapsed: float, size_bytes: Optional[int]) -> None:
        self.last_save_duration = elapsed
        if size_bytes and elapsed > 0:
            self.last_save_bandwidth = size_bytes / elapsed


class _TimedBlock:
    def __init__(self, on_exit: Callable[[float], None]) -> None:
        self._on_exit = on_exit
        self._start: float = 0.0

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, *args):
        self._on_exit(time.perf_counter() - self._start)
