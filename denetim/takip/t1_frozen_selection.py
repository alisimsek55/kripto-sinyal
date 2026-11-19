"""T1: CLI kaydındaki donmus secimleri fiziksel kesilmis veriyle karsilastir."""
import json
import tempfile
import shutil
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from kripto_sinyal.arama import tum_veri_secimi
from kripto_sinyal.simulasyon import Maliyet, Seri

PYTHON = Path(sys.executable)
SCRATCH = Path(tempfile.gettempdir()) / "kripto-sinyal-denetim-takip"
STARTS = ("2024-06-30", "2025-03-15", "2026-05-15")
COINS = {"DOGE": "DOGEUSDT", "BTC": "BTCUSDT"}


def pdict(value):
    return None if value is None else asdict(value)


def main():
    SCRATCH.mkdir(parents=True, exist_ok=True)
    command_runs = 0
    for start in STARTS:
        target = SCRATCH / ("t" + start)
        if target.exists():
            shutil.rmtree(target)
        for command in ("takip-baslat", "karne"):
            args = [str(PYTHON), "-m", "kripto_sinyal", command, "--klasor", str(target)]
            if command == "takip-baslat":
                args += ["--tarih", start]
            completed = subprocess.run(args, cwd=ROOT, text=True, capture_output=True)
            command_runs += 1
            if completed.returncode:
                raise RuntimeError(f"{command} {start} rc={completed.returncode}\n{completed.stdout}\n{completed.stderr}")

    comparisons = 0
    mismatches = []
    for start in STARTS:
        saved = json.loads((SCRATCH / ("t" + start) / "baslangic.json").read_text(encoding="utf-8"))
        m = Maliyet(**{"aylik": saved["ayarlar"]["aylik_tutar"],
                       "komisyon": saved["ayarlar"]["komisyon"],
                       "kayma": saved["ayarlar"]["kayma"]})
        for coin, symbol in COINS.items():
            frame = pd.read_csv(ROOT / "veri" / f"{symbol}_1d.csv")
            truncated = frame[frame["tarih"].astype(str) <= start].reset_index(drop=True).copy()
            # The selector physically receives no rows after S.
            selected = tum_veri_secimi(Seri.tablodan(truncated), m)
            for rule in ("kisa", "uzun", "alim"):
                comparisons += 1
                actual, expected = saved["coinler"][coin][rule], pdict(selected[rule])
                if actual != expected:
                    mismatches.append({"start": start, "coin": coin, "rule": rule,
                                       "saved": actual, "truncated": expected})
    result = {"test": "T1", "pass": not mismatches, "comparisons": comparisons,
              "mismatches": len(mismatches), "command_runs": command_runs,
              "details": mismatches}
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result["pass"] else 1)


if __name__ == "__main__":
    main()
