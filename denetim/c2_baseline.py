"""C2: independent monthly-buy arithmetic, then project-function comparison."""

import json
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
settings = json.loads((ROOT / "ayarlar.json").read_text(encoding="utf-8"))
monthly = float(settings["aylik_tutar"])
commission = float(settings["komisyon"])
slippage = float(settings["kayma"])


def independent(path: Path) -> tuple[float, float, int, str]:
    df = pd.read_csv(path, dtype={"tarih": str})
    months = df["tarih"].str[:7]
    first = months.ne(months.shift(1))
    buys = df.loc[first, "acilis"].astype(float)
    coin = float((monthly * (1 - commission) / (buys * (1 + slippage))).sum())
    value = coin * float(df.iloc[-1]["kapanis"])
    return coin, value, int(first.sum()), str(df.iloc[-1]["tarih"])


independent_results = {}
for coin, symbol in settings["coinler"].items():
    independent_results[coin] = independent(ROOT / "veri" / f"{symbol}_1d.csv")

# Project comparison is deliberately after, and separate from, the independent arithmetic.
from kripto_sinyal.simulasyon import Maliyet, Seri, dca  # noqa: E402

m = Maliyet(monthly, commission, slippage)
all_ok = True
for coin, symbol in settings["coinler"].items():
    df = pd.read_csv(ROOT / "veri" / f"{symbol}_1d.csv", dtype={"tarih": str})
    project_coin, project_value = dca(Seri.tablodan(df), m)
    icoin, ivalue, buys, last_date = independent_results[coin]
    pcoin, pvalue = float(project_coin[-1]), float(project_value[-1])
    coin_rel = abs(icoin - pcoin) / max(abs(icoin), abs(pcoin))
    value_rel = abs(ivalue - pvalue) / max(abs(ivalue), abs(pvalue))
    ok = coin_rel <= 1e-6 and value_rel <= 1e-6
    all_ok &= ok
    print(
        f"{coin} buys={buys} last={last_date} "
        f"ind_coin={icoin:.15g} project_coin={pcoin:.15g} coin_rel={coin_rel:.3e} "
        f"ind_value={ivalue:.15g} project_value={pvalue:.15g} value_rel={value_rel:.3e} "
        f"same={ok}"
    )
print(f"C2_PASS={all_ok}")
