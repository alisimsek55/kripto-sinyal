"""C3: perturb all observations after cut dates and compare causal history."""

import json
import math
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kripto_sinyal.simulasyon import KisaParam, Maliyet, Seri, UzunParam, simule  # noqa: E402


def rel_equal(a, b, tol=1e-12):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if isinstance(a, float) and math.isnan(a):
            return isinstance(b, float) and math.isnan(b)
        return abs(a - b) <= tol * max(abs(a), abs(b), 1e-300)
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(rel_equal(a[k], b[k], tol) for k in a)
    if isinstance(a, (list, tuple)):
        return len(a) == len(b) and all(rel_equal(x, y, tol) for x, y in zip(a, b))
    return a == b


def state_without_log(d):
    raw = asdict(d)
    raw.pop("islemler")
    return raw


settings = json.loads((ROOT / "ayarlar.json").read_text(encoding="utf-8"))
chosen = json.loads((ROOT / "sonuc" / "parametreler.json").read_text(encoding="utf-8"))
m = Maliyet(settings["aylik_tutar"], settings["komisyon"], settings["kayma"])
cuts = ["2021-03-01", "2023-06-01", "2025-01-01"]
saved = {"settings": settings, "coins": {}}
overall = True

for coin_no, (coin, symbol) in enumerate(settings["coinler"].items()):
    df = pd.read_csv(ROOT / "veri" / f"{symbol}_1d.csv", dtype={"tarih": str})
    rules = chosen["coinler"][coin]["kurallar"]
    kp = KisaParam(**rules["kisa"]["secilen"]) if rules["kisa"]["secilen"] else None
    up = UzunParam(**rules["uzun"]["secilen"]) if rules["uzun"]["secilen"] else None
    real_series = Seri.tablodan(df)
    real_final, _ = simule(real_series, kp, up, m)
    saved["coins"][coin] = {
        "symbol": symbol,
        "kisa": None if kp is None else asdict(kp),
        "uzun": None if up is None else asdict(up),
        "trades": [
            {"date": real_series.tarih[i], "side": side, "rule": rule, "price": price, "coin_amount": amount}
            for i, side, rule, price, amount in real_final.islemler
        ],
    }
    print(f"{coin} params kisa={None if kp is None else asdict(kp)} uzun={None if up is None else asdict(up)} total_trades={len(real_final.islemler)}")

    for cut_no, cut in enumerate(cuts):
        future = df["tarih"] > cut
        perturbed = df.copy()
        rng = np.random.default_rng(20261115 + coin_no * 100 + cut_no)
        cols = ["acilis", "yuksek", "dusuk", "kapanis"]
        factors = rng.uniform(0.5, 2.0, size=(int(future.sum()), len(cols)))
        perturbed.loc[future, cols] = perturbed.loc[future, cols].astype(float).to_numpy() * factors
        altered_series = Seri.tablodan(perturbed)
        altered_final, _ = simule(altered_series, kp, up, m)

        real_before = [t for t in real_final.islemler if real_series.tarih[t[0]] <= cut]
        altered_before = [t for t in altered_final.islemler if altered_series.tarih[t[0]] <= cut]
        first_mismatch = None
        for j in range(max(len(real_before), len(altered_before))):
            if j >= len(real_before) or j >= len(altered_before):
                first_mismatch = f"length at index {j}: real={len(real_before)} altered={len(altered_before)}"
                break
            rt, at = real_before[j], altered_before[j]
            rview = (real_series.tarih[rt[0]], *rt[1:])
            aview = (altered_series.tarih[at[0]], *at[1:])
            if not rel_equal(rview, aview):
                first_mismatch = f"index {j}: real={rview!r} altered={aview!r}"
                break

        cut_idx = int(df.index[df["tarih"] <= cut][-1])
        real_cut, _ = simule(real_series, kp, up, m, son=cut_idx)
        altered_cut, _ = simule(altered_series, kp, up, m, son=cut_idx)
        state_same = rel_equal(state_without_log(real_cut), state_without_log(altered_cut))
        trades_same = first_mismatch is None
        ok = trades_same and state_same
        overall &= ok
        print(
            f"{coin} cut={cut} compared={min(len(real_before), len(altered_before))} "
            f"real_count={len(real_before)} altered_count={len(altered_before)} "
            f"trades_same={trades_same} state_same={state_same} first_mismatch={first_mismatch} pass={ok}"
        )

(ROOT / "denetim" / "c3_trade_logs.json").write_text(
    json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(f"C3_PASS={overall}")
