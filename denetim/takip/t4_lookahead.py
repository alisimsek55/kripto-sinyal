"""T4: D sonrasini boz; D'ye kadarki karar ve durumun ayniligini olc."""
import json
import random
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from kripto_sinyal.arama import alim_zincir, tum_veri_secimi, zincir
from kripto_sinyal.simulasyon import Maliyet, Seri
from kripto_sinyal.takip import _katlar, _yillik_secimler

START = "2025-03-15"
CUTOFF = "2025-09-01"
COINS = {"DOGE": "DOGEUSDT", "BTC": "BTCUSDT"}
M = Maliyet(100.0, 0.001, 0.0005)


def normalize(value):
    if is_dataclass(value):
        return normalize(asdict(value))
    if isinstance(value, dict):
        return {k: normalize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize(v) for v in value]
    if isinstance(value, float):
        return round(value, 13)
    return value


def run(frame, initial):
    seri = Seri.tablodan(frame)
    stages = _katlar(seri, START)
    selections = _yillik_secimler(frame, seri, stages, initial, M)
    none = [None] * len(stages)
    return seri, {
        "kisa": zincir(seri, stages, selections["kisa"], none, M, initial["coin"], True),
        "uzun": zincir(seri, stages, none, selections["uzun"], M, initial["coin"], True),
        "alim": alim_zincir(seri, stages, selections["alim"], M, initial["coin"], True),
    }


def prefix(seri, result, rule):
    state = result["_durum"]
    if rule == "alim":
        decisions = [(seri.tarih[i], zone, amount) for i, zone, amount in state.kararlar
                     if seri.tarih[i] <= CUTOFF]
        trades = [x for x in state.islemler if seri.tarih[x[0]] <= CUTOFF]
        return normalize((decisions, trades))
    trades = [x for x in state.islemler if seri.tarih[x[0]] <= CUTOFF]
    return normalize(trades)


def main():
    rng = random.Random(20250901)
    compared = 0
    mismatches = []
    perturbed_rows = 0
    state_checks = 0
    for coin, symbol in COINS.items():
        original = pd.read_csv(ROOT / "veri" / f"{symbol}_1d.csv")
        altered = original.copy(deep=True)
        mask = altered["tarih"].astype(str) > CUTOFF
        for idx in altered.index[mask]:
            factor = rng.uniform(0.5, 2.0)
            altered.loc[idx, ["acilis", "yuksek", "dusuk", "kapanis"]] *= factor
            perturbed_rows += 1
        training = original[original["tarih"].astype(str) <= START].reset_index(drop=True)
        selections = tum_veri_secimi(Seri.tablodan(training), M)
        # Starting coin is recomputed through the public baseline convention.
        from kripto_sinyal.simulasyon import dca
        initial_coin = float(dca(Seri.tablodan(training), M)[0][-1])
        initial = {**selections, "coin": initial_coin}
        s1, r1 = run(original, initial)
        s2, r2 = run(altered, initial)
        for rule in ("kisa", "uzun", "alim"):
            left, right = prefix(s1, r1[rule], rule), prefix(s2, r2[rule], rule)
            compared += len(left[0]) + len(left[1]) if rule == "alim" else len(left)
            if left != right:
                mismatches.append((coin, rule, "decisions"))
        # State exactly at D: run the same project path on frames physically ending at D.
        c1 = original[original["tarih"].astype(str) <= CUTOFF].reset_index(drop=True)
        c2 = altered[altered["tarih"].astype(str) <= CUTOFF].reset_index(drop=True)
        cs1, cr1 = run(c1, initial)
        cs2, cr2 = run(c2, initial)
        for rule in ("kisa", "uzun", "alim"):
            state_checks += 1
            if normalize(cr1[rule]["_durum"]) != normalize(cr2[rule]["_durum"]):
                mismatches.append((coin, rule, "state"))
    passed = not mismatches
    print(json.dumps({"test": "T4", "pass": passed, "decisions_compared": compared,
                      "state_checks": state_checks, "perturbed_rows": perturbed_rows,
                      "mismatches": len(mismatches), "details": mismatches}, ensure_ascii=False))
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
