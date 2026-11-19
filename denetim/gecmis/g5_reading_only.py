"""G5: static/read-only fairness findings plus measured aggregate exposure."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from kripto_sinyal.gecmis import csvleri_oku, defteri_hesapla

rows = csvleri_oku(ROOT / "gecmis")
third_buy_rows = quote_buy_rows = partial_rows = 0
third_fee_total = quote_fee_total = quote_formula_coin_effect = 0.0
for base in sorted({x.base for x in rows if x.quote == "USDT"}):
    d = defteri_hesapla(rows, base)
    cep = 0.0
    for r in (x for x in rows if x.base == base and x.quote == "USDT"):
        fee_quote = r.fee if r.fee_asset == r.quote else 0.0
        if r.yon == "SELL":
            cep += r.amount - fee_quote
            continue
        cost = r.amount + fee_quote
        used = min(cep, cost)
        outside = cost - used
        cep -= used
        if 1e-12 < used < cost - 1e-12:
            partial_rows += 1
        if r.fee_asset not in (r.base, r.quote):
            third_buy_rows += 1
            third_fee_total += r.fee
        if fee_quote and outside > 1e-12 and r.price:
            quote_buy_rows += 1
            quote_fee_total += fee_quote
            current = outside / r.price * (1.0 - fee_quote / r.amount)
            consistent = r.executed * outside / cost
            quote_formula_coin_effect += current - consistent

print(f"third_asset_buy_rows={third_buy_rows} third_fee_units_total={third_fee_total:.12g}")
print(f"quote_fee_buy_rows={quote_buy_rows} quote_fee_total={quote_fee_total:.12g} result2_coin_bias={quote_formula_coin_effect:.12g}")
print(f"partly_cep_funded_buy_rows={partial_rows}")
print("DEFECT third-asset buy fee is converted to an unrelated fee fraction: kripto_sinyal/gecmis.py:279-283")
print("DEFECT third-asset fees are listed but omitted from all scenario values/outside money: kripto_sinyal/gecmis.py:225-228,307-325")
print("DEFECT quote-fee hold formula uses subtraction instead of inclusive-cost division: kripto_sinyal/gecmis.py:279-283")
print("G5 FAIL")
