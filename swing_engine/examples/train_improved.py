"""Improved training — better labels, more data, honest evaluation.

Why your first run looked low:
  * accuracy is misleading with a ~30% positive class (a do-nothing model scores
    ~0.70); AUC is the metric that matters here.
  * the default label ("+3 ATR before -1.5 ATR") is hard and imbalanced.
  * a single recent-30% split is high-variance.

This script:
  1. Builds the dataset ONCE and caches it to parquet (rebuilds are instant).
  2. Lets you pick a more learnable label.
  3. Uses class weighting + HistGradientBoosting (or XGBoost if installed).
  4. Evaluates with time-series cross-validation and reports AUC, baseline,
     and lift in the top-decile (what matters for picking trades).

Usage:
    PYTHONPATH=. python examples/train_improved.py raw_data
    PYTHONPATH=. python examples/train_improved.py raw_data --label updays5
    PYTHONPATH=. python examples/train_improved.py raw_data --label ret10_pos --stride 1

Labels:
    target    : original — target hit before stop (hard, ~0.3 positive)
    updays5   : forward 5-day return > 0           (balanced, easiest)
    updays10  : forward 10-day return > 0
    ret10_pos : forward 10-day return > +2%        (selective, economically meaningful)
"""
from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd

from swing_engine import Asset
from swing_engine.data import RawDataRepository, LoaderConfig, build_dataset


LEAK_PREFIXES = ("fwd_ret_", "mfe_", "mae_")
LEAK_EXACT = {"stop_hit", "target_hit", "holding_outcome", "days_to_exit",
              "label_bin", "asset"}


def derive_label(ds: pd.DataFrame, name: str) -> pd.Series:
    if name == "target":
        return ds["label_bin"].astype(float)
    if name == "updays5":
        return (ds["fwd_ret_5"] > 0).astype(float)
    if name == "updays10":
        return (ds["fwd_ret_10"] > 0).astype(float)
    if name == "ret10_pos":
        return (ds["fwd_ret_10"] > 2.0).astype(float)
    raise ValueError(f"unknown label '{name}'")


def feature_columns(ds: pd.DataFrame):
    return [c for c in ds.columns
            if not c.startswith(LEAK_PREFIXES) and c not in LEAK_EXACT]


def get_model(pos_weight: float):
    """Prefer XGBoost/LightGBM if installed, else sklearn HistGradientBoosting."""
    try:
        from xgboost import XGBClassifier
        return XGBClassifier(
            n_estimators=400, max_depth=4, learning_rate=0.03,
            subsample=0.8, colsample_bytree=0.8,
            scale_pos_weight=pos_weight, eval_metric="auc",
            n_jobs=-1, random_state=0), "XGBoost"
    except ImportError:
        pass
    from sklearn.ensemble import HistGradientBoostingClassifier
    return HistGradientBoostingClassifier(
        max_iter=400, max_depth=4, learning_rate=0.05,
        l2_regularization=1.0, class_weight="balanced",
        random_state=0), "HistGradientBoosting(sklearn)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", nargs="?", default="raw_data")
    ap.add_argument("--label", default="updays5",
                    choices=["target", "updays5", "updays10", "ret10_pos"])
    ap.add_argument("--stride", type=int, default=2)
    ap.add_argument("--warmup", type=int, default=210)
    ap.add_argument("--cache", default="train_cache.parquet")
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--symbols-per-asset", type=int, default=None)
    args = ap.parse_args()

    # ---- 1. build or load cached dataset -------------------------------- #
    if os.path.exists(args.cache) and not args.rebuild:
        print(f"Loading cached dataset: {args.cache}")
        ds = pd.read_parquet(args.cache)
    else:
        print("Building dataset (this is the slow step; cached afterwards)...")
        repo = RawDataRepository(LoaderConfig(root=args.root,
                                              benchmark_index_symbol="NIFTY50"))
        ds = build_dataset(
            repo,
            assets=[Asset.STOCK, Asset.FNO, Asset.INDEX,
                    Asset.FOREX, Asset.COMMODITY],
            symbols_per_asset=args.symbols_per_asset,
            stride=args.stride, warmup=args.warmup,
            horizons=(3, 5, 10, 15),
            stop_atr_mult=1.5, target_atr_mult=3.0,
        )
        if ds.empty:
            print("No rows built — check the loader/diagnostic.")
            return
        ds.to_parquet(args.cache)
        print(f"Cached -> {args.cache}")

    print("dataset:", ds.shape,
          "| symbols:", ds.index.get_level_values("symbol").nunique())

    # ---- 2. features + chosen label ------------------------------------- #
    y = derive_label(ds, args.label)
    cols = feature_columns(ds)
    X = ds[cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    mask = y.notna()
    X, y = X[mask], y[mask]
    base_rate = float(y.mean())
    print(f"label '{args.label}': {len(y)} rows | positive rate {base_rate:.3f} "
          f"| features {len(cols)}")
    print(f"naive baseline accuracy (predict majority): {max(base_rate, 1-base_rate):.3f}")

    # ---- 3. time-series cross-validation -------------------------------- #
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.metrics import roc_auc_score, average_precision_score

    # sort by date so folds respect time
    order = ds.index.get_level_values("date").argsort()
    Xo, yo = X.iloc[order], y.iloc[order]
    pos_weight = (1 - base_rate) / max(base_rate, 1e-6)

    tscv = TimeSeriesSplit(n_splits=5)
    aucs, aps = [], []
    for k, (tr, te) in enumerate(tscv.split(Xo), 1):
        model, mname = get_model(pos_weight)
        model.fit(Xo.iloc[tr], yo.iloc[tr])
        p = model.predict_proba(Xo.iloc[te])[:, 1]
        if len(np.unique(yo.iloc[te])) < 2:
            continue
        auc = roc_auc_score(yo.iloc[te], p)
        ap_ = average_precision_score(yo.iloc[te], p)
        aucs.append(auc); aps.append(ap_)
        print(f"  fold {k}: AUC {auc:.3f} | avg-precision {ap_:.3f} "
              f"(test n={len(te)})")
    print(f"\nMODEL: {mname}")
    print(f"CV mean AUC: {np.mean(aucs):.3f} +/- {np.std(aucs):.3f}")
    print(f"CV mean avg-precision: {np.mean(aps):.3f}  (baseline = {base_rate:.3f})")

    # ---- 4. final fit on all-but-last, evaluate top-decile lift --------- #
    cut = int(len(Xo) * 0.8)
    model, _ = get_model(pos_weight)
    model.fit(Xo.iloc[:cut], yo.iloc[:cut])
    p = model.predict_proba(Xo.iloc[cut:])[:, 1]
    yte = yo.iloc[cut:].values
    thresh = np.quantile(p, 0.9)
    top = p >= thresh
    if top.sum() > 0:
        lift = yte[top].mean() / max(base_rate, 1e-6)
        print(f"\nTop-decile precision: {yte[top].mean():.3f} "
              f"(lift {lift:.2f}x over base {base_rate:.3f})")
        print("-> trade only the highest-confidence signals; lift > 1 means the "
              "model concentrates winners.")

    # ---- 5. importances + save ------------------------------------------ #
    try:
        import joblib
        joblib.dump({"model": model, "features": cols, "label": args.label}, "swing_model.joblib")
        print("\nsaved -> swing_model.joblib")
    except ImportError:
        pass

    imp = getattr(model, "feature_importances_", None)
    if imp is not None:
        print("top features:")
        for n, i in sorted(zip(cols, imp), key=lambda t: -t[1])[:10]:
            print(f"   {n:34s} {i:.3f}")


if __name__ == "__main__":
    main()
