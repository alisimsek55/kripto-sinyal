"""Kısa tavsiye görünümü testleri (sentetik veri, ağ yok)."""

import csv
import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from kripto_sinyal import __main__ as ana
from kripto_sinyal import haber, kur, ozet, veri
from kripto_sinyal.gecmis import CSV_BASLIK
from kripto_sinyal.ozet import Girdi, Portfoy, ozet_metni
from kripto_sinyal.rapor import tavsiye_metni

KISA = {"n": 7, "x": 0.3, "s": 0.2, "y": 0.3, "b": 1.0, "t": 90}
BOS_REF = {"satis_ref": None, "alim_ref": None, "son_satis_tarih": None, "son_islem": None}
SATIS_REF = {"satis_ref": 0.20, "alim_ref": 0.20, "son_satis_tarih": "2026-11-01",
             "son_islem": {"tarih": "2026-11-01"}}


def _analiz(kisa=KISA, alim=None, oran=0.851):
    iy = {"zincir_oran": oran, "en_iyi_yil_haric": oran, "en_iyi_yil": 2021,
          "yillar": [{"yil": 2021, "oran": oran}]}
    return {"veri_son": "2099-01-01",
            "kurallar": {ad: {"secilen": p, "ileri_yuruyus": iy} for ad, p in
                         (("kisa", kisa), ("uzun", None), ("birlesik", None), ("alim", alim))}}


def _girdi(**k):
    g = dict(coin="DOGE", analiz=_analiz(), kapanislar=[0.10] * 210, son_tarih="2026-11-14",
             simdi=0.10, canli=True, ref=BOS_REF)
    g.update(k)
    return Girdi(**g)


def _satirlar(**k):
    metin = ozet_metni(_girdi(**k))
    assert all(len(s) <= 90 for s in metin.splitlines()), metin
    return metin.splitlines()


def _duz(satirlar):
    """Sarılmış satırları tek metin yapar (alt dize aramak için)."""
    return " ".join(x.strip() for x in satirlar)


def test_islem_yok_duzen_ve_etiket_sirasi():
    s = _satirlar()
    assert s[0] == "DOGE  0,1000 $" and s[1] == ""
    assert s[2] == "BUGÜN: İşlem yok." and s[3] == ""
    assert s[4] == "KURAL (deneysel, geçmiş testte düz alımın gerisinde kaldı):"
    assert s[5] == "SAT:       0,1300 $ üstünde kapanırsa elindekinin %20'sini sat."
    assert s[6] == "           Şu ankinden %30 yukarıda."
    assert s[7].startswith("           Hesap: %20 satıp fiyat %30 düşünce geri alırsan")
    assert s[9].startswith("GERİ AL:   Sattıktan sonra fiyat satış fiyatının %30 altına inerse")
    assert s[10] == "           tamamıyla geri al. (0,1300 $'dan satarsan: 0,0910 $)"
    assert s[11] == ("YENİ PARA: Beklemeden al. Düşüşü beklemek geçmiş testte daha iyi "
                     "sonuç vermedi.")
    assert s[12] == "FİYAT:     200 günlük ortalamasının %0 üstünde."
    assert s[14] == ("SENİN DURUMUN: işlem geçmişi yok (gecmis klasörüne Binance dışa "
                     "aktarımını koy).")
    metin = "\n".join(s)
    assert "%15 gerisinde kaldı" in metin and "tavsiye --ayrinti" in metin
    assert "DİKKAT" not in metin and "Haber" not in metin and "TL" not in metin


def test_bugun_satis_seviyesi_geldi():
    s = _satirlar(kapanislar=[0.10] * 209 + [0.14], simdi=0.14)
    assert s[2] == "BUGÜN: Satış seviyesi geldi — elindekinin %20'sini sat."


def test_bugun_geri_alim_durum_kaydindan():
    s = _satirlar(ref=SATIS_REF)
    metin = _duz(s)
    assert s[2] == "BUGÜN: Geri alım seviyesi geldi — bekleyen paranın %100'üyle geri al."
    assert "SAT:       0,2300 $ üstünde" in metin  # merdiven: 0.20 * 1.15
    assert "Son satışın 0,2000 $ (01.11.2026)" in metin
    assert "0,1400 $'a inerse bekleyen satış paranın tamamıyla geri al." in metin
    assert "90 gün geri alım olmazsa" in metin
    # seviyenin üstünde: işlem yok
    s = _satirlar(ref=SATIS_REF, kapanislar=[0.15] * 210, simdi=0.15)
    assert s[2] == "BUGÜN: İşlem yok."


def test_bugun_geri_alim_gecmis_cebinden():
    pf = Portfoy(coin=1000, cep=50.0, giren=200, son=datetime(2026, 10, 20),
                 son_satis_fiyat=0.2, son_satis_zaman=datetime(2026, 10, 20))
    metin = _duz(_satirlar(portfoy=pf))
    assert "BUGÜN: Geri alım seviyesi geldi" in metin
    assert "bekleyen 50,0 USDT'nin tamamıyla geri al." in metin
    assert "Bekleyen satış paran: 50,0 USDT" in metin
    # cep yoksa geri alım yok
    pf.cep = 0.0
    assert "BUGÜN: İşlem yok." in "\n".join(_satirlar(portfoy=pf))


def test_kapali_kural():
    s = _satirlar(analiz=_analiz(kisa=None), ref=SATIS_REF)
    metin = "\n".join(s)
    assert s[2] == "BUGÜN: İşlem yok."
    assert "SAT:       Bu coin için satış kuralı önerilmiyor." in s
    assert "GERİ AL" not in metin


def test_kur_ve_tutar():
    s = _satirlar(kur=40.0, tutar=5000)
    assert s[0] == "DOGE  0,1000 $ (4,00 TL)"
    i = next(i for i, x in enumerate(s) if x.startswith("YENİ PARA:"))
    assert s[i + 1] == "           5.000 TL ≈ 125,0 USDT ≈ 1.250 DOGE"
    # kur yoksa tutar satırı yok
    metin = "\n".join(_satirlar(tutar=5000))
    assert "TL" not in metin and "USDT ≈" not in metin


def test_alim_kurali_acikken_bolge():
    alim = {"u": 1.5, "k": 0.0, "l": 1.0, "g": 1.0, "t": 365}
    metin = "\n".join(_satirlar(analiz=_analiz(alim=alim), simdi=0.08))
    assert "YENİ PARA: Şu an ucuz bölge: aylık alımına ek olarak yedeğinin %100'ünü kullan." in metin
    metin = "\n".join(_satirlar(analiz=_analiz(alim=alim), simdi=0.16))
    assert "pahalı bölge: aylık alımı yapma" in metin


def test_senin_durumun():
    pf = Portfoy(coin=10000, cep=0.0, giren=1500, son=datetime(2026, 3, 6, 2, 0))
    s = _satirlar(portfoy=pf, kur=40.0)
    metin = "\n".join(s)
    assert "SENİN DURUMUN: 10.000 DOGE ≈ 1.000 $ (40.000 TL)" in s
    assert "               Başa baş fiyatın 0,1500 $ (şu ankinden %50 yukarıda)" in s
    assert "               (işlem geçmişin 06.03.2026'ya kadar)" in s
    assert "(≈ 2.000 DOGE)" in metin and "Bekleyen satış paran" not in metin
    assert "işlem geçmişinde DOGE/USDT işlemi yok" in "\n".join(_satirlar(portfoy="kayit_yok"))
    assert "işlem geçmişi okunamadı" in "\n".join(_satirlar(portfoy="okunamadi"))


@pytest.mark.parametrize("kap, simdi, beklenen", [
    ([0.10] * 210, 0.25, "FİYAT:     ÇOK YÜKSEK — 200 günlük ortalamasının %150 üstünde."),
    ([0.10] * 210, 0.16, "FİYAT:     YÜKSEK — 200 günlük ortalamasının %60 üstünde."),
    ([0.10] * 209 + [0.135], 0.11, "FİYAT:     YÜKSEK — son 7 günde %35 yükseldi."),
    ([0.10] * 209 + [0.14], 0.16,
     "FİYAT:     YÜKSEK — 200 günlük ortalamasının %60 üstünde; son 7 günde %40 yükseldi."),
    ([0.10] * 210, 0.07, "FİYAT:     200 günlük ortalamasının %30 altında."),
    ([0.10] * 210, 0.12, "FİYAT:     200 günlük ortalamasının %20 üstünde."),
])
def test_fiyat_durumlari(kap, simdi, beklenen):
    assert beklenen in _satirlar(kapanislar=kap, simdi=simdi)


def test_dikkat_yalniz_verilen_riskler_ve_en_fazla_iki():
    riskler = [{"baslik": f"Binance hack {i} " + "uzun başlık " * 8, "kaynak": "CoinDesk"}
               for i in range(3)]
    s = _satirlar(riskler=riskler)
    assert s[3].startswith('DİKKAT: 3 ciddi haber: "Binance hack 0')
    metin = "\n".join(s)
    assert "hack 1" in metin and "hack 2" not in metin
    bos = s.index("", 3)
    assert s[bos - 1].endswith("(CoinDesk)") and s[bos + 1].startswith("KURAL (deneysel")
    assert s[bos + 2].startswith("SAT:")


def test_onemli_riskler_suzgeci():
    simdi = datetime.now(timezone.utc)
    h = [{"baslik": b, "tarih": simdi - timedelta(hours=1), "kaynak": "T"} for b in [
        "Dogecoin wallet hacked",          # RİSK + DOGE -> evet
        "Binance halts withdrawals",       # RİSK + Binance -> evet
        "Bitcoin exchange hack",           # RİSK + BTC, Binance yok -> hayır
        "Dogecoin partnership announced",  # OLUMLU -> hayır
        "Crypto lender files bankruptcy",  # RİSK + Piyasa, Binance yok -> hayır
    ]]
    secilen = haber.onemli_riskler(h, "DOGE", ["DOGE", "BTC"])
    assert sorted(x["baslik"] for x in secilen) == ["Binance halts withdrawals",
                                                     "Dogecoin wallet hacked"]
    assert haber.riskli_basliklar("DOGE", ["DOGE", "BTC"]) == []  # ağ yok


def test_btc_satiri():
    btc = {"fiyat": 64799.0, "sma": 73000.0, "c30": -0.21, "fng": 10}
    s = _satirlar(btc=btc)
    i = next(i for i, x in enumerate(s) if x.startswith("BTC  "))
    blok = " ".join(x.strip() for x in s[i:i + 2])
    assert blok.startswith("BTC  64.799 $ — 200 günlük ortalamasının %11 altında; "
                           "son 30 günde -%21; piyasa havası: Aşırı Korku (10/100).")
    assert "piyasa havası" not in "\n".join(_satirlar(btc={**btc, "fng": None}))
    assert "%11 altında" not in "\n".join(_satirlar(coin="BTC", btc=btc))


def test_onde_kalan_kural_notu():
    assert any("%12 önünde kaldı" in x for x in _satirlar(analiz=_analiz(oran=1.12)))


# ---------- Komut düzeyi ----------

def _df(baslangic=None, gun=260, fiyat=0.10):
    baslangic = baslangic or (datetime.now(timezone.utc).date() - timedelta(days=gun))
    tarihler = pd.date_range(baslangic, periods=gun, freq="D").strftime("%Y-%m-%d")
    return pd.DataFrame({"tarih": tarihler, "acilis": fiyat, "yuksek": fiyat, "dusuk": fiyat,
                         "kapanis": fiyat, "hacim": 1.0})


def _ortam(tmp_path, monkeypatch, gecmis_csv=True):
    sonuc = {"coinler": {"DOGE": _analiz(), "BTC": _analiz(kisa=None)}}
    (tmp_path / "parametreler.json").write_text(json.dumps(sonuc), encoding="utf-8")
    gk = tmp_path / "gecmis"
    gk.mkdir()
    if gecmis_csv:
        with (gk / "islemler.csv").open("w", encoding="utf-8", newline="") as f:
            y = csv.writer(f, lineterminator="\n")
            y.writerow(CSV_BASLIK)
            y.writerow(["2025-06-01 10:00:00", "DOGEUSDT", "BUY", "0.1", "500DOGE",
                        "50USDT", "0.5DOGE", "1", "", ""])
    ayar = {"aylik_tutar": 100.0, "komisyon": 0.001, "kayma": 0.0005,
            "coinler": {"DOGE": "DOGEUSDT", "BTC": "BTCUSDT"}, "ana_coin": "DOGE",
            "sonuc_dosyasi": str(tmp_path / "parametreler.json"),
            "durum_dosyasi": str(tmp_path / "durum.json"),
            "veri_klasoru": str(tmp_path / "veri"), "gecmis_klasoru": str(gk)}
    monkeypatch.setattr(ana, "ayarlari_oku", lambda: ayar)
    tablolar = {"DOGEUSDT": _df(), "BTCUSDT": _df(fiyat=60000.0)}
    monkeypatch.setattr(veri, "guncelle", lambda klasor, sembol: (tablolar[sembol], 0))
    return ayar, tablolar, gk


def _cevrimici(monkeypatch):
    monkeypatch.setattr(veri, "anlik_fiyat", lambda s: {"DOGEUSDT": 0.10, "BTCUSDT": 66000.0}[s])
    monkeypatch.setattr(kur, "kur_al", lambda *a: (40.0, "2026-11-15T20:00:00+00:00", True))
    monkeypatch.setattr(haber, "riskli_basliklar", lambda c, cl: [])
    monkeypatch.setattr(haber, "fng_cek", lambda: {"bugun": 50, "ort7": 50, "ort30": 50})


def test_komut_kisa_uctan_uca(tmp_path, monkeypatch, capsys):
    _, _, gk = _ortam(tmp_path, monkeypatch)
    _cevrimici(monkeypatch)
    ana.main(["tavsiye", "--tutar", "5000"])
    s = capsys.readouterr().out.splitlines()
    assert s[0] == "DOGE  0,1000 $ (4,00 TL)"
    metin = _duz(s)
    assert "5.000 TL ≈ 125,0 USDT ≈ 1.250 DOGE" in metin
    assert "SENİN DURUMUN: 500 DOGE ≈ 50 $ (1.998 TL)" in metin  # 49.95 $ tam sayıya yuvarlanır
    assert "Başa baş fiyatın 0,1001 $" in metin
    assert "(işlem geçmişin 01.06.2025'e kadar)" in metin
    assert "BTC  66.000 $ — 200 günlük ortalamasının %10 üstünde; son 30 günde %0; " \
           "piyasa havası: Nötr (50/100)." in metin
    assert not (gk / "rapor.txt").exists()
    assert "Haberler" not in metin and "Kanıt" not in metin

    ana.main(["tavsiye", "--coin", "btc"])
    s = capsys.readouterr().out.splitlines()
    assert s[0].startswith("BTC  66.000 $ (2.640.000 TL)")
    assert "SAT:       Bu coin için satış kuralı önerilmiyor." in s
    assert not any(x.startswith("BTC  66.000 $ —") for x in s)
    assert "işlem geçmişinde BTC/USDT işlemi yok" in "\n".join(s)


def test_cevrimdisi_hata_vermez(tmp_path, monkeypatch, capsys):
    _, tablolar, _ = _ortam(tmp_path, monkeypatch, gecmis_csv=False)

    def patlat(*a):
        raise OSError("ağ yok")

    monkeypatch.setattr(veri, "guncelle", patlat)
    monkeypatch.setattr(veri, "oku", lambda klasor, sembol, *a: tablolar[sembol])
    monkeypatch.setattr(veri, "anlik_fiyat", lambda s: None)
    ana.main(["tavsiye", "--tutar", "1000"])
    metin = capsys.readouterr().out
    dun = ozet.tarih(tablolar["DOGEUSDT"]["tarih"].iloc[-1])
    assert metin.splitlines()[0] == f"DOGE  0,1000 $ — anlık fiyat alınamadı, {dun} kapanışı"
    assert "TL" not in metin and "DİKKAT" not in metin and "piyasa havası" not in metin
    assert "SENİN DURUMUN: işlem geçmişi yok" in metin and "BTC  60.000 $" in metin


def test_tutar_sifir_reddedilir(tmp_path, monkeypatch, capsys):
    _ortam(tmp_path, monkeypatch)
    with pytest.raises(SystemExit):
        ana.main(["tavsiye", "--tutar", "0"])


def test_ayrinti_eski_cikti_ve_kur_satiri(tmp_path, monkeypatch, capsys):
    ayar, tablolar, _ = _ortam(tmp_path, monkeypatch)
    _cevrimici(monkeypatch)
    monkeypatch.setattr(ana, "_haber", lambda coinler: "SABİT HABER")
    monkeypatch.setattr(kur, "kur_al", lambda *a: None)
    ana.main(["tavsiye", "--ayrinti"])
    eski = capsys.readouterr().out.splitlines()
    sonuc = json.loads((tmp_path / "parametreler.json").read_text(encoding="utf-8"))
    beklenen = []
    for coin, sembol in ayar["coinler"].items():
        kap = list(tablolar[sembol]["kapanis"].astype(float))
        simdi = veri.anlik_fiyat(sembol)
        beklenen += tavsiye_metni(coin, sonuc["coinler"][coin], kap, simdi, "Binance anlık",
                                  BOS_REF, datetime.now(timezone.utc).date()).splitlines()
        beklenen.append("")
    beklenen += ["Haberler:", "SABİT HABER", ""]
    assert eski[:len(beklenen)] == beklenen
    assert eski[-1].startswith("Bu, geçmiş veriden çıkan kurala dayalı bir sinyaldir")
    assert not any(x.startswith("Kur:") for x in eski)

    monkeypatch.setattr(kur, "kur_al", lambda *a: (50.7, "2026-11-15T20:30:00+00:00", True))
    ana.main(["tavsiye", "--ayrinti"])
    yeni = capsys.readouterr().out.splitlines()
    assert yeni[-2] == "Kur: 1 USDT = 50.70 TL (Binance, 15.11.2026 20:30 UTC)"
    assert yeni[:-2] + yeni[-1:] == eski


# ---------- Takip: Türkçe sayı biçimi, eski kur, DİKKAT kuralı ----------

def test_turkce_sayi_bicimi():
    assert ozet.fiyat_k(0.059) == "0,0590" and ozet.fiyat_k(65034.4) == "65.034"
    assert ozet.tl(7.775) in ("7,77", "7,78") and ozet.tl(250000.2) == "250.000"
    assert ozet.usdt(98.34) == "98,3" and ozet.usdt(1234.5) == "1.234,5"
    assert ozet.adet(12345.2) == "12.345" and ozet.adet(12.5) == "12,50"
    assert ozet.adet(0.75) == "0,75" and ozet.adet(0.0015) == "0,0015"


def test_btc_kucuk_adet_virgullu():
    s = _satirlar(coin="BTC", kapanislar=[60000.0] * 210, simdi=60000.0, kur=40.0, tutar=1800000)
    assert "           1.800.000 TL ≈ 45.000,0 USDT ≈ 0,75 BTC" in s
    assert s[0] == "BTC  60.000 $ (2.400.000 TL)"


def test_eski_kur_basliga_bir_kez():
    assert _satirlar(kur=40.0, kur_eski=True)[0] == "DOGE  0,1000 $ (4,00 TL) — eski kur"
    assert "eski kur" not in "\n".join(_satirlar(kur=40.0))
    assert "eski kur" not in "\n".join(_satirlar(kur_eski=True))  # kur yoksa ek de yok


def test_komut_kisa_eski_kur(tmp_path, monkeypatch, capsys):
    _ortam(tmp_path, monkeypatch)
    _cevrimici(monkeypatch)
    monkeypatch.setattr(kur, "kur_al", lambda *a: (40.0, "2026-11-01T10:00:00+00:00", False))
    ana.main(["tavsiye"])
    s = capsys.readouterr().out.splitlines()
    assert s[0] == "DOGE  0,1000 $ (4,00 TL) — eski kur"
    assert sum("eski kur" in x for x in s) == 1


@pytest.mark.parametrize("baslik, uyarir", [
    ("DOJ moves to seize $1.2B from Binance hack, disrupts FaceStealer scam", False),
    ("North Korea's Binance hack faces U.S. crackdown as DOJ targets $1.2 billion in "
     "stolen crypto", False),
    ("Binance halts withdrawals after exploit", True),
    ("Binance to delist Dogecoin trading pairs", True),
    ("Binance hacked, hot wallet drained", True),
    ("Binance exchange outage hits traders", True),
    ("Binance settles lawsuit over outage", False),       # hukuki süreç
    ("Former Binance exec sentenced over exploit", False),
    ("Binance launches new token listing", False),        # olay kelimesi yok
    ("Dogecoin wallet hacked", True),                     # RİSK + DOGE
    ("Bitcoin exchange hacked", False),                   # RİSK ama ana coin değil, Binance yok
    ("Crypto exchange halts withdrawals", False),         # Binance yok
])
def test_dikkat_kurali(baslik, uyarir):
    h = [{"baslik": baslik, "tarih": datetime.now(timezone.utc) - timedelta(hours=1),
          "kaynak": "T"}]
    assert bool(haber.onemli_riskler(h, "DOGE", ["DOGE", "BTC"])) is uyarir


# ---------- 30 GÜN, RİSK, Hesap, Not (coinler.json) ----------

ARALIK = {"fiyat": 0.10, "alt": 0.076, "ust": 0.137, "alt_getiri": -0.24, "ust_getiri": 0.37,
          "tarih": "2026-11-17", "ufuk": 30, "pencere": 1095}


def test_otuz_gun_satiri_var_ya_da_yok():
    s = _satirlar(aralik=ARALIK)
    i = next(i for i, x in enumerate(s) if x.startswith("30 GÜN:"))
    assert s[i - 1].startswith("FİYAT:")
    blok = _duz(s[i:i + 3])
    assert blok.startswith("30 GÜN:    Son 3 yılın 30 günlük hareketleri bugüne uygulanırsa "
                           "çoğunlukla 0,0760–0,1370 $ arasında (-%24 / +%37).")
    assert "Garanti değil; daha aşağı da inebilir. (veri: 17.11.2026)" in blok
    metin = "\n".join(s)
    assert "10 seferin" not in metin and "olasılık" not in metin
    assert "30 GÜN" not in "\n".join(_satirlar())


def test_risk_satiri_yalniz_elde_coin_varsa():
    pf = Portfoy(coin=1000, cep=0.0, giren=300, son=datetime(2026, 3, 6))
    kap = [0.10] * 100 + [0.40] + [0.08] * 109     # zirve 0,40 -> dip 0,08: %80 düşüş
    s = _satirlar(portfoy=pf, kur=10.0, kapanislar=kap)
    i = next(i for i, x in enumerate(s) if x.startswith("RİSK:"))
    assert s[i] == "RİSK:      DOGE %50 düşerse elindekinin değeri ≈ 500 TL olur."
    assert s[i + 1] == "           Geçmişte DOGE zirvesinden %80 düştü."
    # kur yoksa $
    s = _satirlar(portfoy=pf, kapanislar=kap)
    assert "RİSK:      DOGE %50 düşerse elindekinin değeri ≈ 50 $ olur." in s
    # elde coin yoksa ya da geçmiş yoksa RİSK yok
    assert "RİSK" not in "\n".join(_satirlar())
    assert "RİSK" not in "\n".join(_satirlar(portfoy="kayit_yok"))
    pf.coin = 0.0
    assert "RİSK" not in "\n".join(_satirlar(portfoy=pf))


def test_hesap_satiri_tam_ve_yarim_nakit():
    metin = _duz(_satirlar())
    assert ("Hesap: %20 satıp fiyat %30 düşünce geri alırsan toplam DOGE'n ≈ %8,5 artar; "
            "fiyat %30 yükselip geri alırsan ≈ %4,7 azalır.") in metin
    yarim = {**KISA, "b": 0.5}
    metin = _duz(_satirlar(analiz=_analiz(kisa=yarim)))
    assert "fiyat %30 düşünce paranın %50'siyle geri alırsan toplam DOGE'n ≈ %5,8 azalır" in metin
    assert "Kalan para nakitte kalır." in metin
    assert "Hesap" not in "\n".join(_satirlar(analiz=_analiz(kisa=None)))


def test_kural_etiketi_onde_ise():
    s = _satirlar(analiz=_analiz(oran=1.12))
    assert "KURAL (deneysel; geçmiş testte düz alımı geçti, garanti değil):" in s
    assert "KURAL" not in "\n".join(_satirlar(analiz=_analiz(kisa=None)))


@pytest.mark.parametrize("gecen, ek", [(4, "4'ünde"), (2, "2'sinde"), (0, "0'ında"),
                                       (6, "6'sında"), (9, "9'unda")])
def test_not_coinler_ozeti(gecen, ek):
    co = {"ozet": {"kisa": {"gecen": gecen, "toplam": 11, "geometrik_ortalama": 0.9}}}
    metin = _duz(_satirlar(coinler_ozet=co))
    assert (f"Not: Satış kuralı DOGE'de düz aylık alımın %15 gerisinde kaldı; aynı yöntem "
            f"11 coinde denendi, {ek} düz alımı geçti. Bunlar kural çıktısıdır, yatırım "
            "tavsiyesi değildir.") in metin
    # bozuk ya da eksik dosya: eski Not
    metin = _duz(_satirlar(coinler_ozet={"ozet": {}}))
    assert "Not: Satış kuralı geçmiş testte düz düzenli alımın %15 gerisinde kaldı." in metin


def test_komut_kisa_coinler_json_ve_aralik(tmp_path, monkeypatch, capsys):
    ayar, tablolar, _ = _ortam(tmp_path, monkeypatch, gecmis_csv=False)
    _cevrimici(monkeypatch)
    ana.main(["tavsiye"])
    metin = _duz(capsys.readouterr().out.splitlines())
    assert "30 GÜN" not in metin                  # 260 gün: aralık için kısa
    assert "aynı yöntem" not in metin             # coinler.json yok
    assert "RİSK" not in metin                    # işlem geçmişi yok
    co = {"tarih": "2026-11-19", "coinler": {},
          "ozet": {"kisa": {"gecen": 3, "toplam": 11, "geometrik_ortalama": 0.9}}}
    (tmp_path / "coinler.json").write_text(json.dumps(co), encoding="utf-8")
    tablolar["DOGEUSDT"] = _df(gun=1300)
    ana.main(["tavsiye"])
    metin = _duz(capsys.readouterr().out.splitlines())
    assert "aynı yöntem 11 coinde denendi, 3'ünde düz alımı geçti." in metin
    assert "30 GÜN:    Son 3 yılın 30 günlük hareketleri" in metin


def test_otuz_gun_yuzdeleri_su_anki_fiyata_gore():
    metin = _duz(_satirlar(aralik=ARALIK, simdi=0.08))
    assert "0,0760–0,1370 $ arasında (-%5 / +%71)." in metin


def test_satis_seviyesinin_ustundeki_yuzde_seviyeye_gore():
    metin = _duz(_satirlar(simdi=0.26))  # satış seviyesi 0.13: fiyat bunun iki katı
    assert "Fiyat şu an bu seviyenin %100 üstünde." in metin


def test_kisa_kapanis_gecmisi_yetersizse_islem_yok_denmez():
    metin = ozet_metni(_girdi(kapanislar=[0.1] * 7))
    assert "veri yetersiz" in metin.lower()
    assert "İşlem yok" not in metin and "kuralı önerilmiyor" not in metin


def test_ayrinti_eksik_sma_ile_yanlis_seviye_vermez():
    metin = tavsiye_metni("DOGE", _analiz(), [0.1] * 7, 0.1, "test", BOS_REF,
                          datetime.now(timezone.utc).date())
    assert "200 günlük kapanış gerekli" in metin and "sinyal hesaplanmadı" in metin
    assert "elindekinin" not in metin


@pytest.mark.parametrize("ayrinti", [False, True])
def test_tavsiye_bos_onbellek_ve_ag_yokken(tmp_path, monkeypatch, capsys, ayrinti):
    _ortam(tmp_path, monkeypatch, gecmis_csv=False)

    def ag_yok(*a):
        raise OSError("ağ yok")

    monkeypatch.setattr(veri, "guncelle", ag_yok)
    ana.main(["tavsiye"] + (["--ayrinti"] if ayrinti else []))
    assert "fiyat verisi yok" in capsys.readouterr().out


@pytest.mark.parametrize("sorun", ["eski", "bosluk", "bozuk_csv", "sifir", "nan"])
@pytest.mark.parametrize("ayrinti", [False, True])
def test_guvenilmez_veriden_gunluk_sinyal_verilmez(tmp_path, monkeypatch, capsys,
                                               sorun, ayrinti):
    ayar, tablolar, _ = _ortam(tmp_path, monkeypatch, gecmis_csv=False)
    _cevrimici(monkeypatch)
    dun = datetime.now(timezone.utc).date() - timedelta(days=1)
    df = _df(baslangic=dun - timedelta(days=259))
    df.loc[df.index[-1], "kapanis"] = 0.20  # normalde SAT sinyali
    if sorun == "eski":
        df["tarih"] = (pd.to_datetime(df["tarih"]) - pd.Timedelta(days=3)).dt.strftime("%Y-%m-%d")
    elif sorun == "bosluk":
        df = df.drop(df.index[-3]).reset_index(drop=True)
    elif sorun in ("sifir", "nan"):
        df.loc[df.index[-1], "kapanis"] = 0 if sorun == "sifir" else float("nan")
    else:
        klasor = tmp_path / "veri"
        klasor.mkdir()
        for sembol in tablolar:
            veri.csv_yolu(klasor, sembol).write_text("", encoding="utf-8")

        def ag_yok(*a):
            raise OSError("ağ yok")

        monkeypatch.setattr(veri, "guncelle", ag_yok)
    for sembol in tablolar:
        tablolar[sembol] = df
    ana.main(["tavsiye"] + (["--ayrinti"] if ayrinti else []))
    metin = capsys.readouterr().out
    assert "sinyal hesaplanmadı" in metin
    assert "elindekinin" not in metin and "İşlem yok" not in metin


def test_bozuk_islem_kaydi_sessizce_yok_sayilmaz(tmp_path, monkeypatch, capsys):
    ayar, _, _ = _ortam(tmp_path, monkeypatch, gecmis_csv=False)
    _cevrimici(monkeypatch)
    (tmp_path / "durum.json").write_text("{", encoding="utf-8")
    ozet.komut_kisa(ayar)
    metin = capsys.readouterr().out
    assert "işlem kaydı okunamadı" in metin
    assert "elindekinin" not in metin


def test_yeni_geri_alim_eski_csv_nakdinden_tekrar_al_onermez():
    pf = Portfoy(coin=1000, cep=50, giren=200, son=datetime(2025, 1, 1),
                 son_satis_fiyat=0.2, son_satis_zaman=datetime(2025, 1, 1))
    ref = {"satis_ref": None, "alim_ref": 0.14, "son_satis_tarih": "2025-01-01",
           "son_islem": {"tur": "al", "yuzde": 100, "tarih": "2025-01-02", "fiyat": 0.14}}
    metin = ozet_metni(_girdi(ref=ref, portfoy=pf))
    assert "BUGÜN: İşlem yok." in metin
    assert "Geri alım seviyesi geldi" not in metin
    assert "bekleyen 50,0 USDT'nin" not in metin


@pytest.mark.parametrize("tutar", ["nan", "inf", "-inf"])
def test_sonlu_olmayan_tutar_reddedilir(tmp_path, monkeypatch, tutar):
    _ortam(tmp_path, monkeypatch)
    with pytest.raises(SystemExit) as e:
        ana.main(["tavsiye", "--tutar=" + tutar])
    assert e.value.code == 2


def test_eski_manuel_alim_yeni_csv_nakdini_gizlemez():
    pf = Portfoy(coin=1000, cep=50, giren=200, son=datetime(2025, 2, 1),
                 son_satis_fiyat=0.2, son_satis_zaman=datetime(2025, 2, 1))
    ref = {"satis_ref": None, "alim_ref": 0.14, "son_satis_tarih": "2025-01-01",
           "son_islem": {"tur": "al", "yuzde": 100, "tarih": "2025-01-02", "fiyat": 0.14}}
    metin = _duz(_satirlar(ref=ref, portfoy=pf))
    assert "bekleyen 50,0 USDT'nin tamamıyla geri al." in metin


def test_btc_otuz_gun_isareti_yuzde_isaretinden_once():
    btc = {"fiyat": 60000, "sma": None, "c30": 0.05, "fng": None}
    assert "son 30 günde +%5" in "\n".join(_satirlar(btc=btc))
