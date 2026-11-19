"""İleriye dönük takip ve karne testleri."""

import json
from dataclasses import asdict

import numpy as np
import pandas as pd
import pytest

from kripto_sinyal import arama, takip
from kripto_sinyal.__main__ import main
from kripto_sinyal.arama import tum_veri_secimi, zincir
from kripto_sinyal.simulasyon import AlimParam, KisaParam, Maliyet, Seri, dca


def _tablo(bas="2021-01-01", son="2021-03-31", fiyat=None):
    tarih = pd.date_range(bas, son, freq="D")
    if fiyat is None:
        fiyat = np.linspace(1.0, 1.2, len(tarih))
    fiyat = np.asarray(fiyat, dtype=float)
    return pd.DataFrame({"tarih": tarih.strftime("%Y-%m-%d"),
                         "acilis": np.r_[fiyat[0], fiyat[:-1]],
                         "yuksek": fiyat, "dusuk": fiyat,
                         "kapanis": fiyat, "hacim": 1.0})


def _ayar(tmp_path):
    return {"aylik_tutar": 100.0, "komisyon": 0.001, "kayma": 0.0005,
            "coinler": {"DOGE": "DOGEUSDT"}, "veri_klasoru": str(tmp_path / "veri")}


def _secim(p=None):
    return {"kisa": p, "uzun": None, "alim": None}


def test_takip_baslat_korur_ve_yeniden_arsivler(tmp_path, monkeypatch):
    df = _tablo()
    monkeypatch.setattr(takip.veri, "guncelle", lambda *a: (df, 0))
    monkeypatch.setattr(takip, "tum_veri_secimi", lambda *a: _secim())
    klasor = tmp_path / "takip"
    takip.takip_baslat(_ayar(tmp_path), klasor, "2021-03-31")
    ilk = (klasor / "baslangic.json").read_bytes()
    with pytest.raises(takip.TakipHatasi):
        takip.takip_baslat(_ayar(tmp_path), klasor)
    assert (klasor / "baslangic.json").read_bytes() == ilk
    takip.takip_baslat(_ayar(tmp_path), klasor, "2021-03-31", yeniden=True)
    assert (klasor / "baslangic-2021-03-31.json").read_bytes() == ilk
    assert (klasor / "baslangic.json").exists()


def test_baslangic_secimi_fiziksel_kesikten_gelir(tmp_path, monkeypatch):
    tarih = pd.date_range("2019-01-01", "2022-12-31", freq="D")
    r = np.random.default_rng(0)
    kap = np.exp(np.cumsum(r.normal(0.001, 0.05, len(tarih))))
    df = _tablo("2019-01-01", "2022-12-31", kap)
    monkeypatch.setattr(takip.veri, "guncelle", lambda *a: (df, 0))
    klasor = tmp_path / "takip"
    takip.takip_baslat(_ayar(tmp_path), klasor, "2021-12-31")
    kayit = json.loads((klasor / "baslangic.json").read_text(encoding="utf-8"))
    kesik = df[df["tarih"] <= "2021-12-31"].reset_index(drop=True)
    beklenen = tum_veri_secimi(Seri.tablodan(kesik), Maliyet())
    gelecekli = tum_veri_secimi(Seri.tablodan(df), Maliyet())
    assert {k: kayit["coinler"]["DOGE"][k] for k in ("kisa", "uzun", "alim")} == {
        k: None if v is None else asdict(v) for k, v in beklenen.items()}
    assert beklenen != gelecekli


def test_henuz_gun_yoksa_oranlar_bir(tmp_path, monkeypatch, capsys):
    df = _tablo()
    monkeypatch.setattr(takip.veri, "guncelle", lambda *a: (df, 0))
    monkeypatch.setattr(takip, "tum_veri_secimi", lambda *a: _secim())
    klasor = tmp_path / "takip"
    takip.takip_baslat(_ayar(tmp_path), klasor, "2021-03-31")
    capsys.readouterr()
    sonuc = takip.karne(_ayar(tmp_path), klasor)
    assert all(k["oran"] == 1.0 for k in sonuc["coinler"]["DOGE"]["kurallar"].values())
    assert "henüz biten gün yok" in capsys.readouterr().out


def test_karne_yillik_yeniden_secimi_aciklar(tmp_path, monkeypatch, capsys):
    df = _tablo()
    monkeypatch.setattr(takip.veri, "guncelle", lambda *a: (df, 0))
    monkeypatch.setattr(takip, "tum_veri_secimi", lambda *a: _secim())
    klasor = tmp_path / "takip"
    takip.takip_baslat(_ayar(tmp_path), klasor, "2021-03-31")
    capsys.readouterr()
    takip.karne(_ayar(tmp_path), klasor)
    metin = capsys.readouterr().out
    assert "Her yeni takvim yılında yalnız önceki yıl sonuna kadarki veriyle yeniden seçim" in metin


def test_eski_onbellek_gercek_ileri_takip_sayilmaz(tmp_path, monkeypatch):
    df = _tablo()
    monkeypatch.setattr(takip.veri, "guncelle", lambda *a: (df, 0))
    klasor = tmp_path / "takip"
    with pytest.raises(takip.TakipHatasi, match="güncel değil"):
        takip.takip_baslat(_ayar(tmp_path), klasor)
    assert not (klasor / "baslangic.json").exists()


def test_taze_veriyle_varsayilan_gercek_ileri_takip(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone
    dun = datetime.now(timezone.utc).date() - timedelta(days=1)
    df = _tablo(str(dun - timedelta(days=90)), str(dun))
    monkeypatch.setattr(takip.veri, "guncelle", lambda *a: (df, 0))
    monkeypatch.setattr(takip, "tum_veri_secimi", lambda *a: _secim())
    kayit = takip.takip_baslat(_ayar(tmp_path), tmp_path / "takip")
    assert kayit["baslangic"] == str(dun) and kayit["geriye_donuk"] is False


def test_ilk_durum_ve_islemler_baslangictan_sonra(monkeypatch):
    df = _tablo("2020-12-01", "2021-03-01")
    df.loc[df["tarih"] >= "2021-01-16", "kapanis"] = 2.0
    seri = Seri.tablodan(df)
    bas = seri.tarih.index("2021-01-16")
    kat = [{"yil": 2021, "test_bas": bas, "test_son": len(seri) - 1, "eksik_yil": True}]
    p = KisaParam(1, 0.5, 0.2, 0.2, 1.0, 0)
    m = Maliyet()
    gorulen = []
    gercek = arama.simule

    def kaydet(*args, **kwargs):
        gorulen.append(args[-1].coin)
        return gercek(*args, **kwargs)

    monkeypatch.setattr(arama, "simule", kaydet)
    sonuc = zincir(seri, kat, [p], [None], m, baslangic_coin=7.0, ayrinti=True)
    assert gorulen[0] == 7.0
    assert all(i[0] >= bas for i in sonuc["_durum"].islemler)
    _, beklenen = dca(seri, m, bas, coin0=7.0)
    np.testing.assert_array_equal(sonuc["_taban"], beklenen)


def test_kapali_kural_her_gun_duz_alimla_ayni():
    seri = Seri.tablodan(_tablo("2020-12-01", "2021-03-01"))
    bas = seri.tarih.index("2021-01-16")
    kat = [{"yil": 2021, "test_bas": bas, "test_son": len(seri) - 1, "eksik_yil": True}]
    sonuc = zincir(seri, kat, [None], [None], Maliyet(), 9.0, True)
    np.testing.assert_array_equal(sonuc["_degerler"], sonuc["_taban"])
    assert sonuc["zincir_oran"] == 1.0


def test_karne_donmus_parametreyi_kullanir(tmp_path, monkeypatch, capsys):
    tarih = pd.date_range("2021-01-01", "2021-02-15", freq="D")
    fiyatlar = np.ones(len(tarih))
    fiyatlar[tarih >= "2021-01-20"] = 2.0
    df = _tablo("2021-01-01", "2021-02-15", fiyatlar)
    p = KisaParam(1, 0.05, 0.5, 0.2, 1.0, 0)
    monkeypatch.setattr(takip.veri, "guncelle", lambda *a: (df, 0))
    monkeypatch.setattr(takip, "tum_veri_secimi", lambda *a: _secim(p))
    klasor = tmp_path / "takip"
    takip.takip_baslat(_ayar(tmp_path), klasor, "2021-01-15")
    capsys.readouterr()
    monkeypatch.setattr(takip, "tum_veri_secimi", lambda *a: _secim())
    sonuc = takip.karne(_ayar(tmp_path), klasor)
    assert sonuc["coinler"]["DOGE"]["kurallar"]["kisa"]["islem_sayisi"] > 0
    coin = sonuc["coinler"]["DOGE"]
    assert coin["kurallar"]["birlikte"]["islem_sayisi"] == 1
    assert sum(i["kural"] == "kısa" for i in coin["islemler"]) == 1
    assert all(i["kural"] != "birlikte" for i in coin["islemler"])
    assert "Dikkat: kod ya da veri değişmiş" in capsys.readouterr().out


def test_esit_oran_ayni_yazar(tmp_path, monkeypatch, capsys):
    df = _tablo("2020-01-01", "2021-01-15", np.ones(381))
    monkeypatch.setattr(takip.veri, "guncelle", lambda *a: (df, 0))
    monkeypatch.setattr(takip, "tum_veri_secimi", lambda *a: _secim())
    klasor = tmp_path / "takip"
    takip.takip_baslat(_ayar(tmp_path), klasor, "2020-06-30")
    capsys.readouterr()
    sonuc = takip.karne(_ayar(tmp_path), klasor)
    cikti = capsys.readouterr().out
    assert "x1.0000 (düz alımla aynı)" in cikti
    assert "Hüküm: kısa aynı; uzun aynı; birlikte aynı; alım aynı." in cikti
    assert "önde" not in cikti
    assert all(k["durum"] == "ayni"
               for k in sonuc["coinler"]["DOGE"]["kurallar"].values())


def test_kapali_kurallar_duzenli_alimlari_islem_saymaz(tmp_path, monkeypatch, capsys):
    df = _tablo("2020-01-01", "2021-04-02", np.ones(458))
    monkeypatch.setattr(takip.veri, "guncelle", lambda *a: (df, 0))
    monkeypatch.setattr(takip, "tum_veri_secimi", lambda *a: _secim())
    klasor = tmp_path / "takip"
    takip.takip_baslat(_ayar(tmp_path), klasor, "2021-01-15")
    capsys.readouterr()
    sonuc = takip.karne(_ayar(tmp_path), klasor)
    coin = sonuc["coinler"]["DOGE"]
    assert all(k["islem_sayisi"] == 0 for k in coin["kurallar"].values())
    assert coin["islemler"] == []
    assert "Son işlemler: yok" in capsys.readouterr().out


def test_alim_yalniz_farkli_aylik_alimi_islem_sayar(monkeypatch):
    tarih = pd.date_range("2020-01-01", "2021-12-02", freq="D")
    fiyatlar = np.ones(len(tarih))
    fiyatlar[tarih == "2021-09-30"] = 2.0
    df = _tablo("2020-01-01", "2021-12-02", fiyatlar)
    p = AlimParam(u=1.001, k=0.5, l=0.5, g=0.5, t=0)
    monkeypatch.setattr(takip, "tum_veri_secimi",
                        lambda *a: {"kisa": None, "uzun": None, "alim": p})
    kayit = {"kisa": None, "uzun": None, "alim": asdict(p), "kapanis": 1.0,
             "baslangic_coin": 10.0}
    sonuc, _ = takip._coin_karnesi(df, "2021-09-15", kayit, Maliyet())
    alim = sonuc["kurallar"]["alim"]
    assert alim["islem_sayisi"] == 1
    assert len(alim["islemler"]) == 1
    assert alim["islemler"][0]["kural"] == "alım"
    assert alim["islemler"][0]["yon"] == "pahalı"


def test_yil_degisiminde_yeni_secim_ve_oran_carpimi(tmp_path, monkeypatch):
    df = _tablo("2022-01-01", "2023-02-15")
    p = KisaParam(1, 0.05, 0.5, 0.2, 1.0, 0)
    cagrilar = []

    def sec(seri, _m):
        cagrilar.append(seri.tarih[-1])
        return _secim(p if seri.tarih[-1] < "2023-01-01" else None)

    monkeypatch.setattr(takip, "tum_veri_secimi", sec)
    kayit = {"kisa": asdict(p), "uzun": None, "alim": None, "kapanis": 1.0,
             "baslangic_coin": 10.0}
    sonuc, _ = takip._coin_karnesi(df, "2022-12-15", kayit, Maliyet())
    assert "2022-12-31" in cagrilar
    for k in sonuc["kurallar"].values():
        assert np.prod([y["oran"] for y in k["yillar"]]) == pytest.approx(k["oran"], rel=1e-9)


def test_tarih_dogrulamasi_ve_geriye_donuk_etiketi(tmp_path, monkeypatch, capsys):
    df = _tablo()
    monkeypatch.setattr(takip.veri, "guncelle", lambda *a: (df, 0))
    monkeypatch.setattr(takip, "tum_veri_secimi", lambda *a: _secim())
    klasor = tmp_path / "takip"
    with pytest.raises(SystemExit) as e:
        main(["takip-baslat", "--klasor", str(klasor), "--tarih", "2020-01-01"])
    assert e.value.code != 0
    assert "bitmiş fiyat verisinde yok" in capsys.readouterr().out
    main(["takip-baslat", "--klasor", str(klasor), "--tarih", "2021-03-01"])
    kayit = json.loads((klasor / "baslangic.json").read_text(encoding="utf-8"))
    assert kayit["geriye_donuk"] is True
    capsys.readouterr()
    main(["karne", "--klasor", str(klasor)])
    assert "geriye dönük başlatıldı; gerçek ileri takip değil" in capsys.readouterr().out


# ---------- 30 günlük senaryo karnesi ----------

def _uzun_tablo(son="2021-03-01", tohum=3):
    tarih = pd.date_range("2017-11-01", son, freq="D")
    r = np.random.default_rng(tohum)
    return _tablo("2017-11-01", son, np.exp(np.cumsum(r.normal(0, 0.03, len(tarih)))))


def test_senaryo_tamamlanmis_donem_yok():
    df = _uzun_tablo(son="2021-02-10")
    k = takip.senaryo_karnesi(df, "2021-01-15")       # bitiş 14.02: henüz yok
    assert k == {"tamam": 0, "icinde": 0, "donemler": []}
    assert "DOGE: Henüz tamamlanmış 30 günlük dönem yok." in takip.senaryo_satirlari({"DOGE": k})


def test_senaryo_aralik_yalniz_donem_basina_kadarki_veriyle():
    df = _uzun_tablo()
    k = takip.senaryo_karnesi(df, "2021-01-15")       # tek dönem: 15.01 -> 14.02
    assert k["tamam"] == 1
    d = k["donemler"][0]
    assert (d["bas"], d["bitis"]) == ("2021-01-15", "2021-02-14")
    kesik = df[df["tarih"] <= "2021-01-15"]
    from kripto_sinyal.aralik import tarihsel_aralik
    r = tarihsel_aralik(list(kesik["kapanis"]))
    assert (d["alt"], d["ust"]) == pytest.approx((r["alt"], r["ust"]))
    # dönem içindeki fiyatlar değişse de aralık değişmez
    df2 = df.copy()
    df2.loc[(df2["tarih"] > "2021-01-15") & (df2["tarih"] < "2021-02-14"), "kapanis"] = 99.0
    d2 = takip.senaryo_karnesi(df2, "2021-01-15")["donemler"][0]
    assert (d2["alt"], d2["ust"]) == (d["alt"], d["ust"])


@pytest.mark.parametrize("kat, icinde", [(None, True), (5.0, False)])
def test_senaryo_icinde_ya_da_disinda(kat, icinde):
    df = _uzun_tablo()
    bas = float(df.loc[df["tarih"] == "2021-01-15", "kapanis"].iloc[0])
    df.loc[df["tarih"] == "2021-02-14", "kapanis"] = bas if kat is None else bas * kat
    k = takip.senaryo_karnesi(df, "2021-01-15")
    assert k["tamam"] == 1 and k["icinde"] == int(icinde)
    satirlar = takip.senaryo_satirlari({"DOGE": k})
    beklenen = "1'inde" if icinde else "0'ında"
    assert f"DOGE: 1 tamamlanmış dönemin {beklenen} fiyat aralıkta kaldı." in satirlar
    assert ("(içinde)" if icinde else "(dışında)") in satirlar[-1]


def test_karne_senaryo_bolumu(tmp_path, monkeypatch, capsys):
    df = _uzun_tablo()
    monkeypatch.setattr(takip.veri, "guncelle", lambda *a: (df, 0))
    monkeypatch.setattr(takip, "tum_veri_secimi", lambda *a: _secim())
    klasor = tmp_path / "takip"
    takip.takip_baslat(_ayar(tmp_path), klasor, "2021-01-15")
    capsys.readouterr()
    sonuc = takip.karne(_ayar(tmp_path), klasor)
    cikti = capsys.readouterr().out
    assert "30 günlük senaryo karnesi:" in cikti
    assert "19.11.2026 tarihinde eklendi ve donduruldu" in cikti
    assert "DOGE: 1 tamamlanmış dönemin" in cikti
    assert sonuc["senaryo"]["DOGE"]["tamam"] == 1
