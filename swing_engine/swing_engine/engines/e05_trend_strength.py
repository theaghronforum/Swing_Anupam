"""Engine 5: Trend Strength Detection Engine."""
from __future__ import annotations

from typing import Any, Dict

from ..core.base_engine import BaseEngine
from ..core.enums import Asset, Regime, StrategyTag, TrendDirection
from ..core.indicators import clamp
from ..core.models import EngineContext
from ..core.registry import register


@register
class TrendStrengthEngine(BaseEngine):
    """5. Measures trend direction/strength and continuation vs exhaustion."""

    engine_id = 5
    name = "Trend Strength Detection Engine"
    min_history = 50

    def evaluate(self, ctx: EngineContext) -> Dict[str, Any]:
        ad, ix = ctx.asset_data, ctx.indicators
        warnings = []

        up = ix.last_close > ix.ema20 > ix.ema50 and ix.plus_di > ix.minus_di
        down = ix.last_close < ix.ema20 < ix.ema50 and ix.minus_di > ix.plus_di

        if up and ix.adx >= 20:
            direction = TrendDirection.UPTREND
        elif down and ix.adx >= 20:
            direction = TrendDirection.DOWNTREND
        elif ix.adx < 15:
            direction = TrendDirection.SIDEWAYS
        elif ix.adx < 22:
            direction = TrendDirection.WEAK
        else:
            direction = TrendDirection.MIXED

        # Daily / weekly / swing alignment.
        weekly = ad.weekly
        weekly_up = bool(weekly is not None and len(weekly) >= 10 and
                         weekly["close"].iloc[-1] > weekly["close"].rolling(10).mean().iloc[-1])
        daily_score = clamp(ix.adx * 2 + (15 if up or down else 0))
        weekly_score = 75.0 if weekly_up == (direction == TrendDirection.UPTREND) else 40.0
        swing_score = clamp(abs(ix.ema20_slope) * 12 + ix.adx)
        strength = round((daily_score + weekly_score + swing_score) / 3, 1)

        # Continuation vs exhaustion from RSI extremes + slope.
        exhaustion = clamp((ix.rsi14 - 70) * 3 if ix.rsi14 > 70 else (30 - ix.rsi14) * 3 if ix.rsi14 < 30 else 0)
        continuation = round(clamp(strength - exhaustion * 0.5), 1)
        if exhaustion > 50:
            warnings.append(self.warn("momentum extreme — exhaustion risk"))

        grade = self.grade(strength, [(70, "strong"), (45, "weak"), (0, "no-trade")])
        if direction == TrendDirection.UPTREND:
            trend_grade = f"{grade} buy trend" if grade != "no-trade" else "no-trade trend"
        elif direction == TrendDirection.DOWNTREND:
            trend_grade = f"{grade} sell trend" if grade != "no-trade" else "no-trade trend"
        else:
            trend_grade = "no-trade trend"

        outputs = {
            "trend_direction": direction.value,
            "trend_strength": strength,
            "timeframe_scores": {"daily": round(daily_score, 1),
                                  "weekly": round(weekly_score, 1),
                                  "swing": round(swing_score, 1)},
            "continuation_probability": continuation,
            "exhaustion_probability": round(exhaustion, 1),
            "segment_confidence": {ad.asset.value: strength},
            "trend_grade": trend_grade,
        }
        return {"outputs": outputs, "score": strength,
                "decision": trend_grade, "warnings": warnings}
