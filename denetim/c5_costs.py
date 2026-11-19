"""C5: independently recompute every rule-trade and baseline-buy delta."""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import kripto_sinyal.simulasyon as sm  # noqa: E402


def relerr(actual, expected):
    return abs(actual - expected) / max(abs(actual), abs(expected), 1e-300)


settings = json.loads((ROOT / "ayarlar.json").read_text(encoding="utf-8"))
chosen = json.loads((ROOT / "sonuc" / "parametreler.json").read_text(encoding="utf-8"))
m = sm.Maliyet(settings["aylik_tutar"], settings["komisyon"], settings["kayma"])
original_buy, original_sell = sm._al, sm._sat
checks = []


def audited_buy(d, bucket, spend, open_price, costs, day, rule):
    before_cash, before_coin = bucket.nakit, d.coin
    original_buy(d, bucket, spend, open_price, costs, day, rule)
    if spend > 1e-12:
        actual_cash = bucket.nakit - before_cash
        actual_coin = d.coin - before_coin
        expected_cash = -spend
        expected_coin = spend * (1 - costs.komisyon) / (open_price * (1 + costs.kayma))
        checks.append((day, "al", rule, relerr(actual_cash, expected_cash), relerr(actual_coin, expected_coin)))


def audited_sell(d, bucket, fraction, open_price, costs, day, rule):
    before_cash, before_coin = bucket.nakit, d.coin
    original_sell(d, bucket, fraction, open_price, costs, day, rule)
    amount = before_coin * fraction
    if amount > 1e-15:
        actual_cash = bucket.nakit - before_cash
        actual_coin = d.coin - before_coin
        expected_cash = amount * open_price * (1 - costs.kayma) * (1 - costs.komisyon)
        expected_coin = -amount
        checks.append((day, "sat", rule, relerr(actual_cash, expected_cash), relerr(actual_coin, expected_coin)))


sm._al, sm._sat = audited_buy, audited_sell
overall = True
baseline_total = 0
baseline_worst = 0.0
try:
    for coin, symbol in settings["coinler"].items():
        del checks[:]
        df = pd.read_csv(ROOT / "veri" / f"{symbol}_1d.csv", dtype={"tarih": str})
        series = sm.Seri.tablodan(df)
        rules = chosen["coinler"][coin]["kurallar"]
        kp = sm.KisaParam(**rules["kisa"]["secilen"]) if rules["kisa"]["secilen"] else None
        up = sm.UzunParam(**rules["uzun"]["secilen"]) if rules["uzun"]["secilen"] else None
        sm.simule(series, kp, up, m)
        worst = max((max(x[3], x[4]) for x in checks), default=0.0)
        failures = [x for x in checks if max(x[3], x[4]) > 1e-9]
        coin_ok = not failures
        overall &= coin_ok
        print(f"{coin} rule_trades={len(checks)} worst_relative_error={worst:.3e} first_failure={failures[0] if failures else None} pass={coin_ok}")

        baseline_coin, _ = sm.dca(series, m)
        previous = 0.0
        monthly_errors = []
        for i, current in enumerate(baseline_coin):
            if series.ay_basi[i]:
                actual = float(current - previous)
                expected = m.aylik * (1 - m.komisyon) / (series.acilis[i] * (1 + m.kayma))
                monthly_errors.append(relerr(actual, expected))
            previous = float(current)
        baseline_total += len(monthly_errors)
        baseline_worst = max(baseline_worst, max(monthly_errors, default=0.0))
        print(f"{coin} baseline_monthly_buys={len(monthly_errors)} same_formula_worst_relative_error={max(monthly_errors, default=0.0):.3e}")
finally:
    sm._al, sm._sat = original_buy, original_sell

baseline_same = baseline_worst <= 1e-9
overall &= baseline_same
print(
    f"baseline_same_costs_as_strategy_monthly_buys=YES checked={baseline_total} "
    f"worst_relative_error={baseline_worst:.3e} commission={m.komisyon} slippage={m.kayma}"
)
print(f"C5_PASS={overall}")
