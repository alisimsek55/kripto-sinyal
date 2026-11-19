"""T2: erken islem yok ve baslangic DCA coini bagimsiz hesapla."""
import csv
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRATCH = Path(tempfile.gettempdir()) / "kripto-sinyal-denetim-takip"
STARTS = ("2024-06-30", "2025-03-15", "2026-05-15")
COINS = {"DOGE": "DOGEUSDT", "BTC": "BTCUSDT"}


def baseline_coin(csv_path, stop, monthly, fee, slip):
    """No kripto_sinyal import: first candle of each YYYY-MM gets monthly purchase."""
    total = 0.0
    previous_month = None
    with csv_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            day = row["tarih"]
            if day > stop:
                break
            month = day[:7]
            if month != previous_month:
                total += monthly * (1.0 - fee) / (float(row["acilis"]) * (1.0 + slip))
                previous_month = month
    return total


def main():
    checked_trades = 0
    early = []
    coin_checks = 0
    max_relative_error = 0.0
    coin_errors = []
    for start in STARTS:
        folder = SCRATCH / ("t" + start)
        base = json.loads((folder / "baslangic.json").read_text(encoding="utf-8"))
        card = json.loads((folder / "karne.json").read_text(encoding="utf-8"))
        a = base["ayarlar"]
        for coin, symbol in COINS.items():
            expected = baseline_coin(ROOT / "veri" / f"{symbol}_1d.csv", start,
                                     a["aylik_tutar"], a["komisyon"], a["kayma"])
            actual = float(base["coinler"][coin]["baslangic_coin"])
            relative = abs(actual - expected) / max(abs(expected), 1e-300)
            max_relative_error = max(max_relative_error, relative)
            coin_checks += 1
            if relative > 1e-12:
                coin_errors.append((start, coin, actual, expected, relative))
            for rule, details in card["coinler"][coin]["kurallar"].items():
                for trade in details["islemler"]:
                    checked_trades += 1
                    if trade["tarih"] <= start:
                        early.append((start, coin, rule, trade["tarih"]))
    passed = not early and not coin_errors
    print(json.dumps({"test": "T2", "pass": passed, "trades_checked": checked_trades,
                      "early_trades": len(early), "coin_checks": coin_checks,
                      "max_coin_relative_error": max_relative_error,
                      "early_details": early, "coin_errors": coin_errors}, ensure_ascii=False))
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
