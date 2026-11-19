"""Arşiv denetimleri başka bir klasöre taşınınca kişisel yollara bağlı kalmamalı."""

import runpy
import sys
import tempfile
from pathlib import Path

import pytest


@pytest.mark.parametrize("goreli", [
    "takip/t1_frozen_selection.py", "takip/t2_no_early_trades.py",
    "takip/t3_independent_ratio.py", "takip/t4_lookahead.py",
    "takip/t5_year_crossing.py", "alim/e1_reproduce.py",
])
def test_denetim_betikleri_tasinabilir(tmp_path, goreli):
    kaynak = Path(__file__).resolve().parents[1] / "denetim" / goreli
    hedef = tmp_path / "denetim" / goreli
    hedef.parent.mkdir(parents=True)
    hedef.write_bytes(kaynak.read_bytes())
    ns = runpy.run_path(str(hedef))
    assert ns["ROOT"] == tmp_path
    if "SCRATCH" in ns:
        assert ns["SCRATCH"] == Path(tempfile.gettempdir()) / "kripto-sinyal-denetim-takip"
    for ad in ("PYTHON", "EXPECTED_PYTHON"):
        if ad in ns:
            assert ns[ad] == Path(sys.executable)
