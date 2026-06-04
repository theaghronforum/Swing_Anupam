"""HTTP API that lets the frontend run the swing pipeline.

Run it (from this folder, the one containing the `swing_engine` package):

    pip install fastapi "uvicorn[standard]"
    python server.py
    # or: uvicorn server:app --reload --port 8000

Endpoints:
    GET  /api/health                      -> {status, model_loaded}
    GET  /api/engines                     -> [{id, name}, ...] (all 30)
    GET  /api/symbols                     -> {STOCK:[...], FNO:[...], ...}
    GET  /api/symbols/{asset}             -> [symbols]
    POST /api/run  {asset, symbol, ...}   -> full 30-engine result + trade card
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from swing_engine import Asset, Pipeline, UserProfile, registered_engines
from swing_engine.data import RawDataRepository, LoaderConfig

# --------------------------------------------------------------------------- #
ROOT = os.environ.get("RAW_DATA_ROOT", "raw_data")
BENCHMARK = os.environ.get("BENCHMARK_INDEX", "NIFTY50")
MODEL_PATH = os.environ.get("SWING_MODEL", "swing_model.joblib")

app = FastAPI(title="Swing Trading Engine API", version="1.0.0")

# Allow the Vite dev server (and others) to call us during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_repo: Optional[RawDataRepository] = None
_pipeline = Pipeline()                       # all 30 engines, built once
_asset_cache: Dict[str, object] = {}         # (asset,symbol) -> AssetData


def repo() -> RawDataRepository:
    global _repo
    if _repo is None:
        _repo = RawDataRepository(LoaderConfig(root=ROOT,
                                               benchmark_index_symbol=BENCHMARK))
    return _repo


@lru_cache(maxsize=1)
def load_model():
    try:
        import joblib
        if os.path.exists(MODEL_PATH):
            return joblib.load(MODEL_PATH)
    except Exception:
        pass
    return None


def _asset_enum(name: str) -> Asset:
    try:
        return Asset[name.upper()]
    except KeyError:
        raise HTTPException(404, f"Unknown asset '{name}'")


def _get_asset_data(asset: Asset, symbol: str):
    key = f"{asset.value}:{symbol.upper()}"
    if key not in _asset_cache:
        try:
            _asset_cache[key] = repo().load(asset, symbol)
        except KeyError:
            raise HTTPException(404, f"{symbol} not found under {asset.value}")
    return _asset_cache[key]


# --------------------------------------------------------------------------- #
class RunRequest(BaseModel):
    asset: str
    symbol: str
    capital: float = 1_000_000
    risk_per_trade_pct: float = 1.0
    max_portfolio_risk_pct: float = 6.0


@app.get("/api/health")
def health():
    return {"status": "ok", "model_loaded": load_model() is not None,
            "raw_data_root": ROOT}


@app.get("/api/engines")
def engines() -> List[dict]:
    reg = registered_engines()
    return [{"id": eid, "name": reg[eid].name} for eid in sorted(reg)]


@app.get("/api/symbols")
def symbols() -> Dict[str, List[str]]:
    out = {}
    for a in Asset:
        try:
            out[a.value] = repo().list_symbols(a)
        except Exception:
            out[a.value] = []
    return out


@app.get("/api/symbols/{asset}")
def symbols_for(asset: str) -> List[str]:
    return repo().list_symbols(_asset_enum(asset))


def _model_probability(results) -> Optional[float]:
    """Live model probability from this run's engine outputs, if a model exists."""
    bundle = load_model()
    if not bundle:
        return None
    try:
        from swing_engine.data.dataset import _features_from_results
        import pandas as pd
        feats = _features_from_results(results)
        cols = bundle["features"]
        row = pd.DataFrame([{c: feats.get(c, 0.0) for c in cols}])
        return float(bundle["model"].predict_proba(row)[0, 1])
    except Exception:
        return None


@app.post("/api/run")
def run(req: RunRequest):
    asset = _asset_enum(req.asset)
    ad = _get_asset_data(asset, req.symbol)
    user = UserProfile(
        user_id="frontend", capital=req.capital,
        risk_per_trade_pct=req.risk_per_trade_pct,
        max_portfolio_risk_pct=req.max_portfolio_risk_pct,
        permissions={a.value: True for a in Asset},
    )
    results = _pipeline.run(ad, user)
    gate = results.get(30)
    engines_out = {
        eid: {
            "id": eid, "name": r.engine_name, "score": round(r.score, 1),
            "decision": r.decision, "outputs": r.outputs,
            "warnings": r.warnings, "degraded": r.degraded, "error": r.error,
        }
        for eid, r in results.items()
    }
    return {
        "symbol": ad.symbol,
        "asset": asset.value,
        "as_of": str(ad.daily.index[-1].date()),
        "last_close": float(ad.daily["close"].iloc[-1]),
        "final_action": gate.outputs.get("final_action") if gate else None,
        "approval_status": gate.outputs.get("final_trade_approval_status") if gate else None,
        "execution_priority": gate.outputs.get("execution_priority") if gate else None,
        "trade_card": gate.outputs.get("trade_card") if gate else None,
        "model_probability": _model_probability(results),
        "engines": engines_out,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
