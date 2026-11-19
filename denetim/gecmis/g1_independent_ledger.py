"""G1: independent ledger/result 1/result 2 audit; prints aggregates only."""
import csv
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
NUM_ASSET = re.compile(r"^([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)([A-Za-z0-9]+)$")
REL = 1e-9


def amount(text):
    m = NUM_ASSET.fullmatch(text.strip())
    if not m:
        raise ValueError("unreadable numeric asset field")
    return float(m.group(1)), m.group(2).upper()


def read_rows():
    out = []
    for path in sorted((ROOT / "gecmis").glob("*.csv")):
        with path.open(encoding="utf-8-sig", newline="") as fh:
            for pos, row in enumerate(csv.DictReader(fh)):
                executed, base = amount(row["Executed"])
                quote_amount, quote = amount(row["Amount"])
                fee, fee_asset = amount(row["Fee"])
                out.append({"time": datetime.strptime(row["Date(UTC)"], "%Y-%m-%d %H:%M:%S"),
                            "pair": row["Pair"].upper(), "side": row["Side"].upper(),
                            "price": float(row["Price"]), "executed": executed, "base": base,
                            "amount": quote_amount, "quote": quote, "fee": fee,
                            "fee_asset": fee_asset, "file": path.name, "pos": pos})
    return sorted(out, key=lambda x: (x["time"], x["file"], -x["pos"]))


def close(base):
    today = datetime.now(timezone.utc).date().isoformat()
    df = pd.read_csv(ROOT / "veri" / f"{base}USDT_1d.csv", dtype={"tarih": str})
    return float(df[df["tarih"] < today].sort_values("tarih").iloc[-1]["kapanis"])


def independent(rows, base):
    coin = cep = giren = previous = 0.0
    entries = []
    for r in (x for x in rows if x["base"] == base and x["quote"] == "USDT"):
        fee_base = r["fee"] if r["fee_asset"] == base else 0.0
        fee_quote = r["fee"] if r["fee_asset"] == "USDT" else 0.0
        if r["side"] == "SELL":
            debit = r["executed"] + fee_base
            previous += max(0.0, debit - coin)
            coin = max(0.0, coin - debit)
            cep += r["amount"] - fee_quote
        else:
            cost = r["amount"] + fee_quote
            from_pocket = min(cep, cost)
            outside = cost - from_pocket
            cep -= from_pocket
            coin += r["executed"] - fee_base
            if outside > 1e-12:
                giren += outside
                fee_fraction = fee_base / r["executed"] if fee_base else (
                    r["fee"] / r["amount"] if r["amount"] else 0.0)
                entries.append(outside / r["price"] * (1.0 - fee_fraction))
    p = close(base)
    hold_coin = previous + sum(entries)
    return giren, coin, cep, previous, coin * p + cep, hold_coin


def ok(a, b):
    return abs(a - b) <= REL * max(1.0, abs(a), abs(b))


rows = read_rows()
from kripto_sinyal.gecmis import csvleri_oku, defteri_hesapla, sonuclari_hesapla
from kripto_sinyal.simulasyon import Maliyet
project_rows = csvleri_oku(ROOT / "gecmis")
all_ok = True
for base in sorted({r["base"] for r in rows if r["quote"] == "USDT"}):
    own = independent(rows, base)
    d = defteri_hesapla(project_rows, base)
    p = close(base)
    table = pd.read_csv(ROOT / "veri" / f"{base}USDT_1d.csv", dtype={"tarih": str})
    today = datetime.now(timezone.utc).date().isoformat()
    a = sonuclari_hesapla(d, table[table["tarih"] < today], Maliyet())
    project = (d.giren, d.coin, d.cep, d.onceki_coin, a.gercek.deger, a.satmadan.coin)
    diffs = [abs(a - b) for a, b in zip(own, project)]
    passed = all(ok(a, b) for a, b in zip(own, project))
    all_ok &= passed
    print(f"{base} giren={own[0]:.12g} coin={own[1]:.12g} cep={own[2]:.12g} onceki={own[3]:.12g}")
    print(f"{base} result1_value={own[4]:.12g} result2_coin={own[5]:.12g} max_abs_diff={max(diffs):.12g}")
print("G1", "PASS" if all_ok else "FAIL")

