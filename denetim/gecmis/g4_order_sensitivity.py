"""G4: timestamp-tie reversal/shuffle sensitivity audit."""
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
REL = 1e-9

from kripto_sinyal.gecmis import csvleri_oku, defteri_hesapla, sonuclari_hesapla
from kripto_sinyal.simulasyon import Maliyet


def prices(base):
    today = datetime.now(timezone.utc).date().isoformat()
    df = pd.read_csv(ROOT / "veri" / f"{base}USDT_1d.csv", dtype={"tarih": str})
    return df[df["tarih"] < today].sort_values("tarih").reset_index(drop=True)


def transform(rows, mode):
    groups = defaultdict(list)
    for row in rows:
        groups[row.zaman].append(row)
    rng = random.Random(314159)
    out = []
    for stamp in sorted(groups):
        group = list(groups[stamp])
        if mode == "reverse":
            group.reverse()
        else:
            rng.shuffle(group)
        out.extend(group)
    return out


def signature(rows, base, m):
    d = defteri_hesapla(rows, base)
    a = sonuclari_hesapla(d, prices(base), m)
    return (a.gercek.coin, a.gercek.nakit, a.gercek.deger,
            a.satmadan.coin, a.satmadan.deger, a.aylik.coin, a.aylik.deger)


def close(a, b):
    return abs(a - b) <= REL * max(1.0, abs(a), abs(b))


cfg = json.loads((ROOT / "ayarlar.json").read_text(encoding="utf-8"))
m = Maliyet(cfg["aylik_tutar"], cfg["komisyon"], cfg["kayma"])
rows = csvleri_oku(ROOT / "gecmis")
by_stamp = defaultdict(set)
for row in rows:
    by_stamp[row.zaman].add(row.yon)
mixed = sum(len(sides) > 1 for sides in by_stamp.values())
variants = {name: transform(rows, name) for name in ("reverse", "shuffle")}
all_ok, global_max = True, 0.0
for base in sorted({x.base for x in rows if x.quote == "USDT"}):
    original = signature(rows, base, m)
    diffs = []
    for variant in variants.values():
        changed = signature(variant, base, m)
        diffs.extend(abs(a - b) for a, b in zip(original, changed))
        all_ok &= all(close(a, b) for a, b in zip(original, changed))
    global_max = max([global_max] + diffs)
    print(f"{base} variants=2 metrics_per_variant={len(original)} max_abs_diff={max(diffs):.12g}")
print(f"mixed_side_timestamps={mixed} timestamps={len(by_stamp)} global_max_abs_diff={global_max:.12g}")
print("G4", "PASS" if all_ok else "FAIL")

