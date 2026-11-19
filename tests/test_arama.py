"""İleri yürüyüş (walk-forward) testleri: test yılı seçimde asla görülmez."""

import numpy as np
import pandas as pd
import pytest

from kripto_sinyal import arama
from kripto_sinyal.arama import (KISA_EKSEN, UZUN_EKSEN, coin_analizi, izgara, izgara_degerleri,
                                 katlar, sec, zincir)
from kripto_sinyal.simulasyon import (KisaParam, Maliyet, Seri, UzunParam, coin_al, coin_sat,
                                      dca)


def sentetik(bas="2019-07-05", son="2022-06-30", tohum=3):
    tarih = pd.date_range(bas, son, freq="D")
    r = np.random.default_rng(tohum)
    kap = np.exp(np.cumsum(r.normal(0.001, 0.05, len(tarih))))
    return pd.DataFrame({"tarih": tarih.strftime("%Y-%m-%d"), "acilis": np.r_[kap[0], kap[:-1]],
                         "yuksek": kap, "dusuk": kap, "kapanis": kap, "hacim": 1.0})


def test_kat_sinirlari():
    seri = Seri.tablodan(sentetik())
    k = katlar(seri)
    # 2020'nin eğitimi 365 günden kısa -> ilk test yılı 2021
    assert [x["yil"] for x in k] == [2021, 2022]
    for x in k:
        assert x["egitim_son"] + 1 == x["test_bas"]
        assert seri.tarih[x["egitim_son"]] == f"{x['yil'] - 1}-12-31"
        assert seri.tarih[x["test_bas"]] == f"{x['yil']}-01-01"
        assert all(seri.yil[i] == x["yil"] for i in range(x["test_bas"], x["test_son"] + 1))
    assert k[0]["eksik_yil"] is False and k[1]["eksik_yil"] is True


def _secimler(df, m):
    seri = Seri.tablodan(df)
    _, taban = dca(seri, m)
    sonuc = []
    for tur, eksen, sinif in (("kisa", KISA_EKSEN, KisaParam), ("uzun", UZUN_EKSEN, UzunParam)):
        params, komsu = izgara(eksen, sinif)
        V = izgara_degerleri(seri, params, tur, m)
        sonuc.append([sec(V, taban, komsu, x["egitim_son"], params) for x in katlar(seri)])
    return sonuc


def test_test_yili_secimi_etkilemez():
    m = Maliyet()
    df = sentetik()
    asil = _secimler(df, m)
    k = katlar(Seri.tablodan(df))
    for j, x in enumerate(k):
        # 1) Test yılını ve sonrasını tamamen boz: seçim aynı kalmalı
        bozuk = df.copy()
        n = len(df) - x["test_bas"]
        carpan = np.random.default_rng(j).uniform(0.2, 5.0, n)
        bozuk.loc[x["test_bas"]:, ["acilis", "kapanis"]] = (
            bozuk.loc[x["test_bas"]:, ["acilis", "kapanis"]].values * carpan[:, None])
        b = _secimler(bozuk, m)
        # 2) Veriyi eğitim sonunda kes: seçim yine aynı kalmalı
        kesik = df.iloc[: x["egitim_son"] + 1].reset_index(drop=True)
        seri_k = Seri.tablodan(kesik)
        _, taban_k = dca(seri_k, m)
        for t, (tur, eksen, sinif) in enumerate((("kisa", KISA_EKSEN, KisaParam),
                                                 ("uzun", UZUN_EKSEN, UzunParam))):
            assert b[t][j][0] == asil[t][j][0]
            params, komsu = izgara(eksen, sinif)
            V = izgara_degerleri(seri_k, params, tur, m)
            assert sec(V, taban_k, komsu, len(seri_k) - 1, params)[0] == asil[t][j][0]


def test_izgara_komsulari():
    params, komsu = izgara({"a": [1, 2, 3], "b": [10, 20]}, lambda a, b: (a, b))
    k = params.index((2, 10))
    assert sorted(params[i] for i in komsu[k]) == [(1, 10), (2, 10), (2, 20), (3, 10)]
    assert len(izgara(KISA_EKSEN, KisaParam)[0]) <= 300
    assert len(izgara(UZUN_EKSEN, UzunParam)[0]) <= 300


def test_sec_egitimde_kazanamazsa_kapatir():
    V = np.array([[1.0, 0.9], [1.0, 0.95]])
    taban = np.array([1.0, 1.0])
    p, puan, _ = sec(V, taban, [[0, 1], [1, 0]], 1, ["a", "b"])
    assert p is None and puan < 0


def test_zincir_yil_oranlari_carpimi_zincir_sonucu():
    a = coin_analizi(Seri.tablodan(sentetik(son="2023-03-31")), Maliyet())
    for tur in ("kisa", "uzun", "birlesik"):
        iy = a["kurallar"][tur]["ileri_yuruyus"]
        assert abs(np.prod([y["oran"] for y in iy["yillar"]]) - iy["zincir_oran"]) < 1e-9
        assert [y["yil"] for y in iy["yillar"]] == [2021, 2022, 2023]


def test_veri_ileri_yuruyus_icin_cok_kisa():
    seri = Seri.tablodan(sentetik(bas="2022-01-01", son="2022-12-31"))
    with pytest.raises(ValueError, match="en az 2 tam takvim yılı gerekli"):
        coin_analizi(seri, Maliyet())


def _zorunlu_secim_verisi(satis=True):
    tarih = pd.date_range("2020-12-01", "2022-03-01", freq="D")
    acilis = np.full(len(tarih), 10.0)
    kapanis = np.full(len(tarih), 10.0)
    if satis:
        yukselis = tarih >= "2021-01-02"
        acilis[yukselis] = 20.0
        kapanis[yukselis] = 20.0
        acilis[tarih == "2021-01-02"] = 10.0
        for ay, fiyat in (("2022-01", 10.0), ("2022-02", 20.0), ("2022-03", 40.0)):
            bu_ay = np.char.startswith(tarih.strftime("%Y-%m").to_numpy(dtype=str), ay)
            acilis[bu_ay] = fiyat
            kapanis[bu_ay] = fiyat
    seri = Seri.tablodan(pd.DataFrame({"tarih": tarih.strftime("%Y-%m-%d"),
                                       "acilis": acilis, "kapanis": kapanis}))
    kat_listesi = [
        {"yil": 2021, "test_bas": seri.tarih.index("2021-01-01"),
         "test_son": seri.tarih.index("2021-12-31"), "eksik_yil": False},
        {"yil": 2022, "test_bas": seri.tarih.index("2022-01-01"),
         "test_son": seri.tarih.index("2022-03-01"), "eksik_yil": True},
    ]
    return seri, kat_listesi


def _zorunlu_secim_zinciri(monkeypatch, satis=True):
    seri, kat_listesi = _zorunlu_secim_verisi(satis)
    p = KisaParam(n=1, x=0.5, s=0.5, y=0.99, b=1.0, t=0)
    m = Maliyet(aylik=100.0, komisyon=0.01, kayma=0.02)
    gercek_simule = arama.simule
    son_durum = []

    def durum_kaydet(*args, **kwargs):
        d, v = gercek_simule(*args, **kwargs)
        son_durum[:] = [d]
        return d, v

    monkeypatch.setattr(arama, "simule", durum_kaydet)
    sonuc = zincir(seri, kat_listesi, [p, None], [None, None], m)
    return seri, m, sonuc, son_durum[0]


def test_kapali_kural_nakdi_uc_ayda_maliyetle_geri_alir(monkeypatch):
    seri, m, _, d = _zorunlu_secim_zinciri(monkeypatch)
    alimlar = [islem for islem in d.islemler if islem[2] == "kisa-bekleme"]
    assert [seri.tarih[i[0]] for i in alimlar] == ["2022-01-01", "2022-02-01", "2022-03-01"]
    satis = next(islem for islem in d.islemler if islem[1] == "sat")
    tasinan_nakit = coin_sat(satis[4], satis[3], m)
    for alim in alimlar:
        beklenen = coin_al(tasinan_nakit / 3, alim[3], m)
        assert alim[4] == pytest.approx(beklenen, rel=1e-9)
    assert d.kisa.nakit == 0.0


def test_kapali_kural_zincir_yil_oranlari_carpimi(monkeypatch):
    _, _, sonuc, _ = _zorunlu_secim_zinciri(monkeypatch)
    carpim = np.prod([y["oran"] for y in sonuc["yillar"]])
    assert carpim == pytest.approx(sonuc["zincir_oran"], rel=1e-9)


def test_nakitsiz_kapali_kural_duz_alimla_ayni(monkeypatch):
    _, _, sonuc, d = _zorunlu_secim_zinciri(monkeypatch, satis=False)
    assert d.kisa.nakit == 0.0
    assert sonuc["yillar"][1]["oran"] == pytest.approx(1.0, rel=1e-9)


def _yil_siniri_bekleyen_satis(monkeypatch, kural):
    tarih = pd.date_range("2020-01-01", "2021-03-02", freq="D")
    taban = 10.0 if kural == "kisa" else 1.0
    acilis = np.full(len(tarih), taban)
    kapanis = np.full(len(tarih), taban)
    kapanis[tarih == "2020-12-31"] = 16.0 if kural == "kisa" else 3.0
    seri = Seri.tablodan(pd.DataFrame({"tarih": tarih.strftime("%Y-%m-%d"),
                                       "acilis": acilis, "kapanis": kapanis}))
    kat_listesi = [
        {"yil": 2020, "test_bas": seri.tarih.index("2020-07-01"),
         "test_son": seri.tarih.index("2020-12-31"), "eksik_yil": False},
        {"yil": 2021, "test_bas": seri.tarih.index("2021-01-01"),
         "test_son": seri.tarih.index("2021-03-02"), "eksik_yil": True},
    ]
    if kural == "kisa":
        p = KisaParam(n=1, x=0.5, s=0.4, y=0.2, b=1.0, t=0)
        secim_kisa, secim_uzun, satis_orani = [p, None], [None, None], p.s
    else:
        p = UzunParam(u=2.0, sl=0.3, l=0.6, bl=1.0, t=0)
        secim_kisa, secim_uzun, satis_orani = [None, None], [p, None], p.sl
    m = Maliyet(aylik=100.0, komisyon=0.0, kayma=0.0)
    gercek_simule = arama.simule
    son_durum = []

    def durum_kaydet(*args, **kwargs):
        d, v = gercek_simule(*args, **kwargs)
        son_durum[:] = [d]
        return d, v

    monkeypatch.setattr(arama, "simule", durum_kaydet)
    zincir(seri, kat_listesi, secim_kisa, secim_uzun, m)
    taban_coin, _ = dca(seri, m)
    yil_sonu_coin = taban_coin[seri.tarih.index("2020-12-31")]
    return seri, son_durum[0], satis_orani, yil_sonu_coin


@pytest.mark.parametrize("kural", ["uzun", "kisa"])
def test_yil_siniri_bekleyen_satis_kapali_kuralda_uygulanir(monkeypatch, kural):
    seri, d, satis_orani, yil_sonu_coin = _yil_siniri_bekleyen_satis(monkeypatch, kural)
    satis = next(i for i in d.islemler if i[1:3] == ("sat", kural))
    assert seri.tarih[satis[0]] == "2021-01-01"
    assert satis[4] == pytest.approx(yil_sonu_coin * satis_orani)
    geri_giris = [i for i in d.islemler if i[2] == kural + "-bekleme"]
    assert [seri.tarih[i[0]] for i in geri_giris] == [
        "2021-01-01", "2021-02-01", "2021-03-01"]
    assert (d.kisa if kural == "kisa" else d.uzun).nakit == pytest.approx(0.0)
