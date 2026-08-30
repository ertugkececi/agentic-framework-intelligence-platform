"""Immutable resource and wall-clock quotas for development runs."""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class DevelopmentQuota:
    """Hard upper bounds shared by all attempts in one development run."""

    max_duration_seconds: float = 900.0
    max_model_calls: int = 16
    max_command_executions: int = 32
    max_generated_bytes: int = 1_000_000

    def __post_init__(self) -> None:
        duration = self.max_duration_seconds
        if not isinstance(duration, (int, float)) or isinstance(duration, bool) or not math.isfinite(duration) or duration <= 0:
            raise ValueError("max_duration_seconds must be finite and positive")
        for name in ("max_model_calls", "max_command_executions", "max_generated_bytes"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(f"{name} must be an integer")
            if value < 1:
                raise ValueError(f"{name} must be positive")


@dataclass(frozen=True)
class ResourceUsage:
    """Checkpoint-safe cumulative resource consumption for one run."""

    model_calls: int = 0
    command_executions: int = 0
    generated_bytes: int = 0

    def after_model_call(self, generated_bytes: int) -> ResourceUsage:
        return ResourceUsage(self.model_calls + 1, self.command_executions, self.generated_bytes + generated_bytes)

    def after_command(self) -> ResourceUsage:
        return ResourceUsage(self.model_calls, self.command_executions + 1, self.generated_bytes)
