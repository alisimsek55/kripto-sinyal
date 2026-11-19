"""T5: yil basi yeniden secimleri ve parca oranlarinin carpimini denetle."""
import json
import tempfile
import math
import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from kripto_sinyal.arama import alim_zincir, tum_veri_secimi, zincir
from kripto_sinyal.simulasyon import AlimParam, KisaParam, Maliyet, Seri, UzunParam
from kripto_sinyal.takip import _katlar, _yillik_secimler

SCRATCH = Path(tempfile.gettempdir()) / "kripto-sinyal-denetim-takip"
STARTS = ("2024-06-30", "2025-03-15")
COINS = {"DOGE": "DOGEUSDT", "BTC": "BTCUSDT"}


def pdict(value):
    return None if value is None else asdict(value)


def objects(record):
    return {"kisa": None if record["kisa"] is None else KisaParam(**record["kisa"]),
            "uzun": None if record["uzun"] is None else UzunParam(**record["uzun"]),
            "alim": None if record["alim"] is None else AlimParam(**record["alim"])}


def main():
    parameter_checks = 0
    parameter_mismatches = []
    ratio_checks = 0
    max_ratio_relative_error = 0.0
    ratio_mismatches = []
    crossings = 0
    for start in STARTS:
        base = json.loads((SCRATCH / ("t" + start) / "baslangic.json").read_text(encoding="utf-8"))
        a = base["ayarlar"]
        m = Maliyet(a["aylik_tutar"], a["komisyon"], a["kayma"])
        for coin, symbol in COINS.items():
            frame = pd.read_csv(ROOT / "veri" / f"{symbol}_1d.csv")
            seri = Seri.tablodan(frame)
            stages = _katlar(seri, start)
            initial = objects(base["coinler"][coin])
            used = _yillik_secimler(frame, seri, stages, initial, m)
            crossings += max(0, len(stages) - 1)
            for stage_index, stage in enumerate(stages[1:], 1):
                boundary = f"{stage['yil'] - 1}-12-31"
                truncated = frame[frame["tarih"].astype(str) <= boundary].reset_index(drop=True).copy()
                expected = tum_veri_secimi(Seri.tablodan(truncated), m)
                for rule in ("kisa", "uzun", "alim"):
                    parameter_checks += 1
                    if pdict(used[rule][stage_index]) != pdict(expected[rule]):
                        parameter_mismatches.append((start, coin, stage["yil"], rule))
            none = [None] * len(stages)
            baseline_coin = float(base["coinler"][coin]["baslangic_coin"])
            results = {
                "kisa": zincir(seri, stages, used["kisa"], none, m, baseline_coin, True),
                "uzun": zincir(seri, stages, none, used["uzun"], m, baseline_coin, True),
                "birlikte": zincir(seri, stages, used["kisa"], used["uzun"], m, baseline_coin, True),
                "alim": alim_zincir(seri, stages, used["alim"], m, baseline_coin, True),
            }
            for rule, result in results.items():
                product = math.prod(part["oran"] for part in result["yillar"])
                total = float(result["zincir_oran"])
                relative = abs(product - total) / max(abs(total), 1e-300)
                max_ratio_relative_error = max(max_ratio_relative_error, relative)
                ratio_checks += 1
                if relative > 1e-9:
                    ratio_mismatches.append((start, coin, rule, product, total, relative))
    passed = not parameter_mismatches and not ratio_mismatches
    print(json.dumps({"test": "T5", "pass": passed, "year_crossings": crossings,
                      "parameter_checks": parameter_checks,
                      "parameter_mismatches": len(parameter_mismatches),
                      "ratio_checks": ratio_checks,
                      "max_ratio_relative_error": max_ratio_relative_error,
                      "ratio_mismatches": len(ratio_mismatches),
                      "details": parameter_mismatches + ratio_mismatches}, ensure_ascii=False))
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
