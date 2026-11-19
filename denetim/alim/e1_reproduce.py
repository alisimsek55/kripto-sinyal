import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_PYTHON = Path(sys.executable)


def run(*args, echo=True):
    p = subprocess.run([str(EXPECTED_PYTHON), *args], cwd=ROOT, text=True,
                       capture_output=True, encoding="utf-8")
    if echo:
        print(p.stdout)
    if p.returncode:
        print(p.stderr)
        raise SystemExit(p.returncode)
    return p.stdout


if __name__ == "__main__":
    print(f"python={EXPECTED_PYTHON}")
    test_out = run("-m", "pytest", "-q")
    match = re.search(r"(\d+) passed", test_out)
    test_count = int(match.group(1)) if match else None
    result_path = ROOT / "sonuc/parametreler.json"
    original = result_path.read_bytes()
    try:
        run("-m", "kripto_sinyal", "geritest", echo=False)
        result = json.loads(result_path.read_text(encoding="utf-8"))
    finally:
        result_path.write_bytes(original)
    doge = result["coinler"]["DOGE"]["kurallar"]["alim"]["ileri_yuruyus"]["zincir_oran"]
    btc = result["coinler"]["BTC"]["kurallar"]["alim"]["ileri_yuruyus"]["zincir_oran"]
    btc_is = result["coinler"]["BTC"]["kurallar"]["alim"]["egitim_ici_oran"]
    ok = (test_count is not None and round(doge, 6) == 0.967721 and
          round(btc, 6) == 0.976432 and round(btc_is, 6) == 1.008508)
    print(f"E1 {'PASS' if ok else 'FAIL'} tests={test_count} DOGE={doge:.12f} "
          f"BTC={btc:.12f} BTC_IS={btc_is:.12f}")

