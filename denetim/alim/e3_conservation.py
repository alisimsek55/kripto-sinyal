import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from e2_independent import load
from kripto_sinyal.simulasyon import AlimParam, Maliyet, Seri, alim_simule


PARAMS = [
    {"u": 1.5, "k": 0.0, "l": 1.0, "g": 1.0, "t": 365},
    {"u": 1.25, "k": 0.0, "l": 1.0, "g": 1.0, "t": 0},
]


if __name__ == "__main__":
    worst_all = 0.0
    for coin in ("DOGE", "BTC"):
        df = load(coin)
        seri = Seri.tablodan(df)
        for p in PARAMS:
            d, _ = alim_simule(seri, AlimParam(**p), Maliyet())
            errors = [abs(invested + reserve - contributions)
                      for _, invested, reserve, contributions in d.para_gecmisi]
            worst = max(errors, default=0.0)
            worst_all = max(worst_all, worst)
            print(f"{coin} {p} months={len(errors)} worst_abs_usdt={worst:.15g}")
    print(f"E3 {'PASS' if worst_all <= 1e-8 else 'FAIL'} worst_abs_usdt={worst_all:.15g}")

