"""Kaba ızgara araması + genişleyen pencereli ileri yürüyüş (walk-forward) testi.

Dürüstlük kuralları:
- Y yılı için parametre, yalnız Y-1 sonuna kadarki veriyle seçilir; Y yılına dokunulmaz.
  Simülasyon geleceğe bakmadığı için, tüm geçmişte bir kez koşup Y-1 sonundaki
  değeri okumak, veriyi Y-1'de kesip koşmakla birebir aynıdır (testlerde doğrulanır).
- Puan: Y-1 sonunda strateji/düz alım oranının logaritması. Tek bir keskin tepeye
  aldanmamak için her kombinasyonun puanı, kendisi + ızgaradaki komşularının
  (bir parametresi bir adım farklı olanlar) ortalamasıdır. Komşuları da iyi olan
  "geniş bir iyi bölge" seçilir; tesadüfen tutan tek nokta seçilmez.
- Düzleştirilmiş en iyi puan 0'dan büyük değilse (eğitimde düz alımı geçemiyorsa)
  kural kapatılır: o yıl düz alım yapılır. Bu da seçim sürecinin parçasıdır ve
  test yıllarında aynen uygulanır.
- Test yılları zincir halinde oynatılır: ilk test yılı, düz alımcının o günkü
  durumuyla (aynı coin, sıfır nakit) başlar; sonraki yıllar durumu (coin, nakit,
  son satış fiyatı) bir önceki yıldan devralır. Yıl oranı = (yıl sonu oran) /
  (yıl başı oran); yıl oranlarının çarpımı zincir sonucuna eşittir.
"""

import itertools
import math
from dataclasses import asdict

import numpy as np

from .simulasyon import (KADEME_PARCA, AlimDurum, AlimParam, Durum, KisaParam, Maliyet, Seri,
                         UzunParam, alim_simule, dca, max_dusus, simule)

MIN_EGITIM_GUN = 365

KISA_EKSEN = {
    "n": [7, 30],
    "x": [0.15, 0.30, 0.60, 1.00],
    "s": [0.20, 0.50],
    "y": [0.10, 0.20, 0.30],
    "b": [0.50, 1.00],
    "t": [0, 90, 180],
}  # 288 kombinasyon
UZUN_EKSEN = {
    "u": [1.6, 2.0, 2.5, 3.0],
    "sl": [0.15, 0.30],
    "l": [0.6, 0.75, 0.9],
    "bl": [0.25, 0.50, 1.00],
    "t": [0, 180, 365],
}  # 216 kombinasyon
ALIM_EKSEN = {
    "u": [1.25, 1.5, 2.0, 2.5],
    "k": [0.0, 0.5],
    "l": [0.6, 0.75, 0.9, 1.0],
    "g": [0.25, 0.5, 1.0],
    "t": [0, 365],
}  # 192 kombinasyon


def izgara(eksen: dict, sinif):
    """(parametre listesi, komşu indeks listeleri) döner."""
    adlar = list(eksen)
    indeksler = list(itertools.product(*[range(len(eksen[a])) for a in adlar]))
    konum = {ix: k for k, ix in enumerate(indeksler)}
    params = [sinif(**{a: eksen[a][j] for a, j in zip(adlar, ix)}) for ix in indeksler]
    komsu = []
    for ix in indeksler:
        ks = [konum[ix]]
        for e in range(len(adlar)):
            for adim in (-1, 1):
                j = list(ix)
                j[e] += adim
                if tuple(j) in konum:
                    ks.append(konum[tuple(j)])
        komsu.append(ks)
    return params, komsu


def katlar(seri: Seri) -> list[dict]:
    """Test yılları: eğitim (listelenmeden Y-1 sonuna) en az 365 gün olmalı."""
    sonuc = []
    for y in sorted(set(seri.yil)):
        bas = seri.yil.index(y)
        if bas < MIN_EGITIM_GUN:
            continue
        son = len(seri.yil) - 1 - seri.yil[::-1].index(y)
        sonuc.append({"yil": y, "egitim_son": bas - 1, "test_bas": bas, "test_son": son,
                      "eksik_yil": seri.tarih[son][5:] != "12-31"})
    return sonuc


def izgara_degerleri(seri: Seri, params: list, tur: str, m: Maliyet) -> np.ndarray:
    """Her kombinasyonu tüm geçmişte bir kez oynatır: (kombinasyon x gün) değer matrisi."""
    V = np.empty((len(params), len(seri)))
    for k, p in enumerate(params):
        if tur == "alim":
            _, V[k] = alim_simule(seri, p, m)
        else:
            _, V[k] = simule(seri, p if tur == "kisa" else None, p if tur == "uzun" else None, m)
    return V


def sec(V: np.ndarray, taban: np.ndarray, komsu: list, gun: int, params: list):
    """gun indeksine kadarki sonuca göre en iyi (düzleştirilmiş) kombinasyon; yoksa None."""
    ham = np.log(V[:, gun] / taban[gun])
    duz = np.array([ham[ks].mean() for ks in komsu])
    k = int(np.argmax(duz))
    if duz[k] <= 0:
        return None, float(duz[k]), float(ham[k])
    return params[k], float(duz[k]), float(ham[k])


def zincir(seri: Seri, kat_listesi: list, secim_kisa: list, secim_uzun: list, m: Maliyet,
           baslangic_coin: float | None = None, ayrinti: bool = False) -> dict:
    """Test yıllarını, her yıl o yılın seçimiyle, durumu taşıyarak oynatır."""
    ilk = kat_listesi[0]["test_bas"]
    if baslangic_coin is None:
        taban_coin, taban_deger = dca(seri, m)
        d = Durum(coin=float(taban_coin[ilk - 1]))
        taban_indeks = lambda i: taban_deger[i]
    else:
        taban_coin, taban_deger = dca(seri, m, ilk, coin0=baslangic_coin)
        d = Durum(coin=float(baslangic_coin))
        taban_indeks = lambda i: taban_deger[i - ilk]
    degerler, yillar, onceki_oran = [], [], 1.0
    for kat, pk, pu in zip(kat_listesi, secim_kisa, secim_uzun):
        for kural, p, kova in (("kisa", pk, d.kisa), ("uzun", pu, d.uzun)):
            bekleyen_satis = any(e[0] == "sat" and e[1] == kural for e in d.bekleyen)
            if p is None and (kova.nakit > 1e-9 or bekleyen_satis):
                if kova.parca == 0:
                    kova.parca = KADEME_PARCA
                kova.kapali_giris = True
        islem_once = len(d.islemler)
        d, v = simule(seri, pk, pu, m, kat["test_bas"], kat["test_son"], d)
        degerler.append(v)
        oran = v[-1] / taban_indeks(kat["test_son"])
        yillar.append({"yil": kat["yil"], "oran": oran / onceki_oran, "birikimli": oran,
                       "islem": len(d.islemler) - islem_once, "eksik_yil": kat["eksik_yil"]})
        onceki_oran = oran
    v = np.concatenate(degerler)
    t = taban_deger[ilk:] if baslangic_coin is None else taban_deger
    yil_oranlari = [y["oran"] for y in yillar]
    en_iyi = int(np.argmax(yil_oranlari))
    sonuc = {
        "baslangic": seri.tarih[ilk],
        "bitis": seri.tarih[-1],
        "yillar": yillar,
        "zincir_oran": float(v[-1] / t[-1]),
        "en_iyi_yil_haric": float(np.prod([o for j, o in enumerate(yil_oranlari) if j != en_iyi])),
        "en_iyi_yil": yillar[en_iyi]["yil"],
        "max_dusus": max_dusus(v),
        "taban_max_dusus": max_dusus(t),
        "islem_sayisi": len(d.islemler),
        "onde_gun_orani": float(np.mean(v > t * (1 + 1e-9))),
        "coin_oran": float(d.coin / taban_coin[-1]),
        "kalan_nakit": float(d.nakit()),
    }
    if ayrinti:
        sonuc.update({"_durum": d, "_degerler": v, "_taban": t})
    return sonuc


def alim_zincir(seri: Seri, kat_listesi: list, secimler: list, m: Maliyet,
                baslangic_coin: float | None = None, ayrinti: bool = False) -> dict:
    """Alım ayarını, yedeği ve kademeyi yıllar arasında taşıyarak oynatır."""
    ilk = kat_listesi[0]["test_bas"]
    if baslangic_coin is None:
        taban_coin, taban_deger = dca(seri, m)
        taban_indeks = lambda i: taban_deger[i]
    else:
        taban_coin, taban_deger = dca(seri, m, ilk, coin0=baslangic_coin)
        taban_indeks = lambda i: taban_deger[i - ilk]
    onceki_ay = sum(seri.ay_basi[:ilk])
    onceki_para = onceki_ay * m.aylik
    ilk_coin = taban_coin[ilk - 1] if baslangic_coin is None else baslangic_coin
    d = AlimDurum(coin=float(ilk_coin), yatirilan=onceki_para, katki=onceki_para)
    degerler, yillar, onceki_oran = [], [], 1.0
    for kat, p in zip(kat_listesi, secimler):
        if p is None and d.yedek > 1e-9 and d.parca == 0:
            d.parca = KADEME_PARCA
        islem_once = len(d.islemler)
        karar_once = len(d.kararlar)
        d, v = alim_simule(seri, p, m, kat["test_bas"], kat["test_son"], d)
        degerler.append(v)
        oran = v[-1] / taban_indeks(kat["test_son"])
        yillar.append({"yil": kat["yil"], "oran": oran / onceki_oran, "birikimli": oran,
                       "islem": len(d.islemler) - islem_once,
                       "ay": len(d.kararlar) - karar_once, "eksik_yil": kat["eksik_yil"]})
        onceki_oran = oran
    v = np.concatenate(degerler)
    t = taban_deger[ilk:] if baslangic_coin is None else taban_deger
    yedek = np.asarray(d.yedek_gecmisi, dtype=float)
    yil_oranlari = [y["oran"] for y in yillar]
    en_iyi = int(np.argmax(yil_oranlari))
    bolgeler = {ad: sum(1 for _, b, _ in d.kararlar if b == ad)
                for ad in ("pahalı", "ucuz", "normal")}
    sonuc = {
        "baslangic": seri.tarih[ilk],
        "bitis": seri.tarih[-1],
        "yillar": yillar,
        "zincir_oran": float(v[-1] / t[-1]),
        "en_iyi_yil_haric": float(np.prod([o for j, o in enumerate(yil_oranlari) if j != en_iyi])),
        "en_iyi_yil": yillar[en_iyi]["yil"],
        "max_dusus": max_dusus(v),
        "taban_max_dusus": max_dusus(t),
        "islem_sayisi": len(d.islemler),
        "onde_gun_orani": float(np.mean(v > t * (1 + 1e-9))),
        "coin_oran": float(d.coin / taban_coin[-1]),
        "kalan_yedek": float(d.yedek),
        "onde_yil": int(sum(o > 1.0 for o in yil_oranlari)),
        "yil_sayisi": len(yillar),
        "ortalama_yedek_orani": float(np.mean(np.divide(yedek, v, out=np.zeros_like(yedek),
                                                          where=v > 0))),
        "en_buyuk_yedek": float(d.en_buyuk_yedek),
        "bolgeler": bolgeler,
    }
    if ayrinti:
        sonuc.update({"_durum": d, "_degerler": v, "_taban": t})
    return sonuc


def tum_veri_secimi(seri: Seri, m: Maliyet) -> dict:
    """Verilen serinin son gününde kısa, uzun ve alım seçimini yapar."""
    _, taban = dca(seri, m)
    sonuc = {}
    for tur, eksen, sinif in (("kisa", KISA_EKSEN, KisaParam),
                              ("uzun", UZUN_EKSEN, UzunParam),
                              ("alim", ALIM_EKSEN, AlimParam)):
        params, komsu = izgara(eksen, sinif)
        V = izgara_degerleri(seri, params, tur, m)
        sonuc[tur] = sec(V, taban, komsu, len(seri) - 1, params)[0]
    return sonuc


def _pdict(p):
    return None if p is None else asdict(p)


def coin_analizi(seri: Seri, m: Maliyet) -> dict:
    """Bir coin için tüm arama + ileri yürüyüş sonucu (JSON'a yazılabilir)."""
    _, taban = dca(seri, m)
    kat_listesi = katlar(seri)
    if not kat_listesi:
        raise ValueError("Veri ileri yürüyüş (walk-forward) için çok kısa; "
                         "en az 2 tam takvim yılı gerekli.")
    sonuc = {"veri_bas": seri.tarih[0], "veri_son": seri.tarih[-1], "kurallar": {}}
    secimler = {}
    for tur, eksen, sinif in (("kisa", KISA_EKSEN, KisaParam), ("uzun", UZUN_EKSEN, UzunParam)):
        params, komsu = izgara(eksen, sinif)
        V = izgara_degerleri(seri, params, tur, m)
        secimler[tur] = [sec(V, taban, komsu, k["egitim_son"], params)[0] for k in kat_listesi]
        son_p, duz, ham = sec(V, taban, komsu, len(seri) - 1, params)
        secimler[tur + "_son"] = son_p
        sonuc["kurallar"][tur] = {"kombinasyon": len(params), "secilen": _pdict(son_p),
                                  "metin": son_p.metin() if son_p else "kapalı (düz alım)",
                                  "egitim_ici_oran": math.exp(ham), "kat_secimleri": []}
    sonuc["kurallar"]["birlesik"] = {"secilen": None, "kat_secimleri": []}
    yok = [None] * len(kat_listesi)
    for tur, pk, pu in (("kisa", secimler["kisa"], yok), ("uzun", yok, secimler["uzun"]),
                        ("birlesik", secimler["kisa"], secimler["uzun"])):
        r = sonuc["kurallar"][tur]
        r["ileri_yuruyus"] = zincir(seri, kat_listesi, pk, pu, m)
        r["kat_secimleri"] = [{"yil": k["yil"], "kisa": _pdict(a), "uzun": _pdict(b)}
                              for k, a, b in zip(kat_listesi, pk, pu)]
    # Birleşik kuralın canlı parametreleri = ayrı ayrı seçilen kısa + uzun
    _, v = simule(seri, secimler["kisa_son"], secimler["uzun_son"], m)
    sonuc["kurallar"]["birlesik"]["egitim_ici_oran"] = float(v[-1] / taban[-1])

    params, komsu = izgara(ALIM_EKSEN, AlimParam)
    V = izgara_degerleri(seri, params, "alim", m)
    alim_secimleri = [sec(V, taban, komsu, k["egitim_son"], params)[0] for k in kat_listesi]
    son_p, _, ham = sec(V, taban, komsu, len(seri) - 1, params)
    sonuc["kurallar"]["alim"] = {
        "kombinasyon": len(params),
        "secilen": _pdict(son_p),
        "metin": son_p.metin() if son_p else "kapalı (düz alım)",
        "egitim_ici_oran": math.exp(ham),
        "kat_secimleri": [{"yil": k["yil"], "alim": _pdict(p)}
                           for k, p in zip(kat_listesi, alim_secimleri)],
        "ileri_yuruyus": alim_zincir(seri, kat_listesi, alim_secimleri, m),
    }
    return sonuc
