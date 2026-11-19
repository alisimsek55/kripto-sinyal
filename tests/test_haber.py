import json
from datetime import datetime, timedelta, timezone

import pytest
import requests

from kripto_sinyal import haber

SIMDI = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)


def _tarih(gun_once):
    t = SIMDI - timedelta(days=gun_once)
    return t.strftime("%a, %d %b %Y %H:%M:%S +0000")


def _rss(ogeler):
    items = "".join(
        f"<item><title>{b}</title><pubDate>{_tarih(g)}</pubDate>"
        f"<description>govde</description></item>"
        for b, g in ogeler
    )
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>{items}</channel></rss>'


def test_rss_ayristir():
    xml = _rss([("Bitcoin rises", 1), ("Dogecoin news", 2)])
    r = haber.rss_ayristir(xml, "Test")
    assert [x["baslik"] for x in r] == ["Bitcoin rises", "Dogecoin news"]
    assert r[0]["kaynak"] == "Test"
    assert r[0]["tarih"] == SIMDI - timedelta(days=1)


def test_rss_bozuk_tarih_atlanir():
    xml = "<rss><channel><item><title>A</title><pubDate>bozuk</pubDate></item></channel></rss>"
    assert haber.rss_ayristir(xml, "T") == []


def test_kategori():
    assert haber.kategori("Exchange hacked for $50M") == "RİSK"
    assert haber.kategori("SEC lawsuit against firm") == "RİSK"
    assert haber.kategori("Spot ETF approval expected") == "OLUMLU"
    assert haber.kategori("Bitcoin price today") == "GENEL"


def test_coin_ilgisi():
    c = ["BTC", "DOGE"]
    assert haber.hangi_coin("Bitcoin hits new level", c) == "BTC"
    assert haber.hangi_coin("Dogecoin jumps", c) == "DOGE"
    assert haber.hangi_coin("Musk says X payments coming", c) == "DOGE"
    assert haber.hangi_coin("Ethereum upgrade", c) is None
    assert haber.hangi_coin("Crypto exchange hacked, funds stolen", c) == "Piyasa"
    assert haber.hangi_coin("Cooking recipes", c) is None


def test_fng_etiket_siniri():
    assert haber.fng_etiket(10) == "Aşırı Korku"
    assert haber.fng_etiket(30) == "Korku"
    assert haber.fng_etiket(50) == "Nötr"
    assert haber.fng_etiket(60) == "Açgözlülük"
    assert haber.fng_etiket(90) == "Aşırı Açgözlülük"


def test_fng_ortalama():
    veri = {"data": [{"value": str(v)} for v in range(1, 31)]}  # 1 en yeni
    s = haber.fng_ayristir(veri)
    assert s["bugun"] == 1
    assert s["ort7"] == pytest.approx(4.0)
    assert s["ort30"] == pytest.approx(15.5)


def test_fng_bolumu_metin():
    satirlar = haber.fng_bolumu({"bugun": 10, "ort7": 20, "ort30": 40})
    metin = "\n".join(satirlar)
    assert "Aşırı Korku" in metin and "7 gün" in metin and "30 gün" in metin
    assert "alınamadı" in haber.fng_bolumu(None)[0]


def test_siralama_ve_sinir():
    ogeler = [("Bitcoin price update %d" % i, 0.1) for i in range(10)]
    ogeler += [("Dogecoin partnership announced", 0.2), ("Bitcoin exchange hack", 2)]
    ogeler += [("Bitcoin old hack", 5)]  # 3 günden eski
    h = haber.rss_ayristir(_rss(ogeler), "T")
    s = haber.basliklari_sec(h, ["BTC", "DOGE"], simdi=SIMDI)
    assert len(s) == haber.EN_FAZLA_BASLIK
    assert s[0]["etiket"] == "RİSK" and "hack" in s[0]["baslik"]
    assert s[1]["etiket"] == "OLUMLU"
    assert all("old hack" not in x["baslik"] for x in s)


def test_tekrar_baslik_elenir():
    h = haber.rss_ayristir(_rss([("Bitcoin up", 1), ("Bitcoin up", 1)]), "T")
    assert len(haber.basliklari_sec(h, ["BTC"], simdi=SIMDI)) == 1


def test_haber_bolumu_bicim():
    h = haber.rss_ayristir(_rss([("Bitcoin exchange hack", 1)]), "CoinDesk")
    s = haber.basliklari_sec(h, ["BTC"], simdi=SIMDI)
    satirlar = haber.haber_bolumu(s, ["Decrypt"])
    metin = "\n".join(satirlar)
    assert "[RİSK] BTC" in metin and "(CoinDesk)" in metin
    assert "Decrypt alınamadı" in metin


def test_hepsi_basarisiz_hata_vermez(monkeypatch):
    def patlat(*a, **k):
        raise requests.ConnectionError("yok")

    monkeypatch.setattr(haber.requests, "get", patlat)
    metin = haber.haber_ozeti(["BTC", "DOGE"])
    assert isinstance(metin, str)
    assert "alınamadı" in metin
    assert "analiz değildir" in metin


def test_fixture_ile_uctan_uca(monkeypatch):
    fng = {"data": [{"value": "80"}] * 30}
    xml = _rss([("Bitcoin ETF approval news", 0)]).replace(
        _tarih(0), datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    )

    class Yanit:
        def __init__(self, url):
            self.url = url
            self.text = xml

        def raise_for_status(self):
            pass

        def json(self):
            return fng

    monkeypatch.setattr(haber.requests, "get", lambda url, **k: Yanit(url))
    metin = haber.haber_ozeti(["BTC"])
    assert "Aşırı Açgözlülük" in metin
    assert "[OLUMLU] BTC" in metin


C = ["BTC", "DOGE"]


def test_kural1_kelime_siniri():
    assert haber.kategori("Rehacked tokens") == "GENEL"  # alt dize eşleşmez
    assert haber.kategori("Exchange HACKED") == "RİSK"  # büyük/küçük harf fark etmez
    assert haber.hangi_coin("Bitcoiner meetup", C) is None
    assert haber.hangi_coin("Dogecoinx", C) is None
    assert haber.hangi_coin("Urban planning", C) is None


def test_kural2_liquidation_risk_degil():
    b = "Bitcoin hits 12-week low as dollar rallies on interest-rate outlook, liquidations top $1.6 billion"
    assert haber.hangi_coin(b, C) == "BTC"
    assert haber.kategori(b) != "RİSK"
    assert haber.kategori("Liquidation of positions") == "GENEL"


def test_kural3_ban_sadece_kripto_ile():
    assert haber.kategori("Country bans crypto mining") == "RİSK"
    assert haber.kategori("Regulator banned Bitcoin ETFs") == "RİSK"
    assert haber.kategori("Senator bans phones in office") == "GENEL"
    assert haber.kategori("Should Officials Be Banned From Betting?") == "GENEL"


def test_kural3_gercek_baslik():
    b = "Should Government Officials Be Banned From Prediction Markets? House Oversight Says Maybe"
    assert haber.kategori(b) != "RİSK"
    # "Markets" kural 4'e göre piyasa terimi: Piyasa/GENEL olarak kalır
    assert haber.hangi_coin(b, C) == "Piyasa"


def test_kural4_piyasa_etiketi():
    b = "DOJ moves to seize $1.2B from Binance hack, disrupts FaceStealer scam"
    assert haber.hangi_coin(b, C) == "Piyasa"
    assert haber.kategori(b) == "RİSK"
    for t in ["SEC delays decision", "Spot ETF flows", "Stablecoin supply grows",
              "Kraken expands", "Coinbase earnings", "Crypto rally", "Markets rally"]:
        assert haber.hangi_coin(t, C) == "Piyasa", t
    assert haber.hangi_coin("Local bakery wins award", C) is None
    assert haber.hangi_coin("Hacked hospital systems down", C) is None  # risk tek başına yetmez
    h = haber.rss_ayristir(_rss([("Local bakery wins award", 1)]), "T")
    assert haber.basliklari_sec(h, C, simdi=SIMDI) == []


def test_kural5_doge():
    assert haber.hangi_coin("Dogecoin jumps 10%", C) == "DOGE"
    assert haber.hangi_coin("Dogecoin and federal agency cuts", C) == "DOGE"
    assert haber.hangi_coin("DOGE price rallies", C) == "DOGE"
    for t in ["DOGE cuts hit federal agency staffers",
              "Department of Government Efficiency announces plan",
              "Government DOGE team fires staff"]:
        assert haber.hangi_coin(t, C) is None, t
    assert haber.hangi_coin("Musk visits Texas factory", C) is None
    assert haber.hangi_coin("Musk says X Money launches", C) == "DOGE"
    assert haber.hangi_coin("X payments rollout by Musk", C) == "DOGE"
    assert haber.hangi_coin("Musk tweets about Dogecoin", C) == "DOGE"


@pytest.mark.parametrize("deger", [5, 30, 50, 65, 90])
def test_fng_yorum_yon_vermez(deger):
    yorum = haber.fng_yorum(deger)
    assert yorum == ("Piyasanın ruh halini gösterir. Denenen kurallar alım-satım "
                     "zamanlamasını güvenilir biçimde iyileştirmedi.")
    satirlar = haber.fng_bolumu({"bugun": deger, "ort7": deger, "ort30": deger})
    metin = "\n".join(satirlar)
    assert haber.fng_etiket(deger) in metin and str(deger) in metin
    for yasak in ("fırsat", "satış için", "alım için", "panik", "ısınmış"):
        assert yasak not in metin
