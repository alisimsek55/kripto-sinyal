"""30 günlük aralık, en büyük düşüş, iki yönlü satış hesabı ve coinler komutu testleri
(sentetik veri, ağ yok)."""

import json
import math

import numpy as np
import pandas as pd
import pytest

from kripto_sinyal import coinler, veri
from kripto_sinyal import __main__ as ana
from kripto_sinyal.aralik import en_buyuk_dusus, iki_yonlu_hesap, tarihsel_aralik
from kripto_sinyal.rapor import sayi_ek
from kripto_sinyal.simulasyon import Maliyet


def _yuruyus(n=1200, tohum=1):
    r = np.random.default_rng(tohum)
    return list(np.exp(np.cumsum(r.normal(0, 0.03, n))))


def test_aralik_yuzdelik_ve_son_kapanis():
    kap = _yuruyus()
    r = tarihsel_aralik(kap)
    k = np.asarray(kap)
    getiri = np.log(k[30:] / k[:-30])[-1095:]
    assert len(getiri) == 1095
    assert r["fiyat"] == kap[-1]
    assert r["alt"] == pytest.approx(kap[-1] * math.exp(np.quantile(getiri, 0.10)))
    assert r["ust"] == pytest.approx(kap[-1] * math.exp(np.quantile(getiri, 0.90)))
    assert r["alt"] < kap[-1] < r["ust"]
    assert r["alt_getiri"] == pytest.approx(r["alt"] / kap[-1] - 1)
    assert r["tarih"] is None


def test_aralik_yalniz_bitmis_gunler():
    kap = _yuruyus()
    tarihler = list(pd.date_range("2023-01-01", periods=len(kap), freq="D").strftime("%Y-%m-%d"))
    bugun = tarihler[-1]                       # son mum bitmemiş sayılır
    r = tarihsel_aralik(kap, tarihler=tarihler, bugun=bugun)
    beklenen = tarihsel_aralik(kap[:-1])
    assert r["tarih"] == tarihler[-2]
    assert r["fiyat"] == kap[-2]
    assert (r["alt"], r["ust"]) == pytest.approx((beklenen["alt"], beklenen["ust"]))
    # bitmemiş günün fiyatı ne olursa olsun sonuç değişmez
    r2 = tarihsel_aralik(kap[:-1] + [999.0], tarihler=tarihler, bugun=bugun)
    assert (r2["alt"], r2["ust"]) == (r["alt"], r["ust"])


def test_aralik_kisa_veride_none():
    assert tarihsel_aralik([1.0] * 1124) is None
    assert tarihsel_aralik([1.0] * 1125) is not None
    tarihler = list(pd.date_range("2023-01-01", periods=1125, freq="D").strftime("%Y-%m-%d"))
    assert tarihsel_aralik([1.0] * 1125, tarihler=tarihler, bugun=tarihler[-1]) is None


def test_en_buyuk_dusus():
    assert en_buyuk_dusus([1, 2, 1, 3, 0.6, 2]) == pytest.approx(0.8)
    assert en_buyuk_dusus([1, 2, 3]) == 0.0
    assert en_buyuk_dusus([]) == 0.0


def test_iki_yonlu_hesap_tam_nakit():
    dusus, yukselis = iki_yonlu_hesap(0.20, 0.30, 1.0, Maliyet(100.0, 0.001, 0.0005))
    assert dusus == pytest.approx(0.085, abs=0.001)
    assert yukselis == pytest.approx(-0.047, abs=0.001)
    # maliyetsiz: 0.8 + 0.2/0.7 ve 0.8 + 0.2/1.3
    d0, y0 = iki_yonlu_hesap(0.20, 0.30, 1.0, Maliyet(100.0, 0.0, 0.0))
    assert d0 == pytest.approx(0.8 + 0.2 / 0.7 - 1)
    assert y0 == pytest.approx(0.8 + 0.2 / 1.3 - 1)


def test_iki_yonlu_hesap_yarim_nakit():
    d, y = iki_yonlu_hesap(0.20, 0.30, 0.5, Maliyet(100.0, 0.0, 0.0))
    assert d == pytest.approx(0.8 + 0.1 / 0.7 - 1)   # yalnız kullanılan para coine döner
    assert y == pytest.approx(0.8 + 0.1 / 1.3 - 1)
    d_m, _ = iki_yonlu_hesap(0.20, 0.30, 0.5)        # proje maliyetleri
    assert d_m == pytest.approx(-0.058, abs=0.001)


@pytest.mark.parametrize("n, beklenen", [
    (0, "0'ında"), (1, "1'inde"), (2, "2'sinde"), (3, "3'ünde"), (4, "4'ünde"),
    (6, "6'sında"), (9, "9'unda"), (10, "10'unda"), (11, "11'inde"), (13, "13'ünde"),
])
def test_sayi_ek_bulunma(n, beklenen):
    assert sayi_ek(n, "de") == beklenen


# ---------- coinler komutu ----------

def _ayar(tmp_path):
    return {"aylik_tutar": 100.0, "komisyon": 0.001, "kayma": 0.0005,
            "coinler": {"DOGE": "DOGEUSDT", "BTC": "BTCUSDT"},
            "sonuc_dosyasi": str(tmp_path / "sonuc" / "parametreler.json"),
            "veri_klasoru": str(tmp_path / "veri")}


def test_coinler_komutu_json_ve_atlama(tmp_path, monkeypatch, capsys):
    ayar = _ayar(tmp_path)
    monkeypatch.setattr(ana, "ayarlari_oku", lambda: ayar)
    tablo = pd.DataFrame({"tarih": ["2024-01-01"], "acilis": [1.0], "yuksek": [1.0],
                          "dusuk": [1.0], "kapanis": [1.0], "hacim": [1.0]})
    indirilen = []
    monkeypatch.setattr(veri, "guncelle", lambda k, s: indirilen.append(s) or (tablo, 0))
    monkeypatch.setattr(veri, "oku", lambda k, s, *a: tablo)
    oranlar = {"DOGE": 0.85, "BTC": 1.10, "ETH": 1.05, "SOL": 0.90}
    sira = iter(list(coinler.semboller(ayar)))

    def sahte_analiz(seri, m):
        coin = next(sira)
        if coin not in oranlar:
            raise ValueError("kısa")
        o = oranlar[coin]
        return {"kurallar": {ad: {"ileri_yuruyus": {"zincir_oran": o}}
                             for ad in ("kisa", "uzun", "birlesik", "alim")}}

    monkeypatch.setattr(coinler, "coin_analizi", sahte_analiz)
    ana.main(["coinler"])
    cikti = capsys.readouterr().out
    assert len(indirilen) == 11 and "SHIBUSDT" in indirilen and "DOGEUSDT" in indirilen
    d = json.loads((tmp_path / "sonuc" / "coinler.json").read_text(encoding="utf-8"))
    assert set(d) == {"tarih", "coinler", "ozet"}
    assert d["coinler"]["BTC"] == {"kisa": 1.10, "uzun": 1.10, "birlikte": 1.10, "alim": 1.10}
    k = d["ozet"]["kisa"]
    assert k["gecen"] == 2 and k["toplam"] == 4
    assert k["geometrik_ortalama"] == pytest.approx((0.85 * 1.10 * 1.05 * 0.90) ** 0.25)
    assert "Atlanan:" in cikti and "XRP (geçmişi çok kısa" in cikti
    assert "4 coinin 2 tanesinde düz alımı geçti" in cikti


def test_ozetle_esit_oran_gecmis_sayilmaz():
    o = coinler.ozetle({"A": {k: 1.0 for k in coinler.KURALLAR}})
    assert o["kisa"]["gecen"] == 0 and o["kisa"]["toplam"] == 1
