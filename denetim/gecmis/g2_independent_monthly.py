"""G2: independent result-3 audit; prints aggregates and boundary buy dates."""
from datetime import datetime, timezone
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
REL = 1e-9


def prices(base):
    today = datetime.now(timezone.utc).date().isoformat()
    df = pd.read_csv(ROOT / "veri" / f"{base}USDT_1d.csv", dtype={"tarih": str})
    return df[df["tarih"] < today].sort_values("tarih").reset_index(drop=True)


from kripto_sinyal.gecmis import csvleri_oku, defteri_hesapla, sonuclari_hesapla
from kripto_sinyal.simulasyon import Maliyet

cfg = json.loads((ROOT / "ayarlar.json").read_text(encoding="utf-8"))
m = Maliyet(cfg["aylik_tutar"], cfg["komisyon"], cfg["kayma"])
rows = csvleri_oku(ROOT / "gecmis")
all_ok = True
for base in sorted({x.base for x in rows if x.quote == "USDT"}):
    d = defteri_hesapla(rows, base)
    table = prices(base)
    final_date = str(table.iloc[-1]["tarih"])
    n = (int(final_date[:4]) - d.ilk.year) * 12 + int(final_date[5:7]) - d.ilk.month + 1
    part = d.giren / n
    months = pd.period_range(d.ilk.strftime("%Y-%m"), final_date[:7], freq="M")
    dates, coin = [], d.onceki_coin
    first_day = d.ilk.strftime("%Y-%m-%d")
    for index, month in enumerate(months):
        eligible = table[table["tarih"].str.startswith(str(month))]
        if index == 0:
            eligible = eligible[eligible["tarih"] >= first_day]
        candle = eligible.iloc[0]
        dates.append(str(candle["tarih"]))
        coin += part * (1.0 - cfg["komisyon"]) / (float(candle["acilis"]) * (1.0 + cfg["kayma"]))
    project = sonuclari_hesapla(d, table, m)
    diff = abs(coin - project.aylik.coin)
    passed = n == project.ay_sayisi and dates == project.aylik_alim_tarihleri and (
        diff <= REL * max(1.0, abs(coin), abs(project.aylik.coin)))
    all_ok &= passed
    print(f"{base} n={n} monthly_amount={part:.12g} first={dates[0]} last={dates[-1]}")
    print(f"{base} independent_coin={coin:.12g} project_coin={project.aylik.coin:.12g} abs_diff={diff:.12g}")
print("G2", "PASS" if all_ok else "FAIL")

