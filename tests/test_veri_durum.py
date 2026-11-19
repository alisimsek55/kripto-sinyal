"""Veri ayrıştırma, işlem kaydı ve metin testleri (ağ yok)."""

from datetime import date

import pytest

from kripto_sinyal import durum
from kripto_sinyal import __main__ as ana
from kripto_sinyal.rapor import tavsiye_metni, yuzde_ek
from kripto_sinyal.veri import GUN_MS, bosluklar, oku, satirlara_cevir


def _kline(ms, fiyat):
    return [ms, str(fiyat), str(fiyat), str(fiyat), str(fiyat), "1", ms + GUN_MS - 1]


def test_bitmemis_gun_atilir():
    gun0 = 1_700_006_400_000 - 1_700_006_400_000 % GUN_MS
    ham = [_kline(gun0, 1), _kline(gun0 + GUN_MS, 2), _kline(gun0 + 2 * GUN_MS, 3)]
    simdi = gun0 + 2 * GUN_MS + 5_000_000  # üçüncü gün henüz bitmedi
    df = satirlara_cevir(ham, simdi)
    assert list(df["kapanis"]) == [1.0, 2.0]
    assert bosluklar(df) == []


def test_onbellekten_bugunun_mumu_atilir(tmp_path):
    tablo = "tarih,acilis,yuksek,dusuk,kapanis,hacim\n2026-01-01,1,1,1,1,1\n2026-01-02,2,2,2,2,1\n"
    (tmp_path / "BTCUSDT_1d.csv").write_text(tablo, encoding="utf-8")
    df = oku(tmp_path, "BTCUSDT", date(2026, 1, 2))
    assert list(df["tarih"]) == ["2026-01-01"]


def test_onbellek_dunle_bitiyorsa_degismez(tmp_path):
    tablo = "tarih,acilis,yuksek,dusuk,kapanis,hacim\n2026-01-01,1,1,1,1,1\n2026-01-02,2,2,2,2,1\n"
    (tmp_path / "BTCUSDT_1d.csv").write_text(tablo, encoding="utf-8")
    df = oku(tmp_path, "BTCUSDT", date(2026, 1, 3))
    assert list(df["tarih"]) == ["2026-01-01", "2026-01-02"]


def test_islem_kaydi_ve_referans(tmp_path):
    yol = tmp_path / "durum.json"
    with pytest.raises(ValueError):
        durum.ekle(yol, "sat", "DOGE", 0.3, None, None, "kisa")
    durum.ekle(yol, "sat", "doge", 0.30, 20, None, "kisa", "2026-01-05")
    durum.ekle(yol, "al", "DOGE", 0.10, None, 100, "duzenli", "2026-01-06")  # sayılmaz
    r = durum.kisa_referans(durum.oku(yol), "DOGE")
    assert r["satis_ref"] == 0.30 and r["alim_ref"] == 0.30
    durum.ekle(yol, "al", "DOGE", 0.24, 50, None, "kisa", "2026-01-10")
    r = durum.kisa_referans(durum.oku(yol), "DOGE")
    assert r["satis_ref"] is None and r["alim_ref"] == 0.24
    assert durum.kisa_referans(durum.oku(yol), "BTC")["alim_ref"] is None


def test_yuzde_ekleri():
    assert yuzde_ek(0.20, "i") == "%20'sini"
    assert yuzde_ek(0.30, "i") == "%30'unu"
    assert yuzde_ek(1.0, "ile") == "%100'üyle"
    assert yuzde_ek(0.50, "ile") == "%50'siyle"
    assert yuzde_ek(0.25, "i") == "%25'ini"


def _analiz(kisa, uzun, oran):
    iy = {"zincir_oran": oran, "en_iyi_yil_haric": oran, "en_iyi_yil": 2021,
          "yillar": [{"yil": 2021, "oran": oran}]}
    return {"kurallar": {"kisa": {"secilen": kisa, "ileri_yuruyus": iy},
                         "uzun": {"secilen": uzun, "ileri_yuruyus": iy},
                         "birlesik": {"secilen": None, "ileri_yuruyus": iy}}}


def test_tavsiye_seviyeleri_ve_uyari():
    kisa = {"n": 7, "x": 0.4, "s": 0.2, "y": 0.25, "b": 0.5, "t": 0}
    uzun = {"u": 2.0, "sl": 0.25, "l": 0.75, "bl": 0.5, "t": 0}
    kap = [1.0] * 200  # 200 günlük ortalama = 1
    ref = {"satis_ref": None, "alim_ref": None, "son_satis_tarih": None, "son_islem": None}
    m = tavsiye_metni("DOGE", _analiz(kisa, uzun, 0.8), kap, 1.0, "test", ref, date(2026, 1, 1))
    assert "1.40 $'ın üstünde" in m            # 7 gün önceki 1.0 * 1.4
    assert "geri alım seviyesi 1.05 $" in m    # 1.4 * 0.75
    assert "Fiyat 2.00 $'ı geçerse" in m and "0.7500 $'ın altına" in m
    assert "GEÇEMEDİ" in m and "UYARI" in m
    # gerçek satış kaydı varsa geri alım ona göre
    ref = {"satis_ref": 2.0, "alim_ref": 2.0, "son_satis_tarih": "2025-12-01",
           "son_islem": {"tarih": "2025-12-01"}}
    m = tavsiye_metni("DOGE", _analiz(kisa, uzun, 1.2), kap, 1.0, "test", ref, date(2026, 1, 1))
    assert "1.50 $'a düşerse" in m
    assert "2.40 $'ın üstünde" in m  # merdiven: 2.0 * 1.2
    assert "UYARI" not in m


@pytest.mark.parametrize("alan, deger", [
    ("fiyat", float("nan")), ("fiyat", float("inf")),
    ("yuzde", 0), ("yuzde", -10), ("yuzde", 101), ("yuzde", float("nan")),
    ("miktar", -1), ("miktar", 0), ("miktar", float("inf")),
    ("tarih", "2026-99-01"),
])
def test_gecersiz_islem_dosyaya_yazilmaz(tmp_path, alan, deger):
    hedef = tmp_path / "durum.json"
    args = dict(tur="sat", coin="DOGE", fiyat=0.2, yuzde=20, miktar=None,
                kural="kisa", tarih="2025-01-01")
    if alan == "miktar":
        args["yuzde"] = None
    args[alan] = deger
    with pytest.raises(ValueError):
        durum.ekle(hedef, **args)
    assert not hedef.exists()


def test_islem_yeni_klasore_yazilir(tmp_path):
    hedef = tmp_path / "ozel" / "durum.json"
    durum.ekle(hedef, "sat", "DOGE", 0.2, 20, None, "kisa")
    assert len(durum.oku(hedef)["islemler"]) == 1


@pytest.mark.parametrize("ag_yok", [False, True])
def test_veri_ilk_calistirmada_bos_veya_cevrimdisi(tmp_path, monkeypatch, capsys, ag_yok):
    from kripto_sinyal import veri

    def istek(*a):
        if ag_yok:
            raise OSError("ağ yok")
        return []

    monkeypatch.setattr(veri, "_istek", istek)
    ana.komut_veri({"coinler": {"DOGE": "DOGEUSDT"}, "veri_klasoru": str(tmp_path)})
    assert "DOGE:" in capsys.readouterr().out


def test_geritest_veri_yokken_kayitli_sonucu_silmez(tmp_path, capsys):
    hedef = tmp_path / "parametreler.json"
    hedef.write_text('{"coinler": {"DOGE": {}}}', encoding="utf-8")
    once = hedef.read_bytes()
    ana.komut_geritest({"coinler": {"DOGE": "DOGEUSDT"}, "veri_klasoru": str(tmp_path),
                       "sonuc_dosyasi": str(hedef), "aylik_tutar": 100,
                       "komisyon": 0.001, "kayma": 0.0005})
    assert hedef.read_bytes() == once
    assert "kaydedilmedi" in capsys.readouterr().out


@pytest.mark.parametrize("fiyat", ["NaN", "Infinity", "0", "-1"])
def test_gecersiz_anlik_fiyat_yerine_none(monkeypatch, fiyat):
    from kripto_sinyal import veri
    monkeypatch.setattr(veri, "_istek", lambda *a: {"price": fiyat})
    assert veri.anlik_fiyat("DOGEUSDT") is None
