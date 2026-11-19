from dataclasses import asdict
import json
import sys
from pathlib import Path

ROOT_PATH = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_PATH))

from e2_independent import ROOT, load
from kripto_sinyal.arama import ALIM_EKSEN, izgara, izgara_degerleri, sec
from kripto_sinyal.simulasyon import AlimParam, Maliyet, Seri, dca


def select_truncated(df):
    seri = Seri.tablodan(df)
    params, neighbors = izgara(ALIM_EKSEN, AlimParam)
    _, base = dca(seri, Maliyet())
    values = izgara_degerleri(seri, params, "alim", Maliyet())
    chosen = sec(values, base, neighbors, len(seri) - 1, params)[0]
    return None if chosen is None else asdict(chosen)


if __name__ == "__main__":
    result = json.loads((ROOT / "sonuc/parametreler.json").read_text(encoding="utf-8"))
    rows = []
    print("coin year used truncated_run same")
    for coin in ("DOGE", "BTC"):
        df = load(coin)
        used_rows = result["coinler"][coin]["kurallar"]["alim"]["kat_secimleri"]
        for item in used_rows:
            year, used = item["yil"], item["alim"]
            truncated = df[df["tarih"] <= f"{year - 1}-12-31"].reset_index(drop=True)
            picked = select_truncated(truncated)
            same = used == picked
            rows.append(same)
            print(f"{coin} {year} {used} {picked} {same}")
    print(f"E5 {'PASS' if all(rows) else 'FAIL'} rows={len(rows)} same={sum(rows)}")

