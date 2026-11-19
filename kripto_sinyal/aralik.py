"""30 günlük tarihsel aralık ve basit risk hesapları.

Aralık bir tahmin değildir: son 3 yılın 30 günlük fiyat hareketleri bugünkü fiyata
uygulanırsa fiyatın çoğunlukla nereye kadar gittiğini gösterir. Geçmişte bu aralık
yıllara göre sonuçların %64 ile %92'sini kapsadı; garanti değildir.

Yöntem 2026-11-19'da eklendi ve donduruldu (karne bu ayarlarla ölçer):
ufuk 30 gün, pencere 1095 gün, %10 ve %90 dilimleri, en az 1125 kapanış.
"""

import math
from datetime import datetime, timezone

import numpy as np

from .simulasyon import Maliyet, coin_al, coin_sat

UFUK = 30
PENCERE = 1095
ALT = 0.10
UST = 0.90
EN_AZ = 1125
EKLENME = "2026-11-19"


def tarihsel_aralik(kapanislar, ufuk: int = UFUK, pencere: int = PENCERE, alt: float = ALT,
                    ust: float = UST, en_az: int = EN_AZ, tarihler=None,
                    bugun: str | None = None) -> dict | None:
    """Yalnız bitmiş günlük kapanışlarla 30 günlük tarihsel aralık.

    Son `pencere` tane, üst üste binen 30 günlük getiri (son bitmiş kapanışta ya da
    öncesinde biten) alınır; %10 ve %90 dilimleri son bitmiş kapanışa uygulanır.
    tarihler verilirse bugünün (UTC) ve sonrasının mumları atılır (bitmemiş gün).
    Kapanış sayısı en_az'dan azsa None döner.
    """
    kap = [float(x) for x in kapanislar]
    tarih_listesi = None
    if tarihler is not None:
        tarih_listesi = [str(t)[:10] for t in tarihler]
        if len(tarih_listesi) != len(kap):
            raise ValueError("tarihler ve kapanışlar aynı uzunlukta olmalı")
        sinir = bugun or datetime.now(timezone.utc).date().isoformat()
        tut = [i for i, t in enumerate(tarih_listesi) if t < sinir]
        kap = [kap[i] for i in tut]
        tarih_listesi = [tarih_listesi[i] for i in tut]
    if len(kap) < max(en_az, pencere + ufuk):
        return None
    k = np.asarray(kap, dtype=float)
    getiri = np.log(k[ufuk:] / k[:-ufuk])[-pencere:]
    q_alt, q_ust = np.quantile(getiri, [alt, ust])
    son = float(k[-1])
    return {
        "fiyat": son,
        "alt": son * math.exp(q_alt),
        "ust": son * math.exp(q_ust),
        "alt_getiri": math.exp(q_alt) - 1,
        "ust_getiri": math.exp(q_ust) - 1,
        "tarih": tarih_listesi[-1] if tarih_listesi else None,
        "ufuk": ufuk,
        "pencere": pencere,
    }


def en_buyuk_dusus(kapanislar) -> float:
    """Kapanıştan kapanışa, zirveden dibe en büyük düşüş (0.9 = %90)."""
    k = np.asarray([float(x) for x in kapanislar], dtype=float)
    if len(k) == 0:
        return 0.0
    zirve = np.maximum.accumulate(k)
    return float((1 - k / zirve).max())


def iki_yonlu_hesap(s: float, y: float, b: float, m: Maliyet | None = None) -> tuple[float, float]:
    """Elindekinin s'sini satıp satış parasının b'siyle geri alırsan coin adedin
    ne kadar değişir? (fiyat y kadar düşünce, fiyat y kadar yükselince) döner.

    Komisyon ve kayma dahil. b < 1 ise yalnız kullanılan para coine döner;
    kalan para nakitte durur ve coin sayısına katılmaz.
    """
    m = m or Maliyet()
    para = coin_sat(s, 1.0, m)          # 1 coinlik elden s satılır, fiyat 1
    kullanilan = para * b
    dusus = (1 - s) + coin_al(kullanilan, 1 - y, m)
    yukselis = (1 - s) + coin_al(kullanilan, 1 + y, m)
    return dusus - 1, yukselis - 1
