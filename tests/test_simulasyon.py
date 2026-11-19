"""Simülasyon motoru testleri (ağ yok, sentetik veri)."""

import numpy as np
import pandas as pd
import pytest

from kripto_sinyal.simulasyon import (Durum, KisaParam, Maliyet, Seri, UzunParam, coin_al,
                                      coin_sat, dca, max_dusus, simule)

SIFIR = Maliyet(aylik=0.0, komisyon=0.0, kayma=0.0)


def tablo(kapanis, acilis=None, bas="2024-01-01", tarihler=None):
    kapanis = list(map(float, kapanis))
    if acilis is None:  # açılış = dünkü kapanış
        acilis = [kapanis[0]] + kapanis[:-1]
    if tarihler is None:
        tarihler = pd.date_range(bas, periods=len(kapanis), freq="D").strftime("%Y-%m-%d")
    return pd.DataFrame({"tarih": list(tarihler), "acilis": list(map(float, acilis)),
                         "yuksek": kapanis, "dusuk": kapanis, "kapanis": kapanis, "hacim": 1.0})


def rastgele(gun=900, tohum=1):
    r = np.random.default_rng(tohum)
    kap = 1.0 * np.exp(np.cumsum(r.normal(0, 0.06, gun)))
    ac = np.r_[kap[0], kap[:-1]] * np.exp(r.normal(0, 0.01, gun))
    return tablo(kap, ac, bas="2020-01-01")


# ---------- maliyet ----------

def test_maliyet_formulleri():
    m = Maliyet(aylik=100, komisyon=0.001, kayma=0.0005)
    assert coin_al(100, 2.0, m) == pytest.approx(100 * 0.999 / (2.0 * 1.0005))
    assert coin_sat(10, 2.0, m) == pytest.approx(10 * 2.0 * 0.9995 * 0.999)


def test_satista_maliyet_uygulanir():
    m = Maliyet(aylik=0.0, komisyon=0.01, kayma=0.02)
    seri = Seri.tablodan(tablo([10, 12.5, 12.5]))
    p = KisaParam(n=1, x=0.2, s=0.5, y=0.5, b=1.0, t=0)
    d, _ = simule(seri, p, None, m, durum=Durum(coin=100.0))
    assert d.islemler[0][:2] == (2, "sat")
    assert d.coin == pytest.approx(50.0)
    assert d.kisa.nakit == pytest.approx(50 * 12.5 * 0.98 * 0.99)


def test_islem_kaydinda_gerceklesen_fiyat_ve_maliyet_tutarli():
    m = Maliyet(aylik=0.0, komisyon=0.01, kayma=0.02)
    seri = Seri.tablodan(tablo([10, 12.5, 12.5, 9.9, 9.9]))
    p = KisaParam(n=1, x=0.2, s=0.5, y=0.2, b=1.0, t=0)
    d, _ = simule(seri, p, None, m, durum=Durum(coin=100.0))
    satis, alim = d.islemler
    assert satis[5] == pytest.approx(satis[3] * (1 - m.kayma), rel=1e-12)
    assert alim[5] == pytest.approx(alim[3] * (1 + m.kayma), rel=1e-12)
    satis_nakdi = satis[4] * satis[5] * (1 - m.komisyon)
    assert alim[4] == pytest.approx(satis_nakdi * (1 - m.komisyon) / alim[5])
    assert d.coin == pytest.approx(100.0 - satis[4] + alim[4])
    assert d.kisa.nakit == pytest.approx(0.0)


# ---------- düz düzenli alım (elle hesaplanmış) ----------

def test_dca_elle_hesap():
    df = tablo([1.5, 3, 4, 6], acilis=[1, 2, 4, 5],
               tarihler=["2024-01-31", "2024-02-01", "2024-02-02", "2024-03-01"])
    seri = Seri.tablodan(df)
    coin, deger = dca(seri, Maliyet(aylik=100, komisyon=0, kayma=0))
    # 31 Oca: 100/1=100 coin; 1 Şub: +100/2=50; 2 Şub: alım yok; 1 Mar: +100/5=20
    assert list(coin) == [100, 150, 150, 170]
    assert list(deger) == [150, 450, 600, 1020]
    coin2, _ = dca(seri, Maliyet(aylik=100, komisyon=0.01, kayma=0))
    assert coin2[-1] == pytest.approx(99 + 49.5 + 19.8)


def test_kuralsiz_simulasyon_dca_ile_ayni():
    seri = Seri.tablodan(rastgele(400))
    m = Maliyet()
    _, v = simule(seri, None, None, m)
    _, t = dca(seri, m)
    assert np.allclose(v, t)


# ---------- geleceğe bakış yok ----------

def test_gelecek_degisince_gecmis_kararlar_degismez():
    df = rastgele(900)
    k = 600
    df2 = df.copy()
    r = np.random.default_rng(7)
    for s in ("acilis", "kapanis"):
        df2.loc[k + 1:, s] = df2.loc[k + 1:, s] * r.uniform(0.3, 3.0, len(df) - k - 1)
    kisa = KisaParam(n=7, x=0.15, s=0.3, y=0.1, b=0.5, t=90)
    uzun = UzunParam(u=1.3, sl=0.2, l=0.8, bl=0.5, t=180)
    m = Maliyet()
    d1, v1 = simule(Seri.tablodan(df), kisa, uzun, m)
    d2, v2 = simule(Seri.tablodan(df2), kisa, uzun, m)
    once1 = [i for i in d1.islemler if i[0] <= k]
    once2 = [i for i in d2.islemler if i[0] <= k]
    assert len(once1) > 5, "test anlamlı olsun diye işlem olmalı"
    assert once1 == once2
    assert np.array_equal(v1[:k + 1], v2[:k + 1])
    # k kapanışında verilen emirler k+1'de aynı yönde uygulanır (fiyat farklı olabilir)
    assert [i[1:3] for i in d1.islemler if i[0] == k + 1] == [i[1:3] for i in d2.islemler if i[0] == k + 1]
    # 200 günlük ortalama yalnız geçmişi kullanır
    np.testing.assert_array_equal(Seri.tablodan(df).sma200[:k + 1], Seri.tablodan(df2).sma200[:k + 1])


def test_sinyal_ertesi_gun_acilisinda_uygulanir():
    # 1. gün kapanışı +%25 -> satış 2. gün AÇILIŞINDA (açılış 20, kapanış 50)
    seri = Seri.tablodan(tablo([10, 12.5, 50], acilis=[10, 10, 20]))
    p = KisaParam(n=1, x=0.2, s=0.5, y=0.5, b=1.0, t=0)
    d, _ = simule(seri, p, None, SIFIR, durum=Durum(coin=100.0))
    assert d.islemler == [(2, "sat", "kisa", 20.0, 50.0, 20.0)]


# ---------- merdiven ve geri alım ----------

def test_kisa_merdiven_ve_geri_alim():
    #        0   1     2   3     4   5    6    7   8
    kap = [10, 12.5, 11, 13.4, 13, 9.9, 9.9, 12, 12]
    seri = Seri.tablodan(tablo(kap))
    p = KisaParam(n=1, x=0.2, s=0.5, y=0.2, b=1.0, t=0)
    d, _ = simule(seri, p, None, SIFIR, durum=Durum(coin=100.0))
    gun_tur = [(i[0], i[1]) for i in d.islemler]
    # gün 1 +%25 -> gün 2 satış (12.5). gün 3 +%21.8 ama 13.4 < 12.5*1.1 -> merdiven engeller.
    # gün 5: 9.9 <= 12.5*0.8 -> gün 6 geri alım. Geri alım merdiveni sıfırlar:
    # gün 7 +%21 -> gün 8 satış (12 < 13.75 olsa da).
    assert gun_tur == [(2, "sat"), (6, "al"), (8, "sat")]
    assert d.islemler[0][3:5] == (12.5, 50.0)
    assert d.islemler[1][3] == 9.9
    assert d.islemler[1][4] == pytest.approx(625 / 9.9)


def test_merdiven_yeterli_yukseliste_ikinci_satis():
    kap = [10, 12.5, 11, 14.0, 14.0]
    seri = Seri.tablodan(tablo(kap))
    p = KisaParam(n=1, x=0.2, s=0.5, y=0.2, b=1.0, t=0)
    d, _ = simule(seri, p, None, SIFIR, durum=Durum(coin=100.0))
    assert [(i[0], i[1]) for i in d.islemler] == [(2, "sat"), (4, "sat")]
    assert d.coin == pytest.approx(25.0)


def test_geri_alim_tekrari_daha_derin_dusus_ister():
    kap = [10, 12.5, 12.5, 9.9, 9.9, 9.0, 7.9, 7.9]
    seri = Seri.tablodan(tablo(kap))
    p = KisaParam(n=1, x=0.2, s=0.5, y=0.2, b=0.5, t=0)
    d, _ = simule(seri, p, None, SIFIR, durum=Durum(coin=100.0))
    # 9.9'da ilk geri alım; ikincisi 9.9*0.8=7.92 altını bekler (9.0'da alım yok)
    assert [(i[0], i[1], i[3]) for i in d.islemler] == [(2, "sat", 12.5), (4, "al", 9.9), (7, "al", 7.9)]


def test_bekleme_suresi_dolunca_kademeli_geri_giris():
    kap = [10, 12.5] + [12.5] * 128
    seri = Seri.tablodan(tablo(kap, bas="2024-01-01"))
    p = KisaParam(n=1, x=0.2, s=0.5, y=0.5, b=1.0, t=30)
    d, _ = simule(seri, p, None, SIFIR, durum=Durum(coin=100.0))
    bekleme = [i for i in d.islemler if i[2] == "kisa-bekleme"]
    # satış 3 Oca; 30 gün sonrası ilk ay başı 1 Mar, sonra 1 Nis, 1 May
    assert [seri.tarih[i[0]] for i in bekleme] == ["2024-03-01", "2024-04-01", "2024-05-01"]
    assert d.kisa.nakit == pytest.approx(0.0)
    assert d.coin == pytest.approx(100.0)  # maliyet sıfır, fiyat aynı -> coin geri geldi


def test_uzun_merdiven_ve_sifirlanma():
    kap = [1.0] * 199 + [2.1, 2.1, 2.1, 2.8, 2.8, 0.5, 0.5]
    seri = Seri.tablodan(tablo(kap))
    q = UzunParam(u=2.0, sl=0.3, l=0.6, bl=1.0, t=0)
    d, _ = simule(seri, None, q, SIFIR, durum=Durum(coin=100.0))
    # 199: oran>2 -> 200'de sat; seviye 2.5. 200-201: 2.1 < 2.5 satış yok.
    # 202: oran>2.5 -> 203'te sat. 204: oran<1 -> sıfırlama, oran<0.6 -> 205'te al.
    assert [(i[0], i[1]) for i in d.islemler] == [(200, "sat"), (203, "sat"), (205, "al")]
    assert d.uzun_seviye is None
    assert d.uzun.nakit == pytest.approx(0.0)


def test_max_dusus():
    assert max_dusus(np.array([1, 2, 1, 3, 1.5])) == pytest.approx(0.5)
