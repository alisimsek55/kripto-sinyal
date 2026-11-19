"""Yayınlanan sonuç iddiaları, depodaki JSON kanıtlarıyla eşleşmeli."""

import json
import re
from pathlib import Path

import pytest

from kripto_sinyal.__main__ import main

KOK = Path(__file__).resolve().parents[1]


def test_readme_coin_sayilari_kayitli_sonucla_ayni():
    metin = (KOK / "README.md").read_text(encoding="utf-8")
    sonuc = json.loads((KOK / "sonuc/coinler.json").read_text(encoding="utf-8"))
    e = re.search(r"(\d+) coinin kısa satışta (\d+)'ü, uzun satışta (\d+)'ü,\s*"
                  r"birleşimde (\d+)'ü, alım ayarında (\d+)'ü", metin)
    assert e is not None
    toplam, *gecenler = map(int, e.groups())
    assert toplam == len(sonuc["coinler"])
    for ad, gecen in zip(("kisa", "uzun", "birlikte", "alim"), gecenler):
        assert gecen == sum(c[ad] > 1 + 1e-9 for c in sonuc["coinler"].values())
        assert sonuc["ozet"][ad]["geometrik_ortalama"] < 1


def test_readme_doge_btc_iddiasi_kayitli_sonucla_ayni():
    metin = (KOK / "README.md").read_text(encoding="utf-8")
    sonuc = json.loads((KOK / "sonuc/parametreler.json").read_text(encoding="utf-8"))
    for coin in ("DOGE", "BTC"):
        a = sonuc["coinler"][coin]
        tarih = ".".join(reversed(a["veri_son"].split("-")))
        assert tarih in metin
        assert all(k["ileri_yuruyus"]["zincir_oran"] < 1 for k in a["kurallar"].values())


def test_readme_komutlari_cli_tarafindan_taninir(capsys):
    metin = (KOK / "README.md").read_text(encoding="utf-8")
    komutlar = set(re.findall(r"python -m kripto_sinyal ([a-z-]+)", metin))
    assert len(komutlar) == 8
    for komut in komutlar:
        with pytest.raises(SystemExit) as sonuc:
            main([komut, "--help"])
        assert sonuc.value.code == 0
        capsys.readouterr()
