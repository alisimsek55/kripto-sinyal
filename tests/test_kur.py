"""kur.py testleri (ağ yok, sahte yanıt)."""

import json

import requests

from kripto_sinyal import kur


class _Yanit:
    def __init__(self, veri, hata=False):
        self.veri, self.hata = veri, hata

    def raise_for_status(self):
        if self.hata:
            raise requests.HTTPError("500")

    def json(self):
        return self.veri


def test_basarili_kur_kaydedilir(monkeypatch, tmp_path):
    cagri = {}

    def sahte_get(url, **k):
        cagri.update(url=url, **k)
        return _Yanit({"symbol": "USDTTRY", "price": "50.70000000"})

    monkeypatch.setattr(kur.requests, "get", sahte_get)
    dosya = tmp_path / "veri" / "kur.json"
    sonuc = kur.kur_al(dosya)
    assert sonuc[0] == 50.7 and sonuc[2] is True
    assert cagri["params"] == {"symbol": "USDTTRY"} and cagri["timeout"] == 10
    assert "kripto-sinyal" in cagri["headers"]["User-Agent"]
    kayit = json.loads(dosya.read_text(encoding="utf-8"))
    assert kayit == {"kur": 50.7, "zaman_utc": sonuc[1]}


def test_ag_yoksa_kayitli_kur_taze_degil(tmp_path):
    dosya = tmp_path / "kur.json"
    dosya.write_text(json.dumps({"kur": 41.5, "zaman_utc": "2026-11-01T10:00:00+00:00"}),
                     encoding="utf-8")
    assert kur.kur_al(dosya) == (41.5, "2026-11-01T10:00:00+00:00", False)


def test_ag_ve_kayit_yoksa_none(tmp_path):
    assert kur.kur_al(tmp_path / "yok.json") is None


def test_bozuk_yanit_ve_bozuk_kayit(monkeypatch, tmp_path):
    dosya = tmp_path / "kur.json"
    for yanit in (_Yanit({"price": "abc"}), _Yanit({"price": "0"}), _Yanit({}, hata=True)):
        monkeypatch.setattr(kur.requests, "get", lambda url, y=yanit, **k: y)
        assert kur.kur_al(dosya) is None
    dosya.write_text("bozuk", encoding="utf-8")
    assert kur.kur_al(dosya) is None
    dosya.write_text(json.dumps({"kur": 40.0, "zaman_utc": "2026-11-01T10:00:00+00:00"}),
                     encoding="utf-8")
    assert kur.kur_al(dosya)[2] is False


def test_kur_satiri():
    assert kur.kur_satiri(None) is None
    assert kur.kur_satiri((50.7, "2026-11-15T20:30:05+00:00", True)) == \
        "Kur: 1 USDT = 50.70 TL (Binance, 15.11.2026 20:30 UTC)"
    assert "güncel değil" in kur.kur_satiri((50.7, "2026-11-15T20:30:05+00:00", False))
