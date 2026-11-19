"""C6: rerun selection on physically truncated data for every walk-forward fold."""

import json
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dataclasses import asdict  # noqa: E402

from kripto_sinyal.arama import (KISA_EKSEN, UZUN_EKSEN, izgara,  # noqa: E402
                                  izgara_degerleri, sec)
from kripto_sinyal.simulasyon import KisaParam, Maliyet, Seri, UzunParam, dca  # noqa: E402


def short_param(p):
    if p is None:
        return "kapali"
    if "n" in p:
        return f"n{p['n']}/x{p['x']:g}/s{p['s']:g}/y{p['y']:g}/b{p['b']:g}/t{p['t']}"
    return f"u{p['u']:g}/sl{p['sl']:g}/l{p['l']:g}/bl{p['bl']:g}/t{p['t']}"


settings = json.loads((ROOT / "ayarlar.json").read_text(encoding="utf-8"))
chain = json.loads((ROOT / "sonuc" / "parametreler.json").read_text(encoding="utf-8"))
m = Maliyet(settings["aylik_tutar"], settings["komisyon"], settings["kayma"])
rows = []

for coin, symbol in settings["coinler"].items():
    full = pd.read_csv(ROOT / "veri" / f"{symbol}_1d.csv", dtype={"tarih": str})
    short_folds = chain["coinler"][coin]["kurallar"]["kisa"]["kat_secimleri"]
    long_folds = chain["coinler"][coin]["kurallar"]["uzun"]["kat_secimleri"]
    by_year_short = {row["yil"]: row["kisa"] for row in short_folds}
    by_year_long = {row["yil"]: row["uzun"] for row in long_folds}
    for year in sorted(by_year_short):
        cutoff = f"{year - 1}-12-31"
        truncated = full.loc[full["tarih"] <= cutoff].reset_index(drop=True)
        truncated_series = Seri.tablodan(truncated)
        _, baseline_value = dca(truncated_series, m)
        for rule, used_map, axes, cls in (
            ("kisa", by_year_short, KISA_EKSEN, KisaParam),
            ("uzun", by_year_long, UZUN_EKSEN, UzunParam),
        ):
            used = used_map[year]
            params, neighbors = izgara(axes, cls)
            values = izgara_degerleri(truncated_series, params, rule, m)
            selected_obj = sec(values, baseline_value, neighbors, len(truncated_series) - 1, params)[0]
            selected = None if selected_obj is None else asdict(selected_obj)
            same = used == selected
            rows.append((coin, rule, year, used, selected, same, len(truncated)))
            print(
                f"{coin}|{rule}|{year}|used={short_param(used)}|truncated={short_param(selected)}|"
                f"same={same}|train_rows={len(truncated)}|last={truncated.iloc[-1]['tarih']}"
            )

same_count = sum(row[5] for row in rows)
print(f"C6_SUMMARY same={same_count}/{len(rows)}")
print(f"C6_PASS={same_count == len(rows)}")
