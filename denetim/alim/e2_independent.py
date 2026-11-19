from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
import math
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
A = 100.0
FEE = 0.001
SLIP = 0.0005


@dataclass
class State:
    coin: float = 0.0
    reserve: float = 0.0
    invested: float = 0.0
    contributions: float = 0.0
    last_spend: str | None = None
    first_reserve: str | None = None
    parts: int = 0
    decisions: list = field(default_factory=list)
    money_history: list = field(default_factory=list)


def load(symbol):
    df = pd.read_csv(ROOT / "veri" / f"{symbol}USDT_1d.csv", dtype={"tarih": str})
    close = df["kapanis"].astype(float)
    df = df.assign(
        acilis=df["acilis"].astype(float),
        kapanis=close,
        sma200=close.rolling(200).mean(),
        month=df["tarih"].str[:7],
    )
    df["monthly"] = df["month"].ne(df["month"].shift())
    return df


def buy_coin(usdt, opening):
    return usdt * (1.0 - FEE) / (opening * (1.0 + SLIP))


def baseline(df, start=0, end=None, coin=0.0):
    if end is None:
        end = len(df) - 1
    values = []
    for i in range(start, end + 1):
        row = df.iloc[i]
        if bool(row.monthly):
            coin += buy_coin(A, float(row.acilis))
        values.append(coin * float(row.kapanis))
    return coin, values


def simulate(df, param, start=0, end=None, state=None):
    """Independent implementation; no kripto_sinyal import is used here."""
    if end is None:
        end = len(df) - 1
    s = state if state is not None else State()
    values = []
    for i in range(start, end + 1):
        row = df.iloc[i]
        if bool(row.monthly):
            s.contributions += A
            region, amount = "normal", A
            if param is not None and i > 0 and not math.isnan(float(df.iloc[i - 1].sma200)):
                ratio = float(df.iloc[i - 1].kapanis) / float(df.iloc[i - 1].sma200)
                if ratio > param["u"]:
                    region = "pahali"
                    amount = param["k"] * A
                    before = s.reserve
                    s.reserve += (1.0 - param["k"]) * A
                    if before <= 1e-12 and s.reserve > 1e-12 and s.last_spend is None:
                        s.first_reserve = row.tarih
                elif ratio < param["l"]:
                    region = "ucuz"
                    spent = param["g"] * s.reserve
                    amount += spent
                    s.reserve -= spent
                    if spent > 1e-12:
                        s.last_spend = row.tarih
                        if s.reserve <= 1e-9:
                            s.reserve = 0.0
                            s.parts = 0
            if amount > 1e-12:
                s.coin += buy_coin(amount, float(row.acilis))
                s.invested += amount
            monthly_total = amount
            if s.reserve > 1e-9:
                if s.parts == 0 and param is not None and param["t"] > 0:
                    ref = s.last_spend or s.first_reserve
                    if ref is not None and (date.fromisoformat(row.tarih) - date.fromisoformat(ref)).days > param["t"]:
                        s.parts = 3
                if s.parts > 0:
                    spent = s.reserve / s.parts
                    s.reserve -= spent
                    s.coin += buy_coin(spent, float(row.acilis))
                    s.invested += spent
                    monthly_total += spent
                    s.last_spend = row.tarih
                    s.parts -= 1
                    if s.parts == 0 and s.reserve < 1e-9:
                        s.reserve = 0.0
            s.decisions.append((i, row.tarih, region, monthly_total, s.coin, s.reserve))
            s.money_history.append((i, s.invested, s.reserve, s.contributions))
        values.append(s.coin * float(row.kapanis) + s.reserve)
    return s, values


def project_result(df, p):
    from kripto_sinyal.simulasyon import AlimParam, Maliyet, Seri, alim_simule, dca
    seri = Seri.tablodan(df[["tarih", "acilis", "yuksek", "dusuk", "kapanis", "hacim"]])
    state, values = alim_simule(seri, AlimParam(**p), Maliyet())
    _, base = dca(seri, Maliyet())
    decisions = []
    prior = 0.0
    for (idx, region, _), (_, invested, reserve, _) in zip(state.kararlar, state.para_gecmisi):
        decisions.append((idx, seri.tarih[idx], region, invested - prior,
                          state.coin_gecmisi[idx], reserve))
        prior = invested
    return state, float(values[-1] / base[-1]), decisions


def compare_states(own, project):
    for a, b in zip(own.decisions, project):
        same = (abs(a[3] - b[3]) <= 1e-8 and abs(a[4] - b[4]) <= 1e-10 and
                abs(a[5] - b[5]) <= 1e-8)
        if not same:
            return a, b
    return None


if __name__ == "__main__":
    btc_p = {"u": 1.5, "k": 0.0, "l": 1.0, "g": 1.0, "t": 365}
    doge_p = {"u": 1.25, "k": 0.0, "l": 1.0, "g": 1.0, "t": 0}
    all_ok = True
    for coin, p, claim in (("BTC", btc_p, 1.008508), ("DOGE", doge_p, None)):
        df = load(coin)
        own, values = simulate(df, p)
        _, base = baseline(df)
        ratio = values[-1] / base[-1]
        _, project_ratio, project_decisions = project_result(df, p)
        target = claim if claim is not None else project_ratio
        rel = abs(ratio - target) / abs(target)
        ok = rel <= 1e-6
        all_ok &= ok
        print(f"{coin} independent={ratio:.12f} project={project_ratio:.12f} "
              f"target={target:.12f} rel_error={rel:.3e}")
        if not ok:
            mismatch = compare_states(own, project_decisions)
            print(f"first_mismatch={mismatch} specification=independent implementation")
    print(f"E2 {'PASS' if all_ok else 'FAIL'}")

