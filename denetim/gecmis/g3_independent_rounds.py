"""G3: independent sell-round FIFO audit; order numbers are never printed."""
from collections import OrderedDict
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
REL = 1e-9

from kripto_sinyal.gecmis import csvleri_oku, defteri_hesapla


def independent(rows, base):
    rounds = OrderedDict()
    queue = []
    cep = 0.0
    for r in (x for x in rows if x.base == base and x.quote == "USDT"):
        fee_base = r.fee if r.fee_asset == r.base else 0.0
        fee_quote = r.fee if r.fee_asset == r.quote else 0.0
        if r.yon == "SELL":
            if r.order_no not in rounds:
                rounds[r.order_no] = {"sold": 0.0, "bought": 0.0, "waiting": 0.0}
            z = rounds[r.order_no]
            z["sold"] += r.executed
            z["waiting"] += r.amount - fee_quote
            cep += r.amount - fee_quote
            if r.order_no not in queue:
                queue.append(r.order_no)
        else:
            cost = r.amount + fee_quote
            from_pocket = min(cep, cost)
            cep -= from_pocket
            net_coin = r.executed - fee_base
            left = from_pocket
            while left > 1e-12 and queue:
                z = rounds[queue[0]]
                used = min(left, z["waiting"])
                z["bought"] += net_coin * used / cost if cost else 0.0
                z["waiting"] -= used
                left -= used
                if z["waiting"] <= 1e-12:
                    z["waiting"] = 0.0
                    queue.pop(0)
    return list(rounds.values())


def close(a, b):
    return abs(a - b) <= REL * max(1.0, abs(a), abs(b))


rows = csvleri_oku(ROOT / "gecmis")
all_ok = True
for base in sorted({x.base for x in rows if x.quote == "USDT"}):
    own = independent(rows, base)
    project = defteri_hesapla(rows, base).turlar
    pairs_ok = len(own) == len(project) and all(
        close(a["sold"], b.satilan) and close(a["bought"], b.alinan_coin)
        for a, b in zip(own, project))
    own_sold, own_bought = sum(x["sold"] for x in own), sum(x["bought"] for x in own)
    pro_sold, pro_bought = sum(x.satilan for x in project), sum(x.alinan_coin for x in project)
    totals_ok = close(own_sold, pro_sold) and close(own_bought, pro_bought)
    all_ok &= pairs_ok and totals_ok
    max_diff = max([0.0] + [max(abs(a["sold"] - b.satilan), abs(a["bought"] - b.alinan_coin))
                            for a, b in zip(own, project)])
    print(f"{base} rounds={len(own)} sold_total={own_sold:.12g} bought_back_total={own_bought:.12g}")
    print(f"{base} max_round_abs_diff={max_diff:.12g} totals_abs_diff={max(abs(own_sold-pro_sold), abs(own_bought-pro_bought)):.12g}")
print("G3", "PASS" if all_ok else "FAIL")

