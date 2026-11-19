"""Ücretsiz kaynaklardan haber ve duygu özeti (API anahtarı yok, LLM yok).

Genel kullanım: haber_ozeti(["BTC", "DOGE"]) -> Türkçe metin.
Hiçbir durumda hata fırlatmaz.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests

ZAMAN_ASIMI = 10
USER_AGENT = "Mozilla/5.0 (compatible; kripto-sinyal)"
FNG_URL = "https://api.alternative.me/fng/?limit=30"
RSS_KAYNAKLARI = [
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("Cointelegraph", "https://cointelegraph.com/rss"),
    ("Decrypt", "https://decrypt.co/feed"),
]
GUN_SINIRI = 3
EN_FAZLA_BASLIK = 8

COIN_ANAHTAR = {
    "BTC": ["bitcoin", "btc"],
    "ETH": ["ethereum", "ether", "eth"],
}

RISK_KELIMELER = [
    r"hack\w*", r"exploit\w*", r"delist\w*", r"lawsuit\w*", r"sues?", r"sued",
    r"bankrupt\w*", r"outage\w*", r"stolen",
    r"theft", r"scam\w*", r"fraud\w*", r"crackdown", r"insolven\w*",
    r"drain\w*", r"rug ?pull", r"sec (?:charges|sues|action|probe|lawsuit)",
    r"suspend\w*", r"halts?",
]
OLUMLU_KELIMELER = [
    r"etf approv\w*", r"approv\w*", r"list(?:s|ed|ing)", r"adopt\w*",
    r"partner\w*", r"integrat\w*", r"launch\w*", r"record high", r"all-time high",
]
PIYASA_KELIMELER = [
    r"crypto\w*", r"exchanges?", r"binance", r"coinbase", r"kraken", r"stablecoins?",
    r"sec", r"etfs?", r"markets?",
]
BAN_KELIMELER = [r"bans?", r"banned", r"banning"]
KRIPTO_TERIMLER = [
    r"crypto\w*", r"bitcoin", r"btc", r"dogecoin", r"doge", r"exchanges?",
    r"stablecoins?", r"mining", r"tokens?",
]
DOGE_DEVLET = [
    r"department of government efficiency", r"federal", r"agency", r"government",
    r"cuts", r"staffers",
]

_RISK_RE = re.compile(r"\b(?:" + "|".join(RISK_KELIMELER) + r")\b", re.I)
_OLUMLU_RE = re.compile(r"\b(?:" + "|".join(OLUMLU_KELIMELER) + r")\b", re.I)
_PIYASA_RE = re.compile(r"\b(?:" + "|".join(PIYASA_KELIMELER) + r")\b", re.I)
_BAN_RE = re.compile(r"\b(?:" + "|".join(BAN_KELIMELER) + r")\b", re.I)
_KRIPTO_RE = re.compile(r"\b(?:" + "|".join(KRIPTO_TERIMLER) + r")\b", re.I)
_DEVLET_RE = re.compile(r"\b(?:" + "|".join(DOGE_DEVLET) + r")\b", re.I)
_DOGECOIN_RE = re.compile(r"\bdogecoin\b", re.I)
_DOGE_RE = re.compile(r"\bdoge\b", re.I)
_MUSK_RE = re.compile(r"\bmusk\b", re.I)
_XODEME_RE = re.compile(r"\b(?:x money|x payments?)\b", re.I)


# ---------- Korku-Açgözlülük ----------

def fng_etiket(deger: float) -> str:
    if deger <= 24:
        return "Aşırı Korku"
    if deger <= 44:
        return "Korku"
    if deger <= 55:
        return "Nötr"
    if deger <= 74:
        return "Açgözlülük"
    return "Aşırı Açgözlülük"


def fng_ayristir(veri: dict) -> dict:
    """JSON'dan {bugun, ort7, ort30} üretir. Hatalıysa ValueError."""
    liste = veri["data"]
    degerler = [int(x["value"]) for x in liste]  # en yeni başta
    if not degerler:
        raise ValueError("boş veri")
    return {
        "bugun": degerler[0],
        "ort7": sum(degerler[:7]) / len(degerler[:7]),
        "ort30": sum(degerler[:30]) / len(degerler[:30]),
    }


FNG_YORUM = ("Piyasanın ruh halini gösterir. Denenen kurallar alım-satım zamanlamasını "
             "güvenilir biçimde iyileştirmedi.")


def fng_yorum(deger: float) -> str:
    """Endeksin anlamı. Değer ne olursa olsun aynı cümle: geçmiş testlerde endekse göre
    alıp satmak düz aylık alımı güvenilir biçimde geçmedi; "al" ya da "sat" denmez."""
    return FNG_YORUM


def fng_cek() -> dict:
    r = requests.get(FNG_URL, timeout=ZAMAN_ASIMI, headers={"User-Agent": USER_AGENT})
    r.raise_for_status()
    return fng_ayristir(r.json())


def fng_bolumu(sonuc: dict | None) -> list[str]:
    if sonuc is None:
        return ["Korku-Açgözlülük endeksi alınamadı."]
    return [
        f"Korku-Açgözlülük endeksi: {sonuc['bugun']} ({fng_etiket(sonuc['bugun'])})",
        f"7 gün ortalaması: {sonuc['ort7']:.0f} ({fng_etiket(sonuc['ort7'])}), "
        f"30 gün ortalaması: {sonuc['ort30']:.0f} ({fng_etiket(sonuc['ort30'])})",
        fng_yorum(sonuc["bugun"]),
    ]


# ---------- RSS ----------

def rss_ayristir(xml_metin: str, kaynak: str) -> list[dict]:
    """RSS metninden [{baslik, tarih(datetime UTC), kaynak}] çıkarır."""
    kok = ET.fromstring(xml_metin)
    sonuc = []
    for item in kok.iter("item"):
        baslik = (item.findtext("title") or "").strip()
        tarih_metni = (item.findtext("pubDate") or "").strip()
        if not baslik or not tarih_metni:
            continue
        try:
            tarih = parsedate_to_datetime(tarih_metni)
            if tarih.tzinfo is None:
                tarih = tarih.replace(tzinfo=timezone.utc)
            tarih = tarih.astimezone(timezone.utc)
        except (TypeError, ValueError):
            continue
        sonuc.append({"baslik": baslik, "tarih": tarih, "kaynak": kaynak})
    return sonuc


def rss_cek(kaynak: str, url: str) -> list[dict]:
    r = requests.get(url, timeout=ZAMAN_ASIMI, headers={"User-Agent": USER_AGENT})
    r.raise_for_status()
    return rss_ayristir(r.text, kaynak)


def _anahtarlar(coin: str) -> list[str]:
    coin = coin.upper()
    return COIN_ANAHTAR.get(coin, [coin.lower()])


def riskli_mi(baslik: str) -> bool:
    if _RISK_RE.search(baslik):
        return True
    return bool(_BAN_RE.search(baslik) and _KRIPTO_RE.search(baslik))


def doge_ilgili_mi(baslik: str) -> bool:
    if _DOGECOIN_RE.search(baslik):
        return True
    if _DOGE_RE.search(baslik):
        return not _DEVLET_RE.search(baslik)  # devlet kurumu haberi değil
    return bool(_MUSK_RE.search(baslik) and _XODEME_RE.search(baslik))


def hangi_coin(baslik: str, coinler: list[str]) -> str | None:
    """Başlık hangi coinle ilgili? Coin sembolü, yoksa 'Piyasa' (genel), yoksa None."""
    for coin in coinler:
        coin = coin.upper()
        if coin == "DOGE":
            if doge_ilgili_mi(baslik):
                return coin
            continue
        for k in _anahtarlar(coin):
            if re.search(r"\b" + re.escape(k) + r"\b", baslik, re.I):
                return coin
    if _PIYASA_RE.search(baslik):
        return "Piyasa"
    return None


def kategori(baslik: str) -> str:
    if riskli_mi(baslik):
        return "RİSK"
    if _OLUMLU_RE.search(baslik):
        return "OLUMLU"
    return "GENEL"


def basliklari_sec(haberler: list[dict], coinler: list[str], simdi: datetime | None = None,
                   en_fazla: int = EN_FAZLA_BASLIK) -> list[dict]:
    """Süzer, etiketler, sıralar (önce risk, sonra yeni olan), sınırlar."""
    simdi = simdi or datetime.now(timezone.utc)
    sinir = simdi - timedelta(days=GUN_SINIRI)
    gorulen = set()
    secilen = []
    for h in haberler:
        if h["tarih"] < sinir:
            continue
        anahtar = h["baslik"].lower()
        if anahtar in gorulen:
            continue
        coin = hangi_coin(h["baslik"], coinler)
        if coin is None:
            continue
        gorulen.add(anahtar)
        secilen.append({**h, "coin": coin, "etiket": kategori(h["baslik"])})
    sira = {"RİSK": 0, "OLUMLU": 1, "GENEL": 2}
    secilen.sort(key=lambda x: (sira[x["etiket"]], -x["tarih"].timestamp()))
    return secilen[:en_fazla]


def haber_bolumu(secilen: list[dict], basarisiz: list[str], hepsi_basarisiz: bool = False) -> list[str]:
    satirlar = ["Son haber başlıkları:"]
    for ad in basarisiz:
        satirlar.append(f"- {ad} alınamadı.")
    if not secilen and not hepsi_basarisiz:
        satirlar.append("- Son 3 günde ilgili başlık bulunamadı.")
    for h in secilen:
        satirlar.append(
            f"- [{h['etiket']}] {h['coin']} | {h['tarih'].strftime('%d.%m.%Y')} | "
            f"{h['baslik']} ({h['kaynak']})"
        )
    return satirlar


KAPANIS = (
    "Not: Bunlar anahtar kelimeyle etiketlenmiş ham başlıklardır, analiz değildir. "
    "Haber genelde dakikalar içinde fiyata yansır; risk uyarısı olarak değerlendir."
)


# ---------- Kısa görünüm için ----------

_BINANCE_RE = re.compile(r"\bbinance\b", re.I)
# Binance'te parayı şimdi etkileyebilecek olaylar
_BINANCE_OLAY_RE = re.compile(
    r"\b(?:halts withdrawals|suspends withdrawals|withdrawals paused|pauses withdrawals|"
    r"outage|delist|delists|delisting|insolvent|insolvency|bankrupt|bankruptcy|"
    r"hacked|exploit|exploited)\b", re.I)
# Eski olay / hukuki süreç haberleri (ör. el koyma, dava): uyarı vermez
_BINANCE_HARIC_RE = re.compile(
    r"\b(?:doj|seize|seized|seizes|crackdown|charged|charges|sentenced|lawsuit|"
    r"settle|settles|settlement)\b", re.I)


def binance_olayi_mi(baslik: str) -> bool:
    """Binance geçen, güncel bir olay kelimesi olan ve hukuki süreç haberi olmayan başlık."""
    return bool(_BINANCE_RE.search(baslik) and _BINANCE_OLAY_RE.search(baslik)
                and not _BINANCE_HARIC_RE.search(baslik))


def onemli_riskler(haberler: list[dict], ana: str, coinler: list[str],
                   simdi: datetime | None = None) -> list[dict]:
    """Kısa görünümdeki DİKKAT için: RİSK etiketli ve ana coinle ilgili başlıklar
    ya da Binance'te güncel bir sorun bildiren başlıklar."""
    ana = ana.upper()
    liste = list(dict.fromkeys([ana] + [c.upper() for c in coinler]))
    secilen = basliklari_sec(haberler, liste, simdi, en_fazla=max(1, len(haberler)))
    return [h for h in secilen
            if (h["etiket"] == "RİSK" and h["coin"] == ana) or binance_olayi_mi(h["baslik"])]


def riskli_basliklar(ana: str, coinler: list[str]) -> list[dict]:
    """Kaynakları çekip onemli_riskler sonucunu döndürür. Ağ yoksa boş liste."""
    try:
        haberler: list[dict] = []
        for ad, url in RSS_KAYNAKLARI:
            try:
                haberler.extend(rss_cek(ad, url))
            except Exception:
                pass
        return onemli_riskler(haberler, ana, coinler)
    except Exception:
        return []


# ---------- Ana işlev ----------

def haber_ozeti(coinler: list[str]) -> str:
    try:
        try:
            fng = fng_cek()
        except Exception:
            fng = None

        haberler: list[dict] = []
        basarisiz: list[str] = []
        for ad, url in RSS_KAYNAKLARI:
            try:
                haberler.extend(rss_cek(ad, url))
            except Exception:
                basarisiz.append(ad)
        secilen = basliklari_sec(haberler, list(coinler))
        bolumler = fng_bolumu(fng) + [""] + haber_bolumu(
            secilen, basarisiz, len(basarisiz) == len(RSS_KAYNAKLARI)
        ) + ["", KAPANIS]
        return "\n".join(bolumler)
    except Exception:
        return "Haber özeti şu an hazırlanamadı.\n" + KAPANIS
