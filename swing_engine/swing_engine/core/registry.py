"""Registry + pipeline.

Engines self-register via the `@register` decorator. The `Pipeline` builds the
indicator bundle once, then runs engines in ascending engine_id order, feeding
each engine the accumulated upstream results so the Gatekeeper (Engine 30) can
synthesise everything.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Type

from .base_engine import BaseEngine
from .models import (
    AssetData,
    EngineContext,
    EngineResult,
    IndicatorBundle,
    UserProfile,
)

logger = logging.getLogger("swing_engine")

_REGISTRY: Dict[int, Type[BaseEngine]] = {}


def register(cls: Type[BaseEngine]) -> Type[BaseEngine]:
    """Class decorator: register an engine by its engine_id."""
    if cls.engine_id in _REGISTRY:
        raise ValueError(f"Duplicate engine_id {cls.engine_id} ({cls.name})")
    _REGISTRY[cls.engine_id] = cls
    return cls


def registered_engines() -> Dict[int, Type[BaseEngine]]:
    return dict(_REGISTRY)


class Pipeline:
    """Runs a configurable subset of engines for one asset."""

    def __init__(self, engine_ids: List[int] | None = None, config: dict | None = None):
        all_ids = sorted(_REGISTRY)
        self.engine_ids = sorted(engine_ids) if engine_ids else all_ids
        unknown = set(self.engine_ids) - set(_REGISTRY)
        if unknown:
            raise ValueError(f"Unknown engine_ids requested: {sorted(unknown)}")
        self.config = config or {}
        self._engines = {eid: _REGISTRY[eid]() for eid in self.engine_ids}

    def run(self, asset_data: AssetData, user: UserProfile) -> Dict[int, EngineResult]:
        indicators = IndicatorBundle.build(asset_data.daily)
        ctx = EngineContext(
            asset_data=asset_data,
            user=user,
            indicators=indicators,
            upstream={},
            config=self.config,
        )
        results: Dict[int, EngineResult] = {}
        for eid in self.engine_ids:
            engine = self._engines[eid]
            res = engine.run(ctx)
            results[eid] = res
            ctx.upstream[eid] = res  # make available to later engines
            if res.error:
                logger.warning("Engine %s (%s) error on %s: %s",
                               eid, engine.name, asset_data.symbol, res.error)
        return results

    def run_trade_card(self, asset_data: AssetData, user: UserProfile) -> dict:
        """Run all engines and return the Gatekeeper trade card (Engine 30)."""
        results = self.run(asset_data, user)
        gate = results.get(30)
        return {
            "symbol": asset_data.symbol,
            "asset": asset_data.asset.value,
            "trade_card": gate.outputs.get("trade_card") if gate else None,
            "final_action": gate.outputs.get("final_action") if gate else None,
            "all_results": {eid: r.to_dict() for eid, r in results.items()},
        }
