"""T3: DOGE kisa oranini proje kodunu iceri almayan bagimsiz simulatorle hesapla."""
import csv
import json
import tempfile
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRATCH = Path(tempfile.gettempdir()) / "kripto-sinyal-denetim-takip"
START = "2026-05-15"


def buy(amount, price, fee, slip):
    return amount * (1.0 - fee) / (price * (1.0 + slip))


def sell(amount, price, fee, slip):
    return amount * price * (1.0 - slip) * (1.0 - fee)


def main():
    folder = SCRATCH / ("t" + START)
    frozen = json.loads((folder / "baslangic.json").read_text(encoding="utf-8"))
    card = json.loads((folder / "karne.json").read_text(encoding="utf-8"))
    p = frozen["coinler"]["DOGE"]["kisa"]
    a = frozen["ayarlar"]
    monthly, fee, slip = a["aylik_tutar"], a["komisyon"], a["kayma"]
    with (ROOT / "veri" / "DOGEUSDT_1d.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    dates = [r["tarih"] for r in rows]
    opens = [float(r["acilis"]) for r in rows]
    closes = [float(r["kapanis"]) for r in rows]
    start_i = dates.index(START)
    coin = float(frozen["coinler"]["DOGE"]["baslangic_coin"])
    baseline_coin = coin
    cash = 0.0
    last_sale_day = -1
    pieces = 0
    sale_ref = None
    buy_ref = None
    pending = []
    trades = 0
    if p is not None:
        for i in range(start_i + 1, len(rows)):
            for direction, fraction in pending:
                if direction == "sat":
                    amount = coin * fraction
                    coin -= amount
                    cash += sell(amount, opens[i], fee, slip)
                    last_sale_day = i
                    pieces = 0
                    sale_ref = opens[i]
                    buy_ref = opens[i]
                else:
                    amount = cash * fraction
                    cash -= amount
                    coin += buy(amount, opens[i], fee, slip)
                    buy_ref = opens[i]
                    sale_ref = None
                trades += 1
            pending = []
            month_start = dates[i][:7] != dates[i - 1][:7]
            if month_start:
                regular = buy(monthly, opens[i], fee, slip)
                coin += regular
                baseline_coin += regular
                if cash > 1e-9 and (pieces > 0 or (p["t"] > 0 and last_sale_day >= 0 and i - last_sale_day >= p["t"])):
                    if pieces == 0:
                        pieces = 3
                    amount = cash / pieces
                    cash -= amount
                    coin += buy(amount, opens[i], fee, slip)
                    pieces -= 1
                    if pieces == 0 and cash < 1e-9:
                        cash = 0.0
                    if pieces == 0:
                        sale_ref = buy_ref = None
                    trades += 1
            if i >= p["n"]:
                rise = closes[i] / closes[i - p["n"]] - 1.0
                if rise >= p["x"] and coin > 0 and (sale_ref is None or closes[i] >= sale_ref * (1.0 + p["x"] / 2.0)):
                    pending.append(("sat", p["s"]))
                elif buy_ref is not None and cash > 1e-9 and closes[i] <= buy_ref * (1.0 - p["y"]):
                    pending.append(("al", p["b"]))
    else:
        for i in range(start_i + 1, len(rows)):
            if dates[i][:7] != dates[i - 1][:7]:
                regular = buy(monthly, opens[i], fee, slip)
                coin += regular
                baseline_coin += regular
    independent = (coin * closes[-1] + cash) / (baseline_coin * closes[-1])
    reported = float(card["coinler"]["DOGE"]["kurallar"]["kisa"]["oran"])
    relative = abs(independent - reported) / max(abs(reported), 1e-300)
    passed = relative <= 1e-6
    print(json.dumps({"test": "T3", "pass": passed, "independent_ratio": independent,
                      "reported_ratio": reported, "relative_error": relative,
                      "independent_trades": trades, "frozen_closed": p is None}, ensure_ascii=False))
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
