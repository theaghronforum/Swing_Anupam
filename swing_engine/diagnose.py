from swing_engine import Asset
from swing_engine.data import (RawDataRepository, LoaderConfig,
                               make_labels, build_symbol_dataset)

repo = RawDataRepository(LoaderConfig(root="raw_data"))   # benchmark off for now

for a in Asset:
    try:
        syms = repo.list_symbols(a)
    except Exception as e:
        print(f"\n{a.value}: FOLDER ERROR -> {e}")
        continue
    print(f"\n{a.value}: {len(syms)} symbols -> {syms[:5]}")
    if not syms:
        continue
    try:
        ad = repo.load(a, syms[0])
        print("  loaded:", syms[0],
              "| daily rows:", len(ad.daily),
              "| columns:", list(ad.daily.columns))
        print("  date range:", ad.daily.index.min(), "->", ad.daily.index.max())
        print("  label rows:", len(make_labels(ad.daily)))
        print("  feature rows @warmup=210:", len(build_symbol_dataset(ad, stride=3, warmup=210)))
        print("  feature rows @warmup=60 :", len(build_symbol_dataset(ad, stride=3, warmup=60)))
    except Exception as e:
        import traceback; traceback.print_exc()