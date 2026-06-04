"""Swing Trading Engine — 30-engine decision stack for Stocks, F&O, Index,
Forex and Commodities.

Quick start
-----------
    from swing_engine import Pipeline, AssetData, UserProfile, Asset

    pipe = Pipeline()                       # all registered engines (2-30)
    results = pipe.run(asset_data, user)    # dict[engine_id -> EngineResult]
    card = pipe.run_trade_card(asset_data, user)   # gatekeeper trade card
"""
from .core import (
    Asset,
    AssetData,
    UserProfile,
    EngineContext,
    EngineResult,
    IndicatorBundle,
    BaseEngine,
    Pipeline,
    register,
    registered_engines,
    indicators,
)

# Importing engines registers all of them.
from . import engines  # noqa: F401  (side-effect import)

__version__ = "1.0.0"

__all__ = [
    "Asset",
    "AssetData",
    "UserProfile",
    "EngineContext",
    "EngineResult",
    "IndicatorBundle",
    "BaseEngine",
    "Pipeline",
    "register",
    "registered_engines",
    "indicators",
]
