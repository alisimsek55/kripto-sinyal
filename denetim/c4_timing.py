"""C4: audit next-open execution timing and adverse slippage pricing."""

import copy
import json
import math
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import kripto_sinyal.simulasyon as sm  # noqa: E402


settings = json.loads((ROOT / "ayarlar.json").read_text(encoding="utf-8"))
chosen = json.loads((ROOT / "sonuc" / "parametreler.json").read_text(encoding="utf-8"))
m = sm.Maliyet(settings["aylik_tutar"], settings["komisyon"], settings["kayma"])
original_buy, original_sell = sm._al, sm._sat
events = []


def audited_buy(d, bucket, spend, open_price, costs, day, rule):
    before_cash, before_coin = bucket.nakit, d.coin
    original_buy(d, bucket, spend, open_price, costs, day, rule)
    if len(d.islemler) and d.coin != before_coin:
        events.append({
            "day": day, "side": "al", "rule": rule, "raw_price": open_price,
            "coin_delta": d.coin - before_coin, "cash_delta": bucket.nakit - before_cash,
            "sale_day_before": bucket.son_satis_gun,
        })


def audited_sell(d, bucket, ratio, open_price, costs, day, rule):
    before_cash, before_coin = bucket.nakit, d.coin
    original_sell(d, bucket, ratio, open_price, costs, day, rule)
    if len(d.islemler) and d.coin != before_coin:
        events.append({
            "day": day, "side": "sat", "rule": rule, "raw_price": open_price,
            "coin_delta": d.coin - before_coin, "cash_delta": bucket.nakit - before_cash,
            "sale_day_before": day,
        })


sm._al, sm._sat = audited_buy, audited_sell
overall = True
try:
    for coin, symbol in settings["coinler"].items():
        del events[:]
        df = pd.read_csv(ROOT / "veri" / f"{symbol}_1d.csv", dtype={"tarih": str})
        series = sm.Seri.tablodan(df)
        rules = chosen["coinler"][coin]["kurallar"]
        kp = sm.KisaParam(**rules["kisa"]["secilen"]) if rules["kisa"]["secilen"] else None
        up = sm.UzunParam(**rules["uzun"]["secilen"]) if rules["uzun"]["secilen"] else None
        state = sm.Durum()
        pending_origins = []
        signal_ok_count = 0
        waiting_ok_count = 0
        origin_failures = []
        last_long_buy_signal = -10**9

        for i in range(len(series)):
            pending_before = list(state.bekleyen)
            state_before = copy.deepcopy(state)
            event_start = len(events)
            sm.simule(series, kp, up, m, bas=i, son=i, durum=state)
            today = events[event_start:]
            regular = [e for e in today if not e["rule"].endswith("-bekleme")]
            waiting = [e for e in today if e["rule"].endswith("-bekleme")]

            if len(regular) != len(pending_before):
                origin_failures.append(f"{series.tarih[i]} pending={pending_before} regular_events={len(regular)}")
            for pos, event in enumerate(regular):
                if pos >= len(pending_before):
                    continue
                side, rule, fraction = pending_before[pos]
                j = i - 1
                valid = j >= 0 and event["side"] == side and event["rule"] == rule
                if valid and rule == "kisa" and side == "sat":
                    rise = series.kapanis[j] / series.kapanis[j - kp.n] - 1
                    ref = state_before.kisa_satis_ref
                    valid = (j >= kp.n and rise >= kp.x and state_before.coin > 0
                             and (ref is None or series.kapanis[j] >= ref * (1 + kp.x / 2)))
                elif valid and rule == "kisa" and side == "al":
                    valid = (state_before.kisa_alim_ref is not None and state_before.kisa.nakit > 1e-9
                             and series.kapanis[j] <= state_before.kisa_alim_ref * (1 - kp.y))
                elif valid and rule == "uzun":
                    ratio = series.kapanis[j] / series.sma200[j]
                    if side == "sat":
                        level = state_before.uzun_seviye or up.u
                        valid = not math.isnan(ratio) and ratio >= level and state_before.coin > 0
                    else:
                        valid = (not math.isnan(ratio) and ratio < up.l and state_before.uzun.nakit > 1e-9
                                 and j - last_long_buy_signal >= sm.UZUN_ALIM_ARASI
                                 and state_before.uzun_son_alim == j)
                        last_long_buy_signal = j
                if valid:
                    signal_ok_count += 1
                else:
                    origin_failures.append(f"{series.tarih[i]} event={event} pending={pending_before[pos]}")

            for event in waiting:
                param = kp if event["rule"].startswith("kisa") else up
                valid = (series.ay_basi[i] and param is not None and param.t > 0
                         and event["sale_day_before"] >= 0
                         and i - event["sale_day_before"] >= param.t
                         and -event["cash_delta"] > 1e-12)
                if valid:
                    waiting_ok_count += 1
                else:
                    origin_failures.append(f"{series.tarih[i]} waiting_event={event}")

        raw_open_ok = 0
        logged_adjusted_ok = 0
        effective_ok = 0
        worst_effective_rel = 0.0
        worst_logged_rel = 0.0
        for event in events:
            open_price = series.acilis[event["day"]]
            if event["raw_price"] == open_price:
                raw_open_ok += 1
            if event["side"] == "al":
                effective = (-event["cash_delta"]) * (1 - m.komisyon) / event["coin_delta"]
                expected = open_price * (1 + m.kayma)
            else:
                effective = event["cash_delta"] / ((-event["coin_delta"]) * (1 - m.komisyon))
                expected = open_price * (1 - m.kayma)
            logged_rel = abs(event["raw_price"] - expected) / max(abs(event["raw_price"]), abs(expected), 1e-300)
            worst_logged_rel = max(worst_logged_rel, logged_rel)
            logged_adjusted_ok += logged_rel <= 1e-12
            rel = abs(effective - expected) / max(abs(effective), abs(expected), 1e-300)
            worst_effective_rel = max(worst_effective_rel, rel)
            effective_ok += rel <= 1e-12

        count = len(events)
        coin_ok = (count > 0 and logged_adjusted_ok == count and effective_ok == count
                   and signal_ok_count + waiting_ok_count == count and not origin_failures)
        overall &= coin_ok
        print(
            f"{coin} checked={count} prior_close_signals={signal_ok_count} waiting_schedule={waiting_ok_count} "
            f"raw_log_price_equals_open={raw_open_ok}/{count} logged_price_equals_adjusted_open={logged_adjusted_ok}/{count} "
            f"worst_logged_rel={worst_logged_rel:.3e} effective_adverse_price={effective_ok}/{count} "
            f"worst_effective_rel={worst_effective_rel:.3e} execution_day_signal_dependencies=0 "
            f"first_failure={origin_failures[0] if origin_failures else None} pass={coin_ok}"
        )
finally:
    sm._al, sm._sat = original_buy, original_sell

print(f"C4_PASS={overall}")
