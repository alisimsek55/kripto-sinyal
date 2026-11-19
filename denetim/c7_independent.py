"""C7: independent DOGE short-rule implementation and project comparison."""

import json
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
settings = json.loads((ROOT / "ayarlar.json").read_text(encoding="utf-8"))
result = json.loads((ROOT / "sonuc" / "parametreler.json").read_text(encoding="utf-8"))
param = result["coinler"]["DOGE"]["kurallar"]["kisa"]["secilen"]
df = pd.read_csv(ROOT / "veri" / "DOGEUSDT_1d.csv", dtype={"tarih": str})

monthly = float(settings["aylik_tutar"])
fee = float(settings["komisyon"])
slip = float(settings["kayma"])
n, x, sell_part = param["n"], param["x"], param["s"]
drop, buy_part, timeout = param["y"], param["b"], param["t"]


def bought_coin(spend, market_open):
    return spend * (1 - fee) / (market_open * (1 + slip))


def sale_cash(amount, market_open):
    return amount * market_open * (1 - slip) * (1 - fee)


opens = df["acilis"].astype(float).tolist()
closes = df["kapanis"].astype(float).tolist()
dates = df["tarih"].tolist()
month_first = [i == 0 or dates[i][:7] != dates[i - 1][:7] for i in range(len(df))]

# Independent state machine, written without importing project code.
coin = 0.0
cash = 0.0
last_sale_day = -1
installments_left = 0
sale_ladder_reference = None
dip_reference = None
next_order = None
independent_trades = []
independent_states = []

for day, (market_open, close) in enumerate(zip(opens, closes)):
    actions = []
    if next_order == "sat":
        amount = coin * sell_part
        coin -= amount
        cash += sale_cash(amount, market_open)
        last_sale_day = day
        installments_left = 0
        sale_ladder_reference = market_open
        dip_reference = market_open
        independent_trades.append((dates[day], "sat", market_open, amount))
        actions.append("signal-sell")
    elif next_order == "al":
        spend = cash * buy_part
        cash -= spend
        amount = bought_coin(spend, market_open)
        coin += amount
        dip_reference = market_open
        sale_ladder_reference = None
        independent_trades.append((dates[day], "al", market_open, amount))
        actions.append("signal-buy")
    next_order = None

    if month_first[day]:
        coin += bought_coin(monthly, market_open)
        actions.append("monthly-buy")
        timed_out = (timeout > 0 and cash > 1e-9 and last_sale_day >= 0
                     and day - last_sale_day >= timeout)
        if timed_out:
            if installments_left == 0:
                installments_left = 3
            spend = cash / installments_left
            cash -= spend
            amount = bought_coin(spend, market_open)
            coin += amount
            installments_left -= 1
            independent_trades.append((dates[day], "al-bekleme", market_open, amount))
            actions.append("timeout-buy")
            if installments_left == 0:
                if cash < 1e-9:
                    cash = 0.0
                sale_ladder_reference = None
                dip_reference = None

    if day >= n:
        rise = close / closes[day - n] - 1
        ladder_clear = (sale_ladder_reference is None
                        or close >= sale_ladder_reference * (1 + x / 2))
        if rise >= x and coin > 0 and ladder_clear:
            next_order = "sat"
        elif dip_reference is not None and cash > 1e-9 and close <= dip_reference * (1 - drop):
            next_order = "al"

    independent_states.append({
        "coin": coin, "cash": cash, "sale_ref": sale_ladder_reference,
        "buy_ref": dip_reference, "pending": next_order, "actions": actions,
    })

baseline_coin = sum(bought_coin(monthly, opens[i]) for i in range(len(df)) if month_first[i])
last_close = closes[-1]
independent_value = coin * last_close + cash
independent_baseline_value = baseline_coin * last_close
independent_ratio = independent_value / independent_baseline_value

# Only now import the project implementation for the comparison side.
sys.path.insert(0, str(ROOT))
from kripto_sinyal.simulasyon import Durum, KisaParam, Maliyet, Seri, dca, simule  # noqa: E402

series = Seri.tablodan(df)
costs = Maliyet(monthly, fee, slip)
project_state = Durum()
project_states = []
project_trade_count_before = 0
for day in range(len(series)):
    simule(series, KisaParam(**param), None, costs, bas=day, son=day, durum=project_state)
    day_trades = project_state.islemler[project_trade_count_before:]
    project_trade_count_before = len(project_state.islemler)
    project_states.append({
        "coin": project_state.coin,
        "cash": project_state.kisa.nakit,
        "sale_ref": project_state.kisa_satis_ref,
        "buy_ref": project_state.kisa_alim_ref,
        "pending": None if not project_state.bekleyen else project_state.bekleyen[0][0],
        "actions": [(side, rule, price, amount) for _, side, rule, price, amount in day_trades],
    })

_, project_baseline = dca(series, costs)
project_value = project_state.coin * last_close + project_state.nakit()
project_ratio = project_value / float(project_baseline[-1])
relative_ratio_difference = abs(independent_ratio - project_ratio) / abs(project_ratio)

first_divergence = None
for day, (mine, theirs) in enumerate(zip(independent_states, project_states)):
    def close_enough(a, b):
        if a is None or b is None:
            return a is b
        return abs(a - b) <= 1e-12 * max(abs(a), abs(b), 1e-300)

    if not all(close_enough(mine[key], theirs[key]) for key in ("coin", "cash", "sale_ref", "buy_ref")) or mine["pending"] != theirs["pending"]:
        first_divergence = {
            "date": dates[day], "independent": mine, "project": theirs,
        }
        break

passed = relative_ratio_difference <= 0.01
print(f"DOGE params={param} days={len(df)} monthly_buys={sum(month_first)}")
print(
    f"independent strategy_value={independent_value:.15g} baseline_value={independent_baseline_value:.15g} "
    f"ratio={independent_ratio:.15g} trades={len(independent_trades)}"
)
print(
    f"project strategy_value={project_value:.15g} baseline_value={float(project_baseline[-1]):.15g} "
    f"ratio={project_ratio:.15g} trades={len(project_state.islemler)}"
)
print(f"ratio_relative_difference={relative_ratio_difference:.3e} first_divergence={first_divergence}")
print(f"C7_PASS={passed}")
