"""Satışsız alım ayarı testleri."""

import math

import numpy as np
import pandas as pd
import pytest

from kripto_sinyal import arama
from kripto_sinyal.arama import (ALIM_EKSEN, alim_zincir, izgara, izgara_degerleri, katlar,
                                 sec)
from kripto_sinyal.simulasyon import (AlimParam, Maliyet, Seri, alim_simule, dca)


def _tablo(bas="2019-01-01", son="2023-06-30", tohum=11):
    tarih = pd.date_range(bas, son, freq="D")
    r = np.random.default_rng(tohum)
    kap = np.exp(np.cumsum(r.normal(0.0005, 0.035, len(tarih))))
    ac = np.r_[kap[0], kap[:-1]] * np.exp(r.normal(0, 0.005, len(tarih)))
    return pd.DataFrame({"tarih": tarih.strftime("%Y-%m-%d"), "acilis": ac,
                         "yuksek": np.maximum(ac, kap), "dusuk": np.minimum(ac, kap),
                         "kapanis": kap, "hacim": 1.0})


def _aylik_seri(tarihler, kapanis, sma, acilis=None):
    acilis = kapanis if acilis is None else acilis
    return Seri(list(tarihler), list(map(float, acilis)), list(map(float, kapanis)),
                [True] * len(tarihler), list(map(float, sma)),
                [int(t[:4]) for t in tarihler])


def test_tetiklenmeyen_ayar_duz_alimla_ayni():
    seri = Seri.tablodan(_tablo())
    m = Maliyet()
    p = AlimParam(u=math.inf, k=0.0, l=0.0, g=1.0, t=0)
    d, v = alim_simule(seri, p, m)
    coin, taban = dca(seri, m)
    np.testing.assert_allclose(d.coin_gecmisi, coin, rtol=1e-12)
    np.testing.assert_allclose(v, taban, rtol=1e-12)
    k = katlar(seri)
    z = alim_zincir(seri, k, [p] * len(k), m)
    assert z["zincir_oran"] == pytest.approx(1.0, rel=1e-12)


def test_pahali_ucuz_normal_elle_hesap():
    seri = Seri(["2024-01-31", "2024-02-01", "2024-03-01", "2024-04-01"],
                [10.0, 10.0, 5.0, 20.0], [20.0, 5.0, 10.0, 10.0],
                [False, True, True, True], [10.0, 10.0, 10.0, 10.0], [2024] * 4)
    m = Maliyet(aylik=100.0, komisyon=0.01, kayma=0.02)
    p = AlimParam(u=1.5, k=0.5, l=0.75, g=0.5, t=0)
    d, _ = alim_simule(seri, p, m, bas=1)
    assert [x[1] for x in d.kararlar] == ["pahalı", "ucuz", "normal"]
    assert d.yedek_gecmisi == pytest.approx([50.0, 25.0, 25.0])
    assert d.coin_gecmisi == pytest.approx([
        4.852941176470588,
        29.11764705882353,
        33.970588235294116,
    ], rel=1e-12)


def test_para_korunumu_rastgele_yirmi_izgara_noktasi():
    seri = Seri.tablodan(_tablo(son="2022-12-31"))
    m = Maliyet(aylik=137.0, komisyon=0.001, kayma=0.0005)
    params, _ = izgara(ALIM_EKSEN, AlimParam)
    secilen = np.random.default_rng(19).choice(len(params), size=20, replace=False)
    for j in secilen:
        d, _ = alim_simule(seri, params[int(j)], m)
        for _, yatirilan, yedek, katki in d.para_gecmisi:
            assert yatirilan + yedek == pytest.approx(katki, rel=1e-12, abs=1e-9)


def test_alim_ayari_gelecege_bakmaz():
    df = _tablo(son="2022-12-31")
    seri = Seri.tablodan(df)
    hedef = next(i for i in range(250, len(seri)) if seri.ay_basi[i])
    p = AlimParam(u=1.25, k=0.5, l=0.9, g=0.5, t=0)
    m = Maliyet()
    d1, _ = alim_simule(seri, p, m)
    bozuk = df.copy()
    bozuk.loc[hedef:, ["acilis", "yuksek", "dusuk", "kapanis"]] *= 7.0
    d2, _ = alim_simule(Seri.tablodan(bozuk), p, m)
    karar1 = next(x for x in d1.kararlar if x[0] == hedef)
    karar2 = next(x for x in d2.kararlar if x[0] == hedef)
    assert karar1 == karar2

    gun = hedef + 120
    bozuk2 = df.copy()
    bozuk2.loc[gun + 1:, ["acilis", "yuksek", "dusuk", "kapanis"]] *= 0.13
    d3, v3 = alim_simule(seri, p, m)
    d4, v4 = alim_simule(Seri.tablodan(bozuk2), p, m)
    assert [x for x in d3.kararlar if x[0] <= gun] == [x for x in d4.kararlar if x[0] <= gun]
    np.testing.assert_array_equal(d3.coin_gecmisi[:gun + 1], d4.coin_gecmisi[:gun + 1])
    np.testing.assert_array_equal(d3.yedek_gecmisi[:gun + 1], d4.yedek_gecmisi[:gun + 1])
    np.testing.assert_array_equal(v3[:gun + 1], v4[:gun + 1])


def test_alim_secimi_fiziksel_kesikle_ayni():
    df = _tablo(son="2022-06-30")
    seri = Seri.tablodan(df)
    m = Maliyet()
    params, komsu = izgara(ALIM_EKSEN, AlimParam)
    _, taban = dca(seri, m)
    V = izgara_degerleri(seri, params, "alim", m)
    for kat in katlar(seri):
        asil = sec(V, taban, komsu, kat["egitim_son"], params)[0]
        kesik_df = df.iloc[:kat["egitim_son"] + 1].reset_index(drop=True)
        kesik = Seri.tablodan(kesik_df)
        _, kesik_taban = dca(kesik, m)
        kesik_V = izgara_degerleri(kesik, params, "alim", m)
        assert sec(kesik_V, kesik_taban, komsu, len(kesik) - 1, params)[0] == asil


def test_sure_siniri_uc_ayda_yedegi_bitirir():
    tarihler = pd.date_range("2020-01-01", "2021-06-01", freq="MS").strftime("%Y-%m-%d").tolist()
    kapanis = [2.0] + [1.0] * (len(tarihler) - 1)
    seri = _aylik_seri(tarihler, kapanis, [1.0] * len(tarihler))
    m = Maliyet(aylik=100.0, komisyon=0.0, kayma=0.0)
    p = AlimParam(u=1.5, k=0.5, l=0.5, g=1.0, t=365)
    d, _ = alim_simule(seri, p, m)
    giris = [seri.tarih[x[0]] for x in d.islemler if x[2] == "alim-bekleme"]
    assert giris == ["2021-02-01", "2021-03-01", "2021-04-01"]
    assert d.yedek == pytest.approx(0.0)
    d0, _ = alim_simule(seri, AlimParam(1.5, 0.5, 0.5, 1.0, 0), m)
    assert d0.yedek == pytest.approx(50.0)


def test_kapali_yilda_yedek_uc_parcada_girer_ve_oranlar_carpilir(monkeypatch):
    tarihler = pd.date_range("2020-12-01", "2022-03-01", freq="MS").strftime("%Y-%m-%d").tolist()
    seri = _aylik_seri(tarihler, [2.0] * len(tarihler), [1.0] * len(tarihler),
                       [10.0] * len(tarihler))
    kat_listesi = [
        {"yil": 2021, "test_bas": 1, "test_son": 12, "eksik_yil": False},
        {"yil": 2022, "test_bas": 13, "test_son": 15, "eksik_yil": True},
    ]
    p = AlimParam(u=1.5, k=0.5, l=0.5, g=1.0, t=0)
    m = Maliyet(aylik=100.0, komisyon=0.01, kayma=0.02)
    gercek = arama.alim_simule
    son_durum = []

    def kaydet(*args, **kwargs):
        d, v = gercek(*args, **kwargs)
        son_durum[:] = [d]
        return d, v

    monkeypatch.setattr(arama, "alim_simule", kaydet)
    sonuc = alim_zincir(seri, kat_listesi, [p, None], m)
    giris = [x for x in son_durum[0].islemler if x[2] == "alim-bekleme"]
    assert [seri.tarih[x[0]] for x in giris] == ["2022-01-01", "2022-02-01", "2022-03-01"]
    assert [x[4] for x in giris] == pytest.approx([200.0, 200.0, 200.0])
    assert son_durum[0].yedek == pytest.approx(0.0)
    assert np.prod([y["oran"] for y in sonuc["yillar"]]) == pytest.approx(
        sonuc["zincir_oran"], rel=1e-9)
