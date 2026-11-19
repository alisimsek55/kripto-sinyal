"""Binance'ten günlük mum indirir, veri/<SEMBOL>_1d.csv dosyasında saklar.

Kurallar:
- API anahtarı yok, kişisel bilgi gönderilmez (sade User-Agent).
- CSV'ye yalnız BİTMİŞ günler yazılır. Bugünün (UTC) mumu bitmediği için
  geri testte asla kullanılmaz; kapanışı yalnız "şu anki fiyat" olarak alınır.
"""

import math
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

API = "https://api.binance.com/api/v3/klines"
FIYAT_API = "https://api.binance.com/api/v3/ticker/price"
BASLIK = {"User-Agent": "kripto-sinyal/0.1"}
GUN_MS = 86_400_000
SUTUNLAR = ["tarih", "acilis", "yuksek", "dusuk", "kapanis", "hacim"]


def _istek(url: str, params: dict) -> list | dict:
    for deneme in range(4):
        try:
            r = requests.get(url, params=params, headers=BASLIK, timeout=20)
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            if deneme == 3:
                raise
            time.sleep(2 * (deneme + 1))
    return []


def satirlara_cevir(ham: list, simdi_ms: int) -> pd.DataFrame:
    """Binance kline listesini tabloya çevirir; bitmemiş günü atar."""
    bugun_bas = simdi_ms - simdi_ms % GUN_MS  # bugünün UTC 00:00'ı
    satirlar = [
        (int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5]))
        for k in ham
        if int(k[0]) < bugun_bas
    ]
    df = pd.DataFrame(satirlar, columns=["ms"] + SUTUNLAR[1:])
    df.insert(0, "tarih", pd.to_datetime(df.pop("ms"), unit="ms").dt.strftime("%Y-%m-%d"))
    return df


def csv_yolu(klasor: Path, sembol: str) -> Path:
    return klasor / f"{sembol}_1d.csv"


def oku(klasor: Path, sembol: str, bugun: date | None = None) -> pd.DataFrame:
    """Önbellekteki bitmiş günleri okur (yoksa boş tablo)."""
    yol = csv_yolu(klasor, sembol)
    if not yol.exists():
        return pd.DataFrame(columns=SUTUNLAR)
    df = pd.read_csv(yol, dtype={"tarih": str})
    if bugun is not None:
        df = df[df["tarih"] < bugun.isoformat()].reset_index(drop=True)
    return df


def guncelle(klasor: Path, sembol: str) -> tuple[pd.DataFrame, int]:
    """Eksik günleri indirir, CSV'ye ekler. (tablo, yeni_gun_sayisi) döner."""
    klasor.mkdir(parents=True, exist_ok=True)
    eski = oku(klasor, sembol)
    if len(eski):
        son = pd.Timestamp(eski["tarih"].iloc[-1], tz="UTC")
        bas_ms = int(son.timestamp() * 1000) + GUN_MS
    else:
        bas_ms = 0  # Binance listelenme gününden başlar
    simdi_ms = int(time.time() * 1000)
    parcalar = []
    while bas_ms < simdi_ms - simdi_ms % GUN_MS:
        ham = _istek(API, {"symbol": sembol, "interval": "1d", "startTime": bas_ms, "limit": 1000})
        if not ham:
            break
        parcalar.append(satirlara_cevir(ham, simdi_ms))
        bas_ms = int(ham[-1][0]) + GUN_MS
        if len(ham) < 1000:
            break
    yeni = pd.concat(parcalar, ignore_index=True) if parcalar else pd.DataFrame(columns=SUTUNLAR)
    tum = pd.concat([eski, yeni], ignore_index=True) if len(eski) else yeni
    tum = tum.drop_duplicates("tarih", keep="last").sort_values("tarih").reset_index(drop=True)
    tum.to_csv(csv_yolu(klasor, sembol), index=False)
    return tum, len(yeni)


def bosluklar(df: pd.DataFrame) -> list[str]:
    """Ardışık olmayan günleri bulur (veri boşluğu kontrolü)."""
    t = pd.to_datetime(df["tarih"])
    fark = t.diff().dt.days
    return [f"{t.iloc[i - 1]:%Y-%m-%d} -> {t.iloc[i]:%Y-%m-%d}" for i in range(1, len(t)) if fark.iloc[i] != 1]


def gunluk_uyari(df: pd.DataFrame, bugun: date) -> str | None:
    """Günlük sinyal için dünkü kapanış ve kesintisiz günlük veri gerekir."""
    if df.empty:
        return "fiyat verisi yok"
    for sutun in ("acilis", "kapanis"):
        if not df[sutun].astype(float).map(lambda x: math.isfinite(x) and x > 0).all():
            return "günlük fiyat verisinde geçersiz fiyat var"
    if str(df["tarih"].iloc[-1]) != (bugun - timedelta(days=1)).isoformat():
        return f"günlük veri güncel değil (son kapanış: {df['tarih'].iloc[-1]})"
    if bosluklar(df):
        return "günlük fiyat verisinde boşluk veya sıralama hatası var"
    return None


def anlik_fiyat(sembol: str) -> float | None:
    """Şu anki fiyat (bitmemiş günün son fiyatı). Ağ yoksa None."""
    try:
        fiyat = float(_istek(FIYAT_API, {"symbol": sembol})["price"])
        return fiyat if math.isfinite(fiyat) and fiyat > 0 else None
    except Exception:
        return None
