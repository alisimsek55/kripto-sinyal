import copy
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from e2_independent import load
from kripto_sinyal.simulasyon import AlimParam, Maliyet, Seri, alim_simule


PARAMS = [
    {"u": 1.5, "k": 0.0, "l": 1.0, "g": 1.0, "t": 365},
    {"u": 1.25, "k": 0.0, "l": 1.0, "g": 1.0, "t": 0},
]
CUTS = ("2021-03-01", "2023-06-01", "2025-01-01")
OHLC = ["acilis", "yuksek", "dusuk", "kapanis"]


def decisions(df, p):
    seri = Seri.tablodan(df)
    d, _ = alim_simule(seri, AlimParam(**p), Maliyet())
    out, prior = [], 0.0
    for (idx, region, _), (_, invested, reserve, _) in zip(d.kararlar, d.para_gecmisi):
        out.append((seri.tarih[idx], region, invested - prior, reserve))
        prior = invested
    return out


if __name__ == "__main__":
    rng = np.random.default_rng(20261115)
    failures = []
    future_cases = 0
    candle_cases = 0
    for coin in ("DOGE", "BTC"):
        original = load(coin)
        for p in PARAMS:
            base = decisions(original, p)
            for cut in CUTS:
                changed = original.copy()
                mask = changed["tarih"] > cut
                factors = rng.uniform(0.5, 2.0, size=(int(mask.sum()), 4))
                changed.loc[mask, OHLC] = changed.loc[mask, OHLC].to_numpy() * factors
                got = decisions(changed, p)
                expected_prefix = [x for x in base if x[0] <= cut]
                got_prefix = [x for x in got if x[0] <= cut]
                future_cases += len(expected_prefix)
                if expected_prefix != got_prefix:
                    failures.append((coin, p, cut, "future", expected_prefix, got_prefix))
            monthly_indices = original.index[original["monthly"]].tolist()
            base_by_date = {x[0]: x for x in base}
            for idx in monthly_indices:
                changed = original.copy()
                changed.loc[idx, OHLC] = changed.loc[idx, OHLC].to_numpy(dtype=float) * rng.uniform(0.5, 2.0, 4)
                got = decisions(changed, p)
                day = str(original.loc[idx, "tarih"])
                actual = next(x for x in got if x[0] == day)
                expected = base_by_date[day]
                candle_cases += 1
                if actual[1:3] != expected[1:3]:
                    failures.append((coin, p, day, "buy_candle", expected, actual))
    print(f"future_decisions_compared={future_cases} buy_candles_compared={candle_cases} failures={len(failures)}")
    if failures:
        print(f"first_failure={failures[0]}")
    print(f"E4 {'PASS' if not failures else 'FAIL'}")

