"""Base class every engine inherits from.

Subclasses implement `evaluate(ctx) -> dict` and set class attributes
`engine_id`, `name`. The base `run` wraps evaluation with timing, structured
error capture and degraded-mode handling so one bad asset never crashes a run.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Tuple

from .enums import Severity
from .exceptions import InsufficientDataError
from .models import EngineContext, EngineResult


class BaseEngine(ABC):
    engine_id: int = 0
    name: str = "BaseEngine"

    # Minimum daily candles required; subclasses override.
    min_history: int = 30

    # ---- public API ------------------------------------------------------ #
    def run(self, ctx: EngineContext) -> EngineResult:
        start = time.perf_counter()
        result = EngineResult(
            engine_id=self.engine_id,
            engine_name=self.name,
            asset=ctx.asset,
            symbol=ctx.asset_data.symbol,
        )
        try:
            self._check_history(ctx)
            payload = self.evaluate(ctx)
            result.outputs = payload.get("outputs", {})
            result.score = float(payload.get("score", 0.0))
            result.decision = str(payload.get("decision", ""))
            result.warnings = list(payload.get("warnings", []))
            result.degraded = bool(payload.get("degraded", False))
        except InsufficientDataError as exc:
            result.degraded = True
            result.error = str(exc)
            result.decision = "insufficient-data"
            result.warnings.append(f"degraded: {exc}")
        except Exception as exc:  # never let one engine kill the pipeline
            result.error = f"{type(exc).__name__}: {exc}"
            result.decision = "error"
            result.warnings.append(result.error)
        result.elapsed_ms = (time.perf_counter() - start) * 1000.0
        return result

    @abstractmethod
    def evaluate(self, ctx: EngineContext) -> Dict[str, Any]:
        """Return {'outputs': {...}, 'score': float, 'decision': str,
        'warnings': [...], 'degraded': bool}."""
        raise NotImplementedError

    # ---- shared helpers -------------------------------------------------- #
    def _check_history(self, ctx: EngineContext) -> None:
        if len(ctx.asset_data.daily) < self.min_history:
            raise InsufficientDataError(
                f"{self.name} needs >= {self.min_history} daily candles, "
                f"got {len(ctx.asset_data.daily)}"
            )

    @staticmethod
    def grade(score: float, bands: List[Tuple[float, str]]) -> str:
        """Map a 0..100 score to a label using descending (threshold, label)."""
        for threshold, label in bands:
            if score >= threshold:
                return label
        return bands[-1][1]

    @staticmethod
    def warn(msg: str, severity: Severity = Severity.MEDIUM) -> str:
        return f"[{severity.value}] {msg}"
