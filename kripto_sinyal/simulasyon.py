"""Geri test motoru: düz düzenli alım (DCA) + kısa/uzun vade kuralları.

Model (her coin ayrı):
- Her ayın ilk mumunda açılış fiyatından sabit tutar coin alınır (strateji de aynısını yapar).
- t günü kapanışında hesaplanan sinyal t+1 açılışında uygulanır (geleceğe bakış yok).
- Her işlemde komisyon + kayma ödenir.
- Kısa ve uzun kural ayrı nakit "kovası" tutar: her kural yalnız kendi sattığının
  parasıyla geri alım yapar. Böylece ikisi birlikte çalışınca da birbirini bozmaz.
"""

import math
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

KADEME_PARCA = 3          # bekleme süresi dolunca nakit kaç ayda geri sokulur
UZUN_MERDIVEN = 1.25      # uzun vadede sonraki satış için oran bu katla artmalı
UZUN_ALIM_ARASI = 30      # uzun vadede iki alım arasında en az gün


@dataclass(frozen=True)
class KisaParam:
    """Kısa vade: n günde en az %x yükselişte elindekinin s'sini sat.
    Son satış (ya da son geri alım) fiyatının y kadar altına inerse nakdin b'siyle geri al.
    Merdiven: sonraki satış için fiyat son satışın en az x/2 üstüne çıkmalı.
    t: satıştan sonra t gün geçip geri alım olmadıysa nakit 3 ayda eşit parçalarla
    geri alınır (0 = hiç, bekle)."""
    n: int
    x: float
    s: float
    y: float
    b: float
    t: int

    def metin(self) -> str:
        bek = "yok" if self.t == 0 else f"{self.t} gün"
        return (f"{self.n} günde +%{self.x*100:.0f} -> %{self.s*100:.0f} sat; "
                f"-%{self.y*100:.0f} düşüşte geri al (nakit kullanımı %{self.b*100:.0f}); bekleme sınırı {bek}")


@dataclass(frozen=True)
class UzunParam:
    """Uzun vade: fiyat / 200 günlük ortalama (oran).
    Oran u'yu geçerse elindekinin sl'sini sat (sonraki satış u*1.25, u*1.25^2 ... ;
    oran 1'in altına inince merdiven sıfırlanır). Oran l'nin altındaysa en fazla
    30 günde bir nakdin bl'si ile al. t: kısa vadedeki gibi bekleme sınırı."""
    u: float
    sl: float
    l: float
    bl: float
    t: int

    def metin(self) -> str:
        bek = "yok" if self.t == 0 else f"{self.t} gün"
        return (f"oran {self.u:g} üstü -> %{self.sl*100:.0f} sat; oran {self.l:g} altı -> "
                f"al (nakit kullanımı %{self.bl*100:.0f}); bekleme sınırı {bek}")


@dataclass(frozen=True)
class AlimParam:
    """Alım ayarı: pahalıda aylık alımı azaltır, ucuzda yedeği kullanır."""
    u: float
    k: float
    l: float
    g: float
    t: int

    def metin(self) -> str:
        bek = "yok" if self.t == 0 else f"{self.t} gün"
        return (f"oran {self.u:g} üstü -> aylık alım %{self.k*100:.0f}; "
                f"oran {self.l:g} altı -> yedek kullanımı %{self.g*100:.0f}; "
                f"bekleme sınırı {bek}")


@dataclass
class Seri:
    """Simülasyonun kullandığı günlük veri (yalnız bitmiş günler)."""
    tarih: list
    acilis: list
    kapanis: list
    ay_basi: list
    sma200: list
    yil: list

    @classmethod
    def tablodan(cls, df: pd.DataFrame) -> "Seri":
        tarih = list(df["tarih"].astype(str))
        kap = df["kapanis"].astype(float)
        ay = [t[:7] for t in tarih]
        ay_basi = [i == 0 or ay[i] != ay[i - 1] for i in range(len(ay))]
        sma = kap.rolling(200).mean()  # yalnız t ve öncesi
        return cls(tarih, list(df["acilis"].astype(float)), list(kap), ay_basi,
                   [float(v) for v in sma], [int(t[:4]) for t in tarih])

    def __len__(self):
        return len(self.tarih)


@dataclass
class Kova:
    nakit: float = 0.0
    son_satis_gun: int = -1
    parca: int = 0  # kademeli geri girişte kalan parça sayısı
    kapali_giris: bool = False  # kural kapalıyken başlayan geri giriş sürüyor mu


@dataclass
class Durum:
    coin: float = 0.0
    kisa: Kova = field(default_factory=Kova)
    uzun: Kova = field(default_factory=Kova)
    kisa_satis_ref: float | None = None  # merdiven için son satış fiyatı
    kisa_alim_ref: float | None = None   # geri alım seviyesi bunun (1-y) katı
    uzun_seviye: float | None = None     # sonraki uzun satış oranı
    uzun_son_alim: int = -10**9
    bekleyen: list = field(default_factory=list)   # (tur, kural, oran, sonraki_seviye) yarın açılışta
    islemler: list = field(default_factory=list)   # (gun, tur, kural, fiyat, coin_miktari, gerceklesen_fiyat)

    def nakit(self) -> float:
        return self.kisa.nakit + self.uzun.nakit


@dataclass
class AlimDurum:
    """Alım ayarının yıllar arasında taşınan durumu."""
    coin: float = 0.0
    yedek: float = 0.0
    son_harcama_tarih: str | None = None
    ilk_yedek_tarih: str | None = None
    parca: int = 0
    yatirilan: float = 0.0
    katki: float = 0.0
    kararlar: list = field(default_factory=list)  # (gün, bölge, aylık karardan yatırılan)
    islemler: list = field(default_factory=list)
    yedek_gecmisi: list = field(default_factory=list)
    coin_gecmisi: list = field(default_factory=list)
    para_gecmisi: list = field(default_factory=list)  # (gün, yatırılan, yedek, katkı)
    en_buyuk_yedek: float = 0.0

    def __post_init__(self):
        if self.yedek > 0 and self.katki == 0 and self.yatirilan == 0:
            self.katki = self.yedek
        self.en_buyuk_yedek = max(self.en_buyuk_yedek, self.yedek)


@dataclass(frozen=True)
class Maliyet:
    aylik: float = 100.0
    komisyon: float = 0.001
    kayma: float = 0.0005


def coin_al(tutar: float, fiyat: float, m: Maliyet) -> float:
    """tutar USDT ile alınan coin (komisyon + kayma düşülmüş)."""
    return tutar * (1 - m.komisyon) / (fiyat * (1 + m.kayma))


def coin_sat(miktar: float, fiyat: float, m: Maliyet) -> float:
    """miktar coin satışından eline geçen USDT."""
    return miktar * fiyat * (1 - m.kayma) * (1 - m.komisyon)


def dca(seri: Seri, m: Maliyet, bas: int = 0, son: int | None = None, coin0: float = 0.0):
    """Düz düzenli alım: (her günün coin miktarı, her günün toplam değeri) dizileri."""
    son = len(seri) - 1 if son is None else son
    coin = np.empty(son - bas + 1)
    c = coin0
    for k, i in enumerate(range(bas, son + 1)):
        if seri.ay_basi[i]:
            c += coin_al(m.aylik, seri.acilis[i], m)
        coin[k] = c
    return coin, coin * np.asarray(seri.kapanis[bas:son + 1])


def _al(d: Durum, kova: Kova, tutar: float, fiyat: float, m: Maliyet, gun: int, kural: str):
    if tutar <= 1e-12:
        return
    kova.nakit -= tutar
    miktar = coin_al(tutar, fiyat, m)
    d.coin += miktar
    d.islemler.append((gun, "al", kural, fiyat, miktar, fiyat * (1 + m.kayma)))


def _sat(d: Durum, kova: Kova, oran: float, fiyat: float, m: Maliyet, gun: int, kural: str):
    miktar = d.coin * oran
    if miktar <= 1e-15:
        return
    d.coin -= miktar
    kova.nakit += coin_sat(miktar, fiyat, m)
    kova.son_satis_gun = gun
    kova.parca = 0
    d.islemler.append((gun, "sat", kural, fiyat, miktar, fiyat * (1 - m.kayma)))


def simule(seri: Seri, kisa: KisaParam | None, uzun: UzunParam | None, m: Maliyet,
           bas: int = 0, son: int | None = None, durum: Durum | None = None):
    """bas..son (dahil) günlerini oynatır. (durum, günlük toplam değer dizisi) döner.
    Verilen durum yerinde güncellenir; böylece bir yıldan sonrakine taşınabilir."""
    son = len(seri) - 1 if son is None else son
    d = durum if durum is not None else Durum()
    ac, kap, sma, ayb = seri.acilis, seri.kapanis, seri.sma200, seri.ay_basi
    deger = np.empty(son - bas + 1)

    for i in range(bas, son + 1):
        o = ac[i]
        # --- 1) Açılış: dünkü sinyaller uygulanır ---
        for tur, kural, oran, sonraki_seviye in d.bekleyen:
            kova = d.kisa if kural == "kisa" else d.uzun
            if tur == "sat":
                _sat(d, kova, oran, o, m, i, kural)
                if kova.kapali_giris:
                    kova.parca = KADEME_PARCA
                if kural == "kisa":
                    d.kisa_satis_ref = o
                    d.kisa_alim_ref = o
                else:
                    d.uzun_seviye = sonraki_seviye
            else:
                _al(d, kova, kova.nakit * oran, o, m, i, kural)
                if kural == "kisa":
                    d.kisa_alim_ref = o      # sonraki geri alım daha da aşağıda
                    d.kisa_satis_ref = None  # geri alımdan sonra yeni yükselişte satılabilir
                if kova.kapali_giris and kova.nakit <= 1e-9:
                    kova.nakit = 0.0
                    kova.parca = 0
                    kova.kapali_giris = False
                    if kural == "kisa":
                        d.kisa_satis_ref = d.kisa_alim_ref = None
        d.bekleyen = []

        # --- 2) Ay başı: düzenli alım + bekleme süresi dolan nakdin kademeli girişi ---
        if ayb[i]:
            d.coin += coin_al(m.aylik, o, m)
            for kural, kova, p in (("kisa", d.kisa, kisa), ("uzun", d.uzun, uzun)):
                if kova.nakit <= 1e-9:
                    continue
                if (kova.parca > 0 or
                        (p is not None and p.t > 0 and kova.son_satis_gun >= 0
                         and i - kova.son_satis_gun >= p.t)):
                    if kova.parca == 0:
                        kova.parca = KADEME_PARCA
                    _al(d, kova, kova.nakit / kova.parca, o, m, i, kural + "-bekleme")
                    kova.parca -= 1
                    if kova.parca == 0:
                        kova.nakit = 0.0 if kova.nakit < 1e-9 else kova.nakit
                        kova.kapali_giris = False
                        if kural == "kisa":
                            d.kisa_satis_ref = d.kisa_alim_ref = None

        # --- 3) Kapanış: yalnız i ve öncesi verisiyle sinyal üret (yarın uygulanır) ---
        c = kap[i]
        if kisa is not None and not d.kisa.kapali_giris and i >= kisa.n:
            yukselis = c / kap[i - kisa.n] - 1
            ref = d.kisa_satis_ref
            if yukselis >= kisa.x and d.coin > 0 and (ref is None or c >= ref * (1 + kisa.x / 2)):
                d.bekleyen.append(("sat", "kisa", kisa.s, None))
            elif (d.kisa_alim_ref is not None and d.kisa.nakit > 1e-9
                  and c <= d.kisa_alim_ref * (1 - kisa.y)):
                d.bekleyen.append(("al", "kisa", kisa.b, None))
        if uzun is not None and not d.uzun.kapali_giris and not math.isnan(sma[i]):
            oran = c / sma[i]
            if oran < 1.0:
                d.uzun_seviye = None  # merdiven sıfırlanır
            seviye = d.uzun_seviye or uzun.u
            if oran >= seviye and d.coin > 0:
                d.bekleyen.append(("sat", "uzun", uzun.sl, seviye * UZUN_MERDIVEN))
            elif oran < uzun.l and d.uzun.nakit > 1e-9 and i - d.uzun_son_alim >= UZUN_ALIM_ARASI:
                d.bekleyen.append(("al", "uzun", uzun.bl, None))
                d.uzun_son_alim = i

        deger[i - bas] = d.coin * c + d.kisa.nakit + d.uzun.nakit
    return d, deger


def _alim_yap(d: AlimDurum, tutar: float, fiyat: float, m: Maliyet, gun: int,
               kural: str) -> None:
    if tutar <= 1e-12:
        return
    d.coin += coin_al(tutar, fiyat, m)
    d.yatirilan += tutar
    d.islemler.append((gun, "al", kural, fiyat, tutar, fiyat * (1 + m.kayma)))


def alim_simule(seri: Seri, param: AlimParam | None, m: Maliyet, bas: int = 0,
                son: int | None = None, durum: AlimDurum | None = None):
    """Alım ayarını oynatır; satış yapmaz ve yedeği toplam değere katar."""
    son = len(seri) - 1 if son is None else son
    d = durum if durum is not None else AlimDurum()
    deger = np.empty(son - bas + 1)

    for i in range(bas, son + 1):
        if seri.ay_basi[i]:
            d.katki += m.aylik
            bolge, tutar = "normal", m.aylik
            if param is not None and i > 0 and not math.isnan(seri.sma200[i - 1]):
                oran = seri.kapanis[i - 1] / seri.sma200[i - 1]
                if oran > param.u:
                    bolge = "pahalı"
                    tutar = param.k * m.aylik
                    once = d.yedek
                    d.yedek += (1 - param.k) * m.aylik
                    d.en_buyuk_yedek = max(d.en_buyuk_yedek, d.yedek)
                    if once <= 1e-12 and d.yedek > 1e-12 and d.son_harcama_tarih is None:
                        d.ilk_yedek_tarih = seri.tarih[i]
                elif oran < param.l:
                    bolge = "ucuz"
                    harcanan = param.g * d.yedek
                    tutar += harcanan
                    d.yedek -= harcanan
                    if harcanan > 1e-12:
                        d.son_harcama_tarih = seri.tarih[i]
                        if d.yedek <= 1e-9:
                            d.yedek = 0.0
                            d.parca = 0
            _alim_yap(d, tutar, seri.acilis[i], m, i, "alim")
            d.kararlar.append((i, bolge, tutar))

            if d.yedek > 1e-9:
                if d.parca == 0 and param is not None and param.t > 0:
                    referans = d.son_harcama_tarih or d.ilk_yedek_tarih
                    if referans is not None:
                        gecen = (date.fromisoformat(seri.tarih[i]) - date.fromisoformat(referans)).days
                        if gecen > param.t:
                            d.parca = KADEME_PARCA
                if d.parca > 0:
                    harcanan = d.yedek / d.parca
                    d.yedek -= harcanan
                    _alim_yap(d, harcanan, seri.acilis[i], m, i, "alim-bekleme")
                    d.son_harcama_tarih = seri.tarih[i]
                    d.parca -= 1
                    if d.parca == 0 and d.yedek < 1e-9:
                        d.yedek = 0.0

            fark = d.yatirilan + d.yedek - d.katki
            if abs(fark) > 1e-8 * max(1.0, d.katki):
                raise AssertionError("Alım ayarında para korunumu bozuldu.")
            d.para_gecmisi.append((i, d.yatirilan, d.yedek, d.katki))

        deger[i - bas] = d.coin * seri.kapanis[i] + d.yedek
        d.yedek_gecmisi.append(d.yedek)
        d.coin_gecmisi.append(d.coin)
    return d, deger


def max_dusus(deger: np.ndarray) -> float:
    """Toplam değerin zirveden en büyük düşüşü (0.35 = %35)."""
    zirve = np.maximum.accumulate(deger)
    with np.errstate(divide="ignore", invalid="ignore"):
        dd = np.where(zirve > 0, 1 - deger / zirve, 0.0)
    return float(dd.max()) if len(dd) else 0.0
