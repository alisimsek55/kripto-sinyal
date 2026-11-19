"""İleriye dönük takip başlangıcı ve karnesi."""

import json
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from . import veri
from .aralik import ALT, EKLENME, PENCERE, UFUK, UST, tarihsel_aralik
from .arama import alim_zincir, tum_veri_secimi, zincir
from .ayarlar import yol
from .rapor import fiyat, sayi_ek, yuzde
from .simulasyon import AlimParam, KisaParam, Maliyet, Seri, UzunParam, dca


class TakipHatasi(Exception):
    """Kullanıcıya gösterilecek takip hatası."""


def _verileri_oku(ayar: dict) -> dict:
    """Fiyatları sessizce günceller; ağ yoksa kayıtlı veriyi kullanır."""
    sonuc = {}
    bugun = datetime.now(timezone.utc).date().isoformat()
    for coin, sembol in ayar["coinler"].items():
        try:
            df, _ = veri.guncelle(yol(ayar, "veri_klasoru"), sembol)
        except Exception:
            df = veri.oku(yol(ayar, "veri_klasoru"), sembol)
        df = df[df["tarih"].astype(str) < bugun].reset_index(drop=True)
        if len(df) == 0:
            raise TakipHatasi(f"{coin}: bitmiş fiyat verisi yok.")
        sonuc[coin] = df
    return sonuc


def _parametre_sozluk(secimler: dict) -> dict:
    return {ad: None if p is None else asdict(p) for ad, p in secimler.items()}


def _parametreler(kayit: dict) -> dict:
    return {
        "kisa": None if kayit["kisa"] is None else KisaParam(**kayit["kisa"]),
        "uzun": None if kayit["uzun"] is None else UzunParam(**kayit["uzun"]),
        "alim": None if kayit["alim"] is None else AlimParam(**kayit["alim"]),
    }


def _metin(p) -> str:
    return "kapalı" if p is None else p.metin()


def takip_baslat(ayar: dict, klasor: Path, tarih: str | None = None,
                 yeniden: bool = False) -> dict:
    """Kuralları başlangıç gününde dondurur."""
    klasor = Path(klasor)
    hedef = klasor / "baslangic.json"
    if hedef.exists() and not yeniden:
        eski = json.loads(hedef.read_text(encoding="utf-8"))
        raise TakipHatasi(f"Takip zaten {eski['baslangic']} tarihinde başlatılmış.")

    tablolar = _verileri_oku(ayar)
    if tarih is None:
        baslangic = min(str(df["tarih"].iloc[-1]) for df in tablolar.values())
        dun = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
        if baslangic != dun:
            raise TakipHatasi("Günlük veri güncel değil; gerçek ileri takip başlatılmadı. "
                             "Önce 'veri' çalıştır; geçmiş gösterimi için --tarih kullan.")
        geriye_donuk = False
    else:
        try:
            datetime.strptime(tarih, "%Y-%m-%d")
        except ValueError as e:
            raise TakipHatasi("Tarih YYYY-AA-GG biçiminde olmalı.") from e
        eksik = [coin for coin, df in tablolar.items()
                 if tarih not in set(df["tarih"].astype(str))]
        if eksik:
            raise TakipHatasi(f"{tarih} bitmiş fiyat verisinde yok: {', '.join(eksik)}.")
        baslangic = tarih
        geriye_donuk = True

    m = Maliyet(ayar["aylik_tutar"], ayar["komisyon"], ayar["kayma"])
    coinler = {}
    secilenler = {}
    for coin, df in tablolar.items():
        kesik = df[df["tarih"].astype(str) <= baslangic].reset_index(drop=True)
        if len(kesik) == 0 or str(kesik["tarih"].iloc[-1]) != baslangic:
            raise TakipHatasi(f"{coin}: {baslangic} bitmiş fiyat verisinde yok.")
        seri = Seri.tablodan(kesik)
        secimler = tum_veri_secimi(seri, m)
        secilenler[coin] = secimler
        taban_coin, _ = dca(seri, m)
        coinler[coin] = {
            **_parametre_sozluk(secimler),
            "kapanis": float(seri.kapanis[-1]),
            "baslangic_coin": float(taban_coin[-1]),
        }

    kayit = {
        "baslangic": baslangic,
        "geriye_donuk": geriye_donuk,
        "olusturma_zamani_utc": datetime.now(timezone.utc).isoformat(),
        "ayarlar": {"aylik_tutar": m.aylik, "komisyon": m.komisyon, "kayma": m.kayma},
        "coinler": coinler,
    }
    klasor.mkdir(parents=True, exist_ok=True)
    if hedef.exists():
        eski = json.loads(hedef.read_text(encoding="utf-8"))
        kok = klasor / f"baslangic-{eski['baslangic']}"
        arsiv = kok.with_suffix(".json")
        sira = 2
        while arsiv.exists():
            arsiv = klasor / f"{kok.name}-{sira}.json"
            sira += 1
        hedef.rename(arsiv)
    hedef.write_text(json.dumps(kayit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Takip başlangıcı: {baslangic}")
    for coin in ayar["coinler"]:
        for tur in ("kisa", "uzun", "alim"):
            ad = {"kisa": "kısa", "uzun": "uzun", "alim": "alım"}[tur]
            print(f"{coin} {ad}: {_metin(secilenler[coin][tur])}")
    return kayit


def _katlar(seri: Seri, baslangic: str) -> list[dict]:
    indeksler = [i for i, tarih in enumerate(seri.tarih) if tarih > baslangic]
    if not indeksler:
        return []
    sonuc = []
    bas = indeksler[0]
    for i in indeksler[1:]:
        if seri.yil[i] != seri.yil[bas]:
            son = i - 1
            sonuc.append({"yil": seri.yil[bas], "test_bas": bas, "test_son": son,
                          "eksik_yil": seri.tarih[son][5:] != "12-31"})
            bas = i
    son = indeksler[-1]
    sonuc.append({"yil": seri.yil[bas], "test_bas": bas, "test_son": son,
                  "eksik_yil": seri.tarih[son][5:] != "12-31"})
    return sonuc


def _yillik_secimler(df, seri: Seri, kat_listesi: list, ilk: dict, m: Maliyet) -> dict:
    secimler = {ad: [ilk[ad]] for ad in ("kisa", "uzun", "alim")}
    for kat in kat_listesi[1:]:
        sinir = f"{kat['yil'] - 1}-12-31"
        kesik = df[df["tarih"].astype(str) <= sinir].reset_index(drop=True)
        yeni = tum_veri_secimi(Seri.tablodan(kesik), m)
        for ad in secimler:
            secimler[ad].append(yeni[ad])
    return secimler


def _islem_miktari(islem: tuple, tur: str, seri: Seri, secimler: dict, katlar: list,
                   m: Maliyet) -> str:
    gun, yon, kural, _, miktar, etkin = islem
    if yon == "al":
        tutar = miktar if tur == "alim" else miktar * etkin / (1 - m.komisyon)
        return f"{fiyat(tutar)} USDT"
    sinyal_gunu = max(gun - 1, katlar[0]["test_bas"])
    sira = next((j for j, kat in enumerate(katlar)
                 if kat["test_bas"] <= sinyal_gunu <= kat["test_son"]), 0)
    p = secimler["kisa" if kural == "kisa" else "uzun"][sira]
    oran = p.s if kural == "kisa" else p.sl
    return yuzde(oran)


def _islemler(sonuc: dict, tur: str, seri: Seri, secimler: dict, katlar: list,
              m: Maliyet) -> list[dict]:
    kararlar = ({gun: (bolge, tutar) for gun, bolge, tutar in sonuc["_durum"].kararlar}
                if tur == "alim" else {})
    islemler = []
    for i in sonuc["_durum"].islemler:
        if tur == "alim":
            if i[2] == "alim":
                bolge, tutar = kararlar[i[0]]
                if abs(tutar - m.aylik) <= 1e-9:
                    continue
                yon = bolge
            else:
                yon = "yedek girişi"
            ad = "alım"
        else:
            ad = "kısa" if i[2].startswith("kisa") else "uzun"
            yon = i[1]
        islemler.append({
            "tarih": seri.tarih[i[0]],
            "kural": ad,
            "yon": yon,
            "miktar": _islem_miktari(i, tur, seri, secimler, katlar, m),
            "etkin_fiyat": float(i[5]),
        })
    return islemler


def _oran_durumu(r: float) -> str:
    if abs(r - 1) <= 1e-9:
        return "ayni"
    return "onde" if r > 1 else "geride"


def _bos_sonuc(kapanis: float, coin: float) -> dict:
    deger = float(kapanis * coin)
    return {"oran": 1.0, "durum": "ayni", "islem_sayisi": 0, "strateji_degeri": deger,
            "taban_degeri": deger, "islemler": [], "yillar": []}


def _coin_karnesi(df, baslangic: str, kayit: dict, m: Maliyet) -> tuple[dict, bool]:
    seri = Seri.tablodan(df)
    kesik = df[df["tarih"].astype(str) <= baslangic].reset_index(drop=True)
    yeniden = _parametre_sozluk(tum_veri_secimi(Seri.tablodan(kesik), m))
    ilk_sozluk = {ad: kayit[ad] for ad in ("kisa", "uzun", "alim")}
    degisti = yeniden != ilk_sozluk
    ilk = _parametreler(kayit)
    kat_listesi = _katlar(seri, baslangic)
    n = sum(tarih > baslangic for tarih in seri.tarih)
    if not kat_listesi:
        bos = _bos_sonuc(kayit["kapanis"], kayit["baslangic_coin"])
        return {"n": 0, "bitis": baslangic,
                "kurallar": {ad: dict(bos) for ad in ("kisa", "uzun", "birlikte", "alim")},
                "islemler": []}, degisti

    secimler = _yillik_secimler(df, seri, kat_listesi, ilk, m)
    yok = [None] * len(kat_listesi)
    ham = {
        "kisa": zincir(seri, kat_listesi, secimler["kisa"], yok, m,
                        kayit["baslangic_coin"], True),
        "uzun": zincir(seri, kat_listesi, yok, secimler["uzun"], m,
                        kayit["baslangic_coin"], True),
        "birlikte": zincir(seri, kat_listesi, secimler["kisa"], secimler["uzun"], m,
                            kayit["baslangic_coin"], True),
        "alim": alim_zincir(seri, kat_listesi, secimler["alim"], m,
                            kayit["baslangic_coin"], True),
    }
    kurallar = {}
    tum_islemler = []
    for tur, sonuc in ham.items():
        islemler = _islemler(sonuc, tur, seri, secimler, kat_listesi, m)
        if tur != "birlikte":
            tum_islemler.extend(islemler)
        yillar = [{**y, "islem": sum(i["tarih"].startswith(str(y["yil"]))
                                     for i in islemler)} for y in sonuc["yillar"]]
        oran = float(sonuc["zincir_oran"])
        kurallar[tur] = {
            "oran": oran,
            "durum": _oran_durumu(oran),
            "islem_sayisi": len(islemler),
            "strateji_degeri": float(sonuc["_degerler"][-1]),
            "taban_degeri": float(sonuc["_taban"][-1]),
            "islemler": islemler,
            "yillar": yillar,
        }
    tum_islemler.sort(key=lambda x: x["tarih"], reverse=True)
    return {"n": n, "bitis": seri.tarih[-1], "kurallar": kurallar,
            "islemler": tum_islemler[:10]}, degisti


def _oran_metni(r: float) -> str:
    if _oran_durumu(r) == "ayni":
        return f"x{r:.4f} (düz alımla aynı)"
    yon = "önde" if r > 1 else "geride"
    return f"x{r:.4f} ({yuzde(abs(r - 1))} {yon})"


def _kural_metni(tur: str, ilk: dict) -> str:
    if tur == "birlikte":
        if ilk["kisa"] is None and ilk["uzun"] is None:
            return "kapalı"
        return f"{_metin(ilk['kisa'])} | {_metin(ilk['uzun'])}"
    p = ilk[tur]
    return "kapalı" if p is None else p.metin()


def senaryo_karnesi(df, baslangic: str) -> dict:
    """30 günlük aralığın ileri takibi. Takip başlangıcından itibaren 30 günde bir
    açılan, üst üste binmeyen dönemler. Aralık yalnız dönem başına kadarki veriyle
    hesaplanır; dönem sonundaki kapanış aralığın içinde mi diye bakılır.
    Sonu henüz bitmiş bir mum olmayan dönem sayılmaz."""
    tarih = list(df["tarih"].astype(str))
    kap = list(df["kapanis"].astype(float))
    konum = {t: i for i, t in enumerate(tarih)}
    donemler = []
    bas = date.fromisoformat(baslangic)
    while tarih and (bas + timedelta(days=UFUK)).isoformat() <= tarih[-1]:
        bit = bas + timedelta(days=UFUK)
        b, e = bas.isoformat(), bit.isoformat()
        bas = bit
        if b not in konum or e not in konum:
            continue  # veri boşluğu: dönem ölçülemez
        i = konum[b]
        r = tarihsel_aralik(kap[:i + 1], tarihler=tarih[:i + 1], bugun=e)
        if r is None:
            continue  # dönem başında yeterli geçmiş yok
        son = kap[konum[e]]
        donemler.append({"bas": b, "bitis": e, "alt": r["alt"], "ust": r["ust"],
                         "kapanis": son, "icinde": bool(r["alt"] <= son <= r["ust"])})
    return {"tamam": len(donemler), "icinde": sum(d["icinde"] for d in donemler),
            "donemler": donemler}


def senaryo_satirlari(senaryolar: dict) -> list[str]:
    """karne çıktısındaki '30 günlük senaryo karnesi' bölümü."""
    s = ["30 günlük senaryo karnesi:",
         f"(Yöntem {EKLENME[8:10]}.{EKLENME[5:7]}.{EKLENME[:4]} tarihinde eklendi ve donduruldu: "
         f"son {PENCERE} günün {UFUK} günlük hareketlerinin %{ALT * 100:.0f}–%{UST * 100:.0f} "
         "aralığı.)"]
    for coin, k in senaryolar.items():
        if k["tamam"] == 0:
            s.append(f"{coin}: Henüz tamamlanmış {UFUK} günlük dönem yok.")
            continue
        s.append(f"{coin}: {k['tamam']} tamamlanmış dönemin {sayi_ek(k['icinde'], 'de')} "
                 "fiyat aralıkta kaldı.")
        for d in k["donemler"]:
            s.append(f"  {d['bas']} -> {d['bitis']}: kapanış {fiyat(d['kapanis'])} $, aralık "
                     f"{fiyat(d['alt'])}–{fiyat(d['ust'])} $ "
                     f"({'içinde' if d['icinde'] else 'dışında'})")
    return s


def karne(ayar: dict, klasor: Path) -> dict:
    """Başlangıç seçimi ve sonraki yıllık seçimlerle ileri dönem sonuçlarını yazar."""
    klasor = Path(klasor)
    kaynak = klasor / "baslangic.json"
    if not kaynak.exists():
        raise TakipHatasi("Takip kaydı yok; önce 'python -m kripto_sinyal takip-baslat' çalıştır.")
    baslangic_kaydi = json.loads(kaynak.read_text(encoding="utf-8"))
    baslangic = baslangic_kaydi["baslangic"]
    a = baslangic_kaydi["ayarlar"]
    m = Maliyet(a["aylik_tutar"], a["komisyon"], a["kayma"])
    tablolar = _verileri_oku(ayar)

    coinler = {}
    degisti = False
    for coin in ayar["coinler"]:
        coinler[coin], fark = _coin_karnesi(tablolar[coin], baslangic,
                                            baslangic_kaydi["coinler"][coin], m)
        degisti = degisti or fark
    if degisti:
        print("Dikkat: kod ya da veri değişmiş; karne donmuş parametreleri kullanıyor.")

    for coin in ayar["coinler"]:
        sonuc = coinler[coin]
        ek = (" (geriye dönük başlatıldı; gerçek ileri takip değil)"
              if baslangic_kaydi["geriye_donuk"] else "")
        print(f"### {coin} — takip başlangıcı {baslangic}, {sonuc['n']} gün{ek}")
        ilk = _parametreler(baslangic_kaydi["coinler"][coin])
        for tur, ad in (("kisa", "Kısa"), ("uzun", "Uzun"),
                        ("birlikte", "Birlikte"), ("alim", "Alım")):
            k = sonuc["kurallar"][tur]
            print(f"{ad}: {_kural_metni(tur, ilk)}; {_oran_metni(k['oran'])}; "
                  f"işlem {k['islem_sayisi']}")
        if sonuc["islemler"]:
            print("Son işlemler:")
            for i in sonuc["islemler"]:
                print(f"  {i['tarih']} — {i['kural']} — {i['yon']} — {i['miktar']} — "
                      f"{fiyat(i['etkin_fiyat'])} $")
        else:
            print("Son işlemler: yok")
        if sonuc["n"] == 0:
            print(f"Takip {baslangic} tarihinde başladı; henüz biten gün yok.")
        if sonuc["n"] < 180:
            print(f"Henüz erken: hüküm için en az 180 gün gerekli (şu an {sonuc['n']}).")
        else:
            hukumler = []
            for tur, ad in (("kisa", "kısa"), ("uzun", "uzun"),
                            ("birlikte", "birlikte"), ("alim", "alım")):
                r = sonuc["kurallar"][tur]["oran"]
                durum = {"onde": "önde", "geride": "geride", "ayni": "aynı"}[
                    _oran_durumu(r)]
                hukumler.append(f"{ad} {durum}")
            print("Hüküm: " + "; ".join(hukumler) + ".")
        print()

    senaryolar = {coin: senaryo_karnesi(tablolar[coin], baslangic) for coin in ayar["coinler"]}
    for satir in senaryo_satirlari(senaryolar):
        print(satir)
    print()

    cikti = {
        "baslangic": baslangic,
        "geriye_donuk": baslangic_kaydi["geriye_donuk"],
        "olusturma_zamani_utc": datetime.now(timezone.utc).isoformat(),
        "ayarlar": baslangic_kaydi["ayarlar"],
        "coinler": coinler,
        "senaryo": senaryolar,
    }
    (klasor / "karne.json").write_text(
        json.dumps(cikti, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Başlangıç parametreleri {baslangic} tarihinde donduruldu. "
          "Her yeni takvim yılında yalnız önceki yıl sonuna kadarki veriyle yeniden seçim yapılır; "
          "yukarıdaki parametreler başlangıç seçimini gösterir.")
    return cikti
