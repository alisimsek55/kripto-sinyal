"""Gerçek işlem geçmişi karşılaştırmasının sentetik testleri."""

import csv
from datetime import datetime

import pandas as pd
import pytest

from kripto_sinyal import gecmis
from kripto_sinyal.__main__ import main
from kripto_sinyal.gecmis import (CSV_BASLIK, GecmisHatasi, Islem, analiz_metni,
                                  csvleri_oku, defteri_hesapla, gecmis_raporu,
                                  sonuclari_hesapla)
from kripto_sinyal.simulasyon import Maliyet


def _satir(tarih, parite, yon, fiyat, executed, amount, fee, emir):
    return [tarih, parite, yon, str(fiyat), executed, amount, fee, emir, "", ""]


def _csv(yol, satirlar, baslik=CSV_BASLIK):
    with yol.open("w", encoding="utf-8", newline="") as f:
        yazici = csv.writer(f, lineterminator="\n")
        yazici.writerow(baslik)
        yazici.writerows(satirlar)


def _islem(tarih, yon, fiyat, executed, amount, fee=0.0, fee_asset="DOGE", emir="1",
           parite="DOGEUSDT"):
    return Islem(datetime.strptime(tarih, "%Y-%m-%d %H:%M:%S"), parite, yon, fiyat,
                 executed, "DOGE", amount, "USDT", fee, fee_asset, emir, "x.csv", 0)


def _fiyatlar(tarihler, fiyat=10.0):
    return pd.DataFrame({"tarih": tarihler, "acilis": [fiyat] * len(tarihler),
                         "yuksek": [fiyat] * len(tarihler), "dusuk": [fiyat] * len(tarihler),
                         "kapanis": [fiyat] * len(tarihler), "hacim": [1.0] * len(tarihler)})


def test_h1_ayristirma_sira_ucretler_ve_ayni_satirlar(tmp_path):
    ayni = _satir("2024-01-01 10:00:00", "DOGEUSDT", "BUY", 0.1,
                  "250DOGE", "25USDT", "0.25DOGE", "a")
    satirlar = [
        _satir("2024-01-03 10:00:00", "DOGEUSDT", "SELL", 0.2,
               "10DOGE", "2USDT", "0.002BNB", "c"),
        _satir("2024-01-02 10:00:00", "DOGEUSDT", "BUY", 0.1,
               "20DOGE", "2USDT", "0.002USDT", "b"),
        ayni,
        ayni,
    ]
    _csv(tmp_path / "islemler.csv", satirlar)
    icerik = (tmp_path / "islemler.csv").read_text(encoding="utf-8")
    (tmp_path / "islemler.csv").write_text(icerik, encoding="utf-8-sig")
    okunan = csvleri_oku(tmp_path)
    assert len(okunan) == 4
    assert [x.sira for x in okunan[:2]] == [3, 2]
    assert okunan[0].executed == 250
    assert okunan[0].base == "DOGE" and okunan[0].fee_asset == "DOGE"
    assert okunan[2].fee_asset == "USDT"
    assert okunan[3].fee_asset == "BNB"


def test_h2_elle_hesaplanan_defter():
    islemler = [
        _islem("2024-01-01 00:00:00", "BUY", 10, 10, 100, emir="1"),
        _islem("2024-01-02 00:00:00", "BUY", 10, 5, 50, emir="2"),
        _islem("2024-01-03 00:00:00", "SELL", 12, 15, 180, emir="3"),
        _islem("2024-01-04 00:00:00", "BUY", 5, 20, 100, emir="4"),
        _islem("2024-01-05 00:00:00", "BUY", 10, 10, 100, emir="5"),
    ]
    d = defteri_hesapla(islemler, "DOGE")
    assert d.coin == pytest.approx(30)
    assert d.cep == pytest.approx(0)
    assert d.giren == pytest.approx(170)
    assert [(x.tutar, x.fiyat) for x in d.girisler] == [(100, 10), (50, 10), (20, 10)]


def test_h3_satmadan_sonucu_ve_tur_kimligi():
    islemler = [
        _islem("2024-01-01 00:00:00", "BUY", 10, 10, 100, emir="1"),
        _islem("2024-01-02 00:00:00", "BUY", 10, 5, 50, emir="2"),
        _islem("2024-01-03 00:00:00", "SELL", 12, 15, 180, emir="3"),
        _islem("2024-01-04 00:00:00", "BUY", 5, 20, 100, emir="4"),
        _islem("2024-01-05 00:00:00", "BUY", 10, 10, 100, emir="5"),
    ]
    a = sonuclari_hesapla(defteri_hesapla(islemler, "DOGE"),
                          _fiyatlar(["2024-01-01", "2024-01-31"]), Maliyet(0, 0, 0))
    assert a.satmadan.coin == pytest.approx(17)
    assert a.gercek.coin - a.satmadan.coin == pytest.approx(13)
    assert sum(x.alinan_coin - x.satilan for x in a.defter.turlar) == pytest.approx(13)
    assert a.kimlik_farki == pytest.approx(0, abs=1e-12)


def test_h4_duz_aylik_alim_aylar_tarihler_ve_sabit_fiyat():
    islemler = [
        _islem("2024-01-15 12:00:00", "BUY", 10, 10, 100, 0.01, "DOGE", "1"),
        _islem("2024-03-10 12:00:00", "BUY", 10, 10, 100, 0.01, "DOGE", "2"),
    ]
    fiyatlar = _fiyatlar(["2024-01-01", "2024-01-15", "2024-02-01", "2024-03-01", "2024-03-31"])
    a = sonuclari_hesapla(defteri_hesapla(islemler, "DOGE"), fiyatlar,
                          Maliyet(0, 0.001, 0))
    assert a.ay_sayisi == 3
    assert a.aylik_alim_tarihleri == ["2024-01-15", "2024-02-01", "2024-03-01"]
    assert a.gercek.coin == pytest.approx(19.98)
    assert a.satmadan.coin == pytest.approx(19.98)
    assert a.aylik.coin == pytest.approx(19.98)


def test_h5_onceki_coin_ve_uyari_metni():
    d = defteri_hesapla([
        _islem("2024-01-01 00:00:00", "SELL", 10, 12, 120, emir="1")
    ], "DOGE")
    assert d.onceki_coin == pytest.approx(12)
    assert d.coin == 0
    a = sonuclari_hesapla(d, _fiyatlar(["2024-01-01", "2024-01-31"]), Maliyet(0, 0, 0))
    metin = analiz_metni(a)
    assert "Dosya bu coinlerin nereden geldiğini göstermiyor" in metin
    assert "daha eski geçmiş eksik olabilir" in metin


def test_h6_dosya_hatalari_atlama_ve_bos_klasor(tmp_path, monkeypatch, capsys):
    bos = tmp_path / "bos"
    bos.mkdir()
    with pytest.raises(GecmisHatasi, match="CSV bulunamadı"):
        csvleri_oku(bos)
    with pytest.raises(SystemExit) as cikis:
        main(["gecmis", "--klasor", str(bos)])
    assert cikis.value.code != 0
    assert "Binance işlem geçmişi" in capsys.readouterr().out

    hatali = tmp_path / "hatali"
    hatali.mkdir()
    _csv(hatali / "x.csv", [], ["yanlış"])
    with pytest.raises(GecmisHatasi, match="x.csv"):
        csvleri_oku(hatali)

    cakis = tmp_path / "cakis"
    cakis.mkdir()
    _csv(cakis / "a.csv", [_satir("2024-01-01 00:00:00", "DOGEUSDT", "BUY", 10,
                                        "1DOGE", "10USDT", "0DOGE", "1"),
                                  _satir("2024-01-03 00:00:00", "DOGEUSDT", "BUY", 10,
                                        "1DOGE", "10USDT", "0DOGE", "2")])
    _csv(cakis / "b.csv", [_satir("2024-01-02 00:00:00", "DOGEUSDT", "BUY", 10,
                                        "1DOGE", "10USDT", "0DOGE", "3")])
    with pytest.raises(GecmisHatasi, match="a.csv ve b.csv"):
        csvleri_oku(cakis)

    karisik = tmp_path / "karisik"
    karisik.mkdir()
    _csv(karisik / "x.csv", [
        _satir("2024-01-02 00:00:00", "ETHBTC", "BUY", 1, "1ETH", "1BTC", "0ETH", "2"),
        _satir("2024-01-01 00:00:00", "DOGEUSDT", "BUY", 10, "1DOGE", "10USDT", "0DOGE", "1"),
    ])
    monkeypatch.setattr(gecmis, "fiyat_verisini_yukle",
                        lambda ayar, coin: _fiyatlar(["2024-01-01", "2024-01-31"]))
    ayar = {"coinler": {"DOGE": "DOGEUSDT"}, "aylik_tutar": 100,
            "komisyon": 0, "kayma": 0}
    metin, _ = gecmis_raporu(ayar, karisik)
    assert "Uyarı: Atlanan pariteler: ETHBTC (1 satır)." in metin


def test_h7_fifo_iki_satis_kismi_tur():
    islemler = [
        _islem("2024-01-01 00:00:00", "BUY", 10, 20, 200, emir="al0"),
        _islem("2024-01-02 00:00:00", "SELL", 10, 5, 50, emir="sat1"),
        _islem("2024-01-03 00:00:00", "SELL", 10, 5, 50, emir="sat2"),
        _islem("2024-01-04 00:00:00", "BUY", 5, 12, 60, emir="al1"),
        _islem("2024-01-05 00:00:00", "BUY", 5, 2, 10, emir="al2"),
    ]
    d = defteri_hesapla(islemler, "DOGE")
    ilk, ikinci = d.turlar
    assert ilk.harcanan_usdt == pytest.approx(50)
    assert ilk.alinan_coin == pytest.approx(10)
    assert ilk.durum == "tamamı geri alındı"
    assert ikinci.harcanan_usdt == pytest.approx(20)
    assert ikinci.alinan_coin == pytest.approx(4)
    assert ikinci.bekleyen_usdt == pytest.approx(30)
    assert ikinci.durum == "kısmen (30.00 USDT cepte)"


# ---------- Ücret durumları (Hiç satmasaydın) ----------

def _ucret_islemi(tarih, yon, executed, amount, fee, fee_asset, emir):
    return _islem(tarih, yon, 10, executed, amount, fee, fee_asset, emir)


@pytest.mark.parametrize("fee, varlik, net_coin, maliyet", [
    (0.01, "DOGE", 9.99, 100.0),    # baz ücreti: coin azalır
    (0.1, "USDT", 10.0, 100.1),     # kotasyon ücreti: maliyet artar
    (0.0005, "BNB", 10.0, 100.0),   # üçüncü varlık: hiçbir şey değişmez
])
def test_ucret_turleri_tek_alim(fee, varlik, net_coin, maliyet):
    d = defteri_hesapla([_ucret_islemi("2024-01-01 00:00:00", "BUY", 10, 100, fee, varlik, "1")],
                        "DOGE")
    a = sonuclari_hesapla(d, _fiyatlar(["2024-01-01", "2024-01-31"]), Maliyet(0, 0, 0))
    assert d.coin == pytest.approx(net_coin)
    assert d.giren == pytest.approx(maliyet)
    assert a.satmadan.coin == pytest.approx(net_coin)  # tamamı dışarıdan: net coinin hepsi
    assert d.komisyon_diger == ({"BNB": 0.0005} if varlik == "BNB" else {})
    assert a.kimlik_farki == pytest.approx(0, abs=1e-9)


@pytest.mark.parametrize("fee, varlik, net_coin, maliyet", [
    (0.01, "DOGE", 9.99, 100.0),
    (0.1, "USDT", 10.0, 100.1),
    (0.0005, "BNB", 10.0, 100.0),
])
def test_ucret_turleri_cepten_kismen_odenen_alim(fee, varlik, net_coin, maliyet):
    islemler = [
        _ucret_islemi("2024-01-01 00:00:00", "BUY", 10, 100, 0, "DOGE", "1"),
        _ucret_islemi("2024-01-02 00:00:00", "SELL", 5, 60, 0, "USDT", "2"),   # cep 60
        _ucret_islemi("2024-01-03 00:00:00", "BUY", 10, 100, fee, varlik, "3"),
    ]
    d = defteri_hesapla(islemler, "DOGE")
    a = sonuclari_hesapla(d, _fiyatlar(["2024-01-01", "2024-01-31"]), Maliyet(0, 0, 0))
    disaridan = maliyet - 60
    assert d.cep == pytest.approx(0)
    assert d.giren == pytest.approx(100 + disaridan)
    assert d.coin == pytest.approx(5 + net_coin)
    assert a.satmadan.coin == pytest.approx(10 + net_coin * disaridan / maliyet)
    assert a.kimlik_farki == pytest.approx(0, abs=1e-9)


# ---------- TL karşılıkları ----------

def _tl_klasoru(tmp_path, monkeypatch):
    k = tmp_path / "g"
    k.mkdir()
    _csv(k / "x.csv", [
        _satir("2024-01-01 00:00:00", "DOGEUSDT", "BUY", 10, "10DOGE", "100USDT", "0DOGE", "1"),
        _satir("2024-01-02 00:00:00", "DOGEUSDT", "SELL", 12, "5DOGE", "60USDT", "0USDT", "2"),
    ])
    monkeypatch.setattr(gecmis, "fiyat_verisini_yukle",
                        lambda ayar, coin: _fiyatlar(["2024-01-01", "2024-01-31"]))
    return k, {"coinler": {"DOGE": "DOGEUSDT"}, "aylik_tutar": 100, "komisyon": 0, "kayma": 0}


def test_gecmis_tl_satirlari(tmp_path, monkeypatch):
    k, ayar = _tl_klasoru(tmp_path, monkeypatch)
    duz, _ = gecmis_raporu(ayar, k)
    assert "TL" not in duz
    metin, _ = gecmis_raporu(ayar, k, 50.0)
    assert (k / "rapor.txt").read_text(encoding="utf-8") == metin
    s = metin.splitlines()
    i = next(i for i, x in enumerate(s) if x.startswith("Giren:"))
    assert s[i + 1] == ("TL karşılıkları bugünkü kurla hesaplandı (1 USDT = 50.00 TL); "
                        "geçmişteki alımların o günkü TL maliyetini göstermez.")
    assert "Gerçekte yaptığın: 5.00 DOGE; 110.00 USDT; kâr/zarar +10.00 USDT (%10.00); " \
           "değer ≈ 5.500 TL" in s
    assert sum(x.endswith(" TL") for x in s) == 3
    # USDT sayıları değişmez: TL ekleri çıkarılınca düz metinle aynı
    temiz = [x.split("; değer ≈")[0] for x in s if not x.startswith("TL karşılıkları")]
    assert temiz == duz.splitlines()


def test_gecmis_komutu_kurla(tmp_path, monkeypatch, capsys):
    from kripto_sinyal import kur
    k, ayar = _tl_klasoru(tmp_path, monkeypatch)
    monkeypatch.setattr("kripto_sinyal.__main__.ayarlari_oku", lambda: ayar)
    monkeypatch.setattr(kur, "kur_al", lambda *a: (50.0, "2026-11-15T20:00:00+00:00", True))
    main(["gecmis", "--klasor", str(k)])
    assert "değer ≈ 5.500 TL" in capsys.readouterr().out
    monkeypatch.setattr(kur, "kur_al", lambda *a: None)
    main(["gecmis", "--klasor", str(k)])
    assert "TL" not in capsys.readouterr().out
