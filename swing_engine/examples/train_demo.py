"""Training demo — wire your `raw_data/` tree to a trained swing model.

Usage:
    PYTHONPATH=. python examples/train_demo.py [raw_data_root]

Steps:
  1. RawDataRepository reads raw_data/{ohlcv,fo,index,forex,commodities}.
  2. build_dataset walks history as-of each bar, runs the technical engines,
     and attaches forward labels (target-hit before stop-hit) from your spec.
  3. Train a classifier; persist it. In production you would point each engine's
     scoring block at the loaded model (see README "Plugging in trained models").
"""
from __future__ import annotations

import sys

from swing_engine import Asset
from swing_engine.data import (
    RawDataRepository,
    LoaderConfig,
    build_dataset,
    feature_label_split,
)


def main(root: str = "raw_data") -> None:
    repo = RawDataRepository(LoaderConfig(root=root, benchmark_index_symbol="NIFTY50"))

    print("Discovered symbols per asset:")
    for a in Asset:
        try:
            print(f"  {a.value:10s} {repo.list_symbols(a)}")
        except (FileNotFoundError, KeyError):
            print(f"  {a.value:10s} (folder missing)")

    # Build a combined training table across equities. For full training, drop
    # `symbols_per_asset`, set stride=1, and add the other assets.
    print("\nBuilding training dataset (stride=3 for the demo)...")
    ds = build_dataset(
        repo,
        assets=[Asset.STOCK, Asset.INDEX, Asset.COMMODITY],
        symbols_per_asset=None,
        stride=3,
        warmup=210,
        horizons=(3, 5, 10, 15),
        stop_atr_mult=1.5,
        target_atr_mult=3.0,
    )
    print("dataset shape:", ds.shape,
          "| symbols:", ds.index.get_level_values("symbol").nunique())

    X, y, cols = feature_label_split(ds, label="label_bin")
    print("features:", len(cols), "| samples:", len(X),
          "| positive rate:", round(float(y.mean()), 3))

    try:
        from sklearn.ensemble import GradientBoostingClassifier
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import roc_auc_score, accuracy_score
        import joblib
    except ImportError:
        print("\nInstall scikit-learn + joblib to train: "
              "pip install scikit-learn joblib")
        return

    # Time-ordered split (no shuffle) — respect temporal causality.
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.3, shuffle=False)
    model = GradientBoostingClassifier(random_state=0).fit(Xtr, ytr)
    proba = model.predict_proba(Xte)[:, 1]
    print("\ntest accuracy:", round(accuracy_score(yte, proba > 0.5), 3))
    try:
        print("test AUC     :", round(roc_auc_score(yte, proba), 3))
    except ValueError:
        print("test AUC     : n/a (single class in test fold)")

    top = sorted(zip(cols, model.feature_importances_), key=lambda t: -t[1])[:8]
    print("top features :")
    for name, imp in top:
        print(f"   {name:34s} {imp:.3f}")

    joblib.dump({"model": model, "features": cols}, "swing_model.joblib")
    print("\nsaved -> swing_model.joblib")
    print("NOTE: synthetic/random data has no edge — real metrics need your data.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "raw_data")
