"""Assemble model-ready training data: engine outputs as features + forward labels.

For each symbol we walk history bar by bar (with a configurable stride), slice the
data *as of* that date (no look-ahead), run a chosen subset of engines, and turn
their scores + numeric outputs into a feature row. We then attach the forward
labels from `labels.make_labels`. The result is one tidy DataFrame you can feed
straight into scikit-learn / XGBoost / LightGBM.

This is the bridge described in your Implementation Notes: raw -> indicators ->
model-ready features -> outcome labels, all kept as separate layers.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Sequence

import pandas as pd

from ..core.enums import Asset
from ..core.models import AssetData, UserProfile
from ..core.registry import Pipeline
from .labels import make_labels

logger = logging.getLogger("swing_engine.data")

# Self-contained technical engines that make good features (no portfolio/user dep).
DEFAULT_FEATURE_ENGINES = [4, 5, 6, 7, 8, 9, 10, 11, 12, 21]
# Add F&O confirmation when training on derivatives.
FNO_FEATURE_ENGINES = DEFAULT_FEATURE_ENGINES + [20]

_NEUTRAL_USER = UserProfile(user_id="train", capital=1_000_000,
                            permissions={a.value: True for a in Asset})


def _slice_asset(ad: AssetData, upto: pd.Timestamp) -> AssetData:
    """Return a copy of `ad` containing only data up to and including `upto`."""
    daily = ad.daily.loc[:upto]
    weekly = (ad.weekly.loc[:upto] if ad.weekly is not None else None)
    extras = {}
    for k, v in ad.extras.items():
        if isinstance(v, pd.Series):
            s = v.loc[:upto]
            extras[k] = s
            base = k[:-7] if k.endswith("_series") else k
            if not s.empty:
                extras[base] = float(s.iloc[-1])
        elif isinstance(v, pd.DataFrame):
            extras[k] = v.loc[:upto]
        else:
            extras[k] = v
    return AssetData(asset=ad.asset, symbol=ad.symbol, daily=daily,
                     weekly=weekly, extras=extras)


_SCALE_FREE_TOKENS = ("score", "probability", "confidence", "ratio", "pct",
                      "depth", "strength", "percentile", "rate", "relative",
                      "utilisation", "multiple", "rvol")
_ABSOLUTE_TOKENS = ("level", "price", "target", "stop", "entry", "swing",
                    "pain", "support", "resistance", "zone", "_high", "_low",
                    "reward", "distance", "move", "range")


def _features_from_results(results: dict, scale_free_only: bool = True) -> dict:
    """Flatten engine results into a numeric feature dict.

    With `scale_free_only=True` (recommended for cross-symbol training) only
    scores, ratios, percentages, probabilities and boolean flags are kept;
    absolute price levels (entry/stop/target/swing-highs/...) are dropped because
    they don't generalise across instruments or price regimes.
    """
    feats: dict = {}
    for eid, r in results.items():
        feats[f"e{eid:02d}_score"] = r.score
        for k, v in r.outputs.items():
            if isinstance(v, bool):
                feats[f"e{eid:02d}_{k}"] = int(v)
                continue
            if not isinstance(v, (int, float)):
                continue
            if scale_free_only:
                kl = k.lower()
                scale_free = any(tok in kl for tok in _SCALE_FREE_TOKENS)
                absolute = any(tok in kl for tok in _ABSOLUTE_TOKENS)
                if absolute and not scale_free:
                    continue
                if not scale_free and not absolute:
                    continue  # unknown -> drop to stay safe
            feats[f"e{eid:02d}_{k}"] = float(v)
    return feats


def build_symbol_dataset(
    ad: AssetData,
    feature_engine_ids: Optional[Sequence[int]] = None,
    horizons: Sequence[int] = (3, 5, 10, 15),
    stride: int = 1,
    warmup: int = 210,
    stop_atr_mult: float = 1.5,
    target_atr_mult: float = 3.0,
    direction: int = 1,
    user: Optional[UserProfile] = None,
    max_rows: Optional[int] = None,
) -> pd.DataFrame:
    """Build the (features + labels) table for a single instrument."""
    if feature_engine_ids is None:
        feature_engine_ids = (FNO_FEATURE_ENGINES if ad.asset == Asset.FNO
                              else DEFAULT_FEATURE_ENGINES)
    user = user or _NEUTRAL_USER
    pipe = Pipeline(engine_ids=list(feature_engine_ids))
    labels = make_labels(ad.daily, horizons=horizons, stop_atr_mult=stop_atr_mult,
                         target_atr_mult=target_atr_mult, direction=direction)
    if labels.empty:
        return pd.DataFrame()

    valid_dates = labels.index
    idx_positions = range(warmup, len(ad.daily), max(1, stride))
    rows: List[dict] = []
    for pos in idx_positions:
        date = ad.daily.index[pos]
        if date not in valid_dates:
            continue
        sliced = _slice_asset(ad, date)
        if len(sliced.daily) < warmup:
            continue
        try:
            results = pipe.run(sliced, user)
        except Exception as exc:
            logger.debug("feature run failed %s @ %s: %s", ad.symbol, date, exc)
            continue
        row = {"symbol": ad.symbol, "asset": ad.asset.value, "date": date}
        row.update(_features_from_results(results))
        row.update(labels.loc[date].to_dict())
        rows.append(row)
        if max_rows and len(rows) >= max_rows:
            break

    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).set_index(["symbol", "date"])
    return df


def build_dataset(
    repo,
    assets: Optional[Sequence[Asset]] = None,
    symbols_per_asset: Optional[int] = None,
    **kwargs,
) -> pd.DataFrame:
    """Build one combined training table across many symbols / assets.

    `repo` is a `RawDataRepository`. Extra kwargs flow to `build_symbol_dataset`.
    """
    from .loaders import RawDataRepository  # local import to avoid cycle
    assert isinstance(repo, RawDataRepository)
    assets = assets or list(dict.fromkeys(repo.cfg.folder_map.values()))
    frames: List[pd.DataFrame] = []
    for asset in assets:
        for ad in repo.load_all(asset, limit=symbols_per_asset):
            df = build_symbol_dataset(ad, **kwargs)
            if not df.empty:
                frames.append(df)
                logger.info("built %d rows for %s/%s", len(df), asset.value, ad.symbol)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames).sort_index()


def feature_label_split(df: pd.DataFrame, label: str = "label_bin"):
    """Convenience: split into (X, y), dropping all label/leakage columns from X."""
    leak_prefixes = ("fwd_ret_", "mfe_", "mae_")
    leak_cols = [c for c in df.columns
                 if c.startswith(leak_prefixes) or c in
                 ("stop_hit", "target_hit", "holding_outcome", "days_to_exit",
                  "label_bin", "asset")]
    feature_cols = [c for c in df.columns if c not in leak_cols]
    X = df[feature_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    y = df[label]
    return X, y, feature_cols
