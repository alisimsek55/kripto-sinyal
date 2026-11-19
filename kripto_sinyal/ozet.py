"""tavsiye komutunun kısa görünümü: ana coin için sade, kısa özet.

Yeni alım-satım mantığı yok; seviyeler rapor.py'deki hesaptan gelir.
Ağ yoksa hata vermez, yalnız daha az satır yazar.
"""

import json
import textwrap
from dataclasses import dataclass
from datetime import date, datetime, timezone

from . import durum, gecmis, haber, kur, veri
from .aralik import en_buyuk_dusus, iki_yonlu_hesap, tarihsel_aralik
from .ayarlar import yol
from .rapor import kisa_satis_seviyesi, sayi_ek, yuzde_ek
from .simulasyon import Maliyet

GENISLIK = 90


# ---------- Sayı biçimleri (Türkçe: ondalık virgül, binlik nokta) ----------

def tr_sayi(x: float, ondalik: int) -> str:
    """1234.5 -> '1.234,5' (ondalik=1)."""
    return f"{x:,.{ondalik}f}".replace(",", "#").replace(".", ",").replace("#", ".")


def fiyat_k(p: float) -> str:
    """1 $ altı 4 ondalık ('0,0590'); 1 $ ve üstü tam sayı ('65.034')."""
    return tr_sayi(p, 4) if p < 1 else tr_sayi(p, 0)


def adet(x: float) -> str:
    """Coin adedi: 100 ve üstü tam sayı ('12.345'); küçükse ondalıklı ('12,50', '0,75')."""
    if abs(x) >= 100:
        return tr_sayi(x, 0)
    if abs(x) >= 1:
        return tr_sayi(x, 2)
    metin = f"{x:.6f}".rstrip("0")
    metin += "0" * max(0, 2 - len(metin.split(".")[1]))
    return metin.replace(".", ",")


def usdt(x: float) -> str:
    """USDT: 1 ondalık ('98,3')."""
    return tr_sayi(x, 1)


def tl(x: float) -> str:
    """TL: 100'ün altında 2 ondalık ('3,00'), üstünde tam sayı ('250.000')."""
    return tr_sayi(x, 2) if abs(x) < 100 else tr_sayi(x, 0)


def yuzde_tam(x: float) -> str:
    """0.523 -> '%52' (işaretsiz)."""
    return f"%{abs(x) * 100:.0f}"


def yuzde_bir(x: float) -> str:
    """0.0849 -> '%8,5' (işaretsiz, 1 ondalık)."""
    return "%" + tr_sayi(abs(x) * 100, 1)


def tarih(t) -> str:
    """'2026-03-06', date ya da datetime -> '06.03.2026'."""
    if isinstance(t, str):
        t = date.fromisoformat(t[:10])
    return t.strftime("%d.%m.%Y")


# Yönelme hali eki, yılın okunuşunun son kelimesine göre (2026 -> 'ya, 2025 -> 'e)
_BIRLER = {1: "e", 2: "ye", 3: "e", 4: "e", 5: "e", 6: "ya", 7: "ye", 8: "e", 9: "a"}
_ONLAR = {0: "e", 1: "a", 2: "ye", 3: "a", 4: "a", 5: "ye", 6: "a", 7: "e", 8: "e", 9: "a"}


def tarih_e(t) -> str:
    """'06.03.2026'ya' gibi, yönelme ekiyle tarih."""
    metin = tarih(t)
    yil = int(metin[-4:])
    ek = _BIRLER.get(yil % 10) or _ONLAR[(yil // 10) % 10]
    return f"{metin}'{ek}"


def _blok(etiket: str, cumleler: list[str]) -> list[str]:
    """Etiketli, girintili ve 90 karaktere sarılmış satırlar. Her cümle yeni satırda başlar."""
    bas = etiket.ljust(max(len(etiket) + 1, 11))
    girinti = " " * len(bas)
    satirlar = []
    for cumle in cumleler:
        if not cumle:
            continue
        on = bas if not satirlar else girinti
        satirlar.extend(textwrap.wrap(cumle, GENISLIK, initial_indent=on, subsequent_indent=girinti,
                                      break_long_words=False, break_on_hyphens=False))
    return satirlar


def _sar(metin: str, girinti: int = 0, ilk_girinti: int = 0) -> list[str]:
    return textwrap.wrap(metin, GENISLIK, initial_indent=" " * ilk_girinti,
                         subsequent_indent=" " * girinti,
                         break_long_words=False, break_on_hyphens=False)


# ---------- Girdiler ----------

@dataclass
class Portfoy:
    """İşlem geçmişinden: elde kalan coin, bekleyen satış parası, giren para."""
    coin: float
    cep: float
    giren: float
    son: datetime
    son_satis_fiyat: float | None = None
    son_satis_zaman: datetime | None = None


@dataclass
class Girdi:
    coin: str
    analiz: dict
    kapanislar: list            # yalnız bitmiş günler (son eleman = dün)
    son_tarih: str              # son bitmiş günün tarihi
    simdi: float
    canli: bool                 # anlık fiyat mı, son kapanış mı
    ref: dict                   # durum.kisa_referans sonucu
    kur: float | None = None
    kur_eski: bool = False          # kur önbellekten geldiyse (taze değil)
    portfoy: Portfoy | str = "yok"   # ya da "yok" / "kayit_yok" / "okunamadi"
    riskler: list | None = None
    btc: dict | None = None
    tutar: float | None = None
    parametre_eski: str | None = None
    aralik: dict | None = None       # aralik.tarihsel_aralik sonucu (yoksa 30 GÜN satırı yok)
    maliyet: Maliyet = Maliyet()     # Hesap satırındaki komisyon + kayma
    coinler_ozet: dict | None = None  # sonuc/coinler.json (varsa Not satırında kullanılır)


def _bekleyen(ref: dict, portfoy) -> dict | None:
    """Bekleyen satış parası: durum.json'daki son kısa satış ya da işlem geçmişindeki cep.
    İkisi de varsa tarihi yeni olan seçilir."""
    adaylar = []
    if ref.get("satis_ref") is not None:
        adaylar.append({"fiyat": ref["alim_ref"], "tarih": str(ref["son_satis_tarih"])[:10],
                        "usdt": None})
    son_islem = ref.get("son_islem") or {}
    # Yeni bir manuel alım, CSV'deki eski nakit bilgisini geçersiz kılar.
    # Satış parası harcanmışken eski dışa aktarımdan yeniden AL sinyali üretme.
    csv_eski = (isinstance(portfoy, Portfoy) and son_islem.get("tur") == "al"
                and str(son_islem["tarih"])[:10] >= portfoy.son.strftime("%Y-%m-%d"))
    if (isinstance(portfoy, Portfoy) and not csv_eski
            and portfoy.cep > 1e-9 and portfoy.son_satis_fiyat):
        adaylar.append({"fiyat": portfoy.son_satis_fiyat,
                        "tarih": portfoy.son_satis_zaman.strftime("%Y-%m-%d"),
                        "usdt": portfoy.cep})
    if not adaylar:
        return None
    return max(adaylar, key=lambda x: (x["tarih"], x["usdt"] is None))


# ---------- Metin ----------

def ozet_metni(g: Girdi) -> str:
    a, kap, simdi, coin = g.analiz, g.kapanislar, g.simdi, g.coin
    s = []

    bas = f"{coin}  {fiyat_k(simdi)} $"
    if g.kur:
        bas += f" ({tl(simdi * g.kur)} TL)"
        if g.kur_eski:
            bas += " — eski kur"
    if not g.canli:
        bas += f" — anlık fiyat alınamadı, {tarih(g.son_tarih)} kapanışı"
    s += [bas, ""]

    p = a["kurallar"]["kisa"]["secilen"]
    yetersiz = p is not None and len(kap) < p["n"] + 1
    if yetersiz:
        p = None
    elde = g.portfoy.coin if isinstance(g.portfoy, Portfoy) else None
    bekleyen = _bekleyen(g.ref, g.portfoy) if p is not None else None

    # BUGÜN: dünkü kapanış, dün geçerli olan seviyeyle karşılaştırılır (motordaki sinyal gibi)
    bugun = "Veri yetersiz; kısa kural sinyali hesaplanmadı." if yetersiz else "İşlem yok."
    if p is not None:
        _, sat_dun = kisa_satis_seviyesi(p, kap[:-1], g.ref)
        if kap[-1] >= sat_dun and (elde is None or elde > 0):
            bugun = f"Satış seviyesi geldi — elindekinin {yuzde_ek(p['s'], 'i')} sat."
        elif bekleyen and kap[-1] <= bekleyen["fiyat"] * (1 - p["y"]):
            bugun = f"Geri alım seviyesi geldi — bekleyen paranın {yuzde_ek(p['b'], 'ile')} geri al."
    s.append("BUGÜN: " + bugun)

    if g.riskler:
        for i, h in enumerate(g.riskler[:2]):
            on = f"DİKKAT: {len(g.riskler)} ciddi haber: " if i == 0 else ""
            s += _sar(f'{on}"{h["baslik"]}" ({h["kaynak"]})', 8, 0 if i == 0 else 8)
    s.append("")

    # SAT / GERİ AL
    z = a["kurallar"]["kisa"]["ileri_yuruyus"]["zincir_oran"]
    if p is None:
        s += _blok("SAT:", ["Kısa kural için günlük veri yetersiz." if yetersiz
                            else "Bu coin için satış kuralı önerilmiyor."])
    else:
        s.append("KURAL (deneysel, geçmiş testte düz alımın gerisinde kaldı):" if z < 1
                 else "KURAL (deneysel; geçmiş testte düz alımı geçti, garanti değil):")
        _, sat = kisa_satis_seviyesi(p, kap, g.ref)
        c1 = f"{fiyat_k(sat)} $ üstünde kapanırsa elindekinin {yuzde_ek(p['s'], 'i')} sat"
        if elde:
            c1 += f" (≈ {adet(elde * p['s'])} {coin})"
        fark = sat / simdi - 1
        c2 = (f"Şu ankinden {yuzde_tam(fark)} yukarıda." if fark >= 0
              else f"Fiyat şu an bu seviyenin {yuzde_tam(simdi / sat - 1)} üstünde.")
        s += _blok("SAT:", [c1 + ".", c2, hesap_metni(p, coin, g.maliyet)])
        ile = "tamamıyla" if p["b"] >= 1 else yuzde_ek(p["b"], "ile")
        if bekleyen:
            seviye = bekleyen["fiyat"] * (1 - p["y"])
            para = (f"bekleyen {usdt(bekleyen['usdt'])} USDT'nin {ile}" if bekleyen["usdt"]
                    else f"bekleyen satış paranın {ile}")
            cumleler = [f"Son satışın {fiyat_k(bekleyen['fiyat'])} $ ({tarih(bekleyen['tarih'])}). "
                        f"Fiyat {fiyat_k(seviye)} $'a inerse {para} geri al."]
            if p["t"]:
                cumleler.append(f"Satıştan sonra {p['t']} gün geri alım olmazsa parayı 3 ayda "
                                "eşit parçalarla geri al.")
        else:
            cumleler = [f"Sattıktan sonra fiyat satış fiyatının {yuzde_tam(p['y'])} altına inerse "
                        f"satış parasının {ile} geri al. ({fiyat_k(sat)} $'dan satarsan: "
                        f"{fiyat_k(sat * (1 - p['y']))} $)"]
        s += _blok("GERİ AL:", cumleler)

    # YENİ PARA
    sma = sum(kap[-200:]) / 200 if len(kap) >= 200 else None
    alim = a["kurallar"].get("alim")
    q = alim["secilen"] if alim else None
    if q is None:
        yeni = "Beklemeden al. Düşüşü beklemek geçmiş testte daha iyi sonuç vermedi."
    elif sma is None:
        yeni = "Alım kuralı için 200 günlük veri yok; normal alım yap."
    else:
        r = simdi / sma
        if r > q["u"]:
            yeni = ("Şu an pahalı bölge: aylık alımı yapma, tamamını yedeğe ayır." if q["k"] == 0
                    else f"Şu an pahalı bölge: aylık alımının {yuzde_ek(q['k'], 'i')} yap, "
                         "kalanını yedeğe ayır.")
        elif r < q["l"]:
            yeni = (f"Şu an ucuz bölge: aylık alımına ek olarak yedeğinin "
                    f"{yuzde_ek(q['g'], 'i')} kullan.")
        else:
            yeni = "Şu an normal bölge: normal alım yap."
    tutar_satiri = None
    if g.tutar and g.kur:
        u = g.tutar / g.kur
        tutar_satiri = f"{tl(g.tutar)} TL ≈ {usdt(u)} USDT ≈ {adet(u / simdi)} {coin}"
    s += _blok("YENİ PARA:", [yeni, tutar_satiri])

    # FİYAT (şişkinlik uyarısı)
    if sma is not None:
        r = simdi / sma
        c7 = kap[-1] / kap[-8] - 1 if len(kap) >= 8 else None
        if r >= 2.0:
            fyt = f"ÇOK YÜKSEK — 200 günlük ortalamasının {yuzde_tam(r - 1)} üstünde."
        elif r >= 1.5 or (c7 is not None and c7 >= 0.30):
            nedenler = []
            if r >= 1.5:
                nedenler.append(f"200 günlük ortalamasının {yuzde_tam(r - 1)} üstünde")
            if c7 is not None and c7 >= 0.30:
                nedenler.append(f"son 7 günde {yuzde_tam(c7)} yükseldi")
            fyt = "YÜKSEK — " + "; ".join(nedenler) + "."
        else:
            yon = "altında" if r < 1 else "üstünde"
            fyt = f"200 günlük ortalamasının {yuzde_tam(r - 1)} {yon}."
        s += _blok("FİYAT:", [fyt])
    if g.aralik:
        s += _blok("30 GÜN:", aralik_metni(g.aralik, simdi))
    s.append("")

    # SENİN DURUMUN
    pf = g.portfoy
    if isinstance(pf, Portfoy):
        deger = pf.coin * simdi
        ilk = f"{adet(pf.coin)} {coin} ≈ {fiyat_k(deger)} $"
        if g.kur:
            ilk += f" ({tl(deger * g.kur)} TL)"
        cumleler = [ilk]
        if pf.coin > 0 and pf.giren - pf.cep > 0:
            bb = (pf.giren - pf.cep) / pf.coin
            fark = bb / simdi - 1
            cumleler.append(f"Başa baş fiyatın {fiyat_k(bb)} $ (şu ankinden {yuzde_tam(fark)} "
                            f"{'yukarıda' if fark >= 0 else 'aşağıda'})")
        if pf.cep > 0.05:
            cumleler.append(f"Bekleyen satış paran: {usdt(pf.cep)} USDT")
        cumleler.append(f"(işlem geçmişin {tarih_e(pf.son)} kadar)")
        s += _blok("SENİN DURUMUN:", cumleler)
        if pf.coin > 0:
            s += _blok("RİSK:", risk_metni(coin, deger, g.kur, kap))
    elif pf == "kayit_yok":
        s.append(f"SENİN DURUMUN: işlem geçmişinde {coin}/USDT işlemi yok.")
    elif pf == "okunamadi":
        s.append("SENİN DURUMUN: işlem geçmişi okunamadı; hata için: python -m kripto_sinyal gecmis")
    else:
        s.append("SENİN DURUMUN: işlem geçmişi yok (gecmis klasörüne Binance dışa aktarımını koy).")
    s.append("")

    # BTC satırı
    b = g.btc
    if b and coin != "BTC":
        parcalar = [f"BTC  {fiyat_k(b['fiyat'])} $"]
        if b.get("sma"):
            r = b["fiyat"] / b["sma"]
            parcalar.append(f" — 200 günlük ortalamasının {yuzde_tam(r - 1)} "
                            f"{'altında' if r < 1 else 'üstünde'}")
        if b.get("c30") is not None:
            c30 = round(b["c30"] * 100)
            isaret = "-" if c30 < 0 else "+" if c30 > 0 else ""
            parcalar.append(f"; son 30 günde {isaret}%{abs(c30)}")
        if b.get("fng") is not None:
            f = b["fng"]
            parcalar.append(f"; piyasa havası: {haber.fng_etiket(f)} ({f}/100)")
        s += _sar("".join(parcalar) + ".", 5)
        s.append("")

    # Not
    if g.parametre_eski:
        s += _sar(f"Not: parametreler {tarih(g.parametre_eski)} verisiyle seçildi; "
                  "'python -m kripto_sinyal geritest' ile yenile.")
    s += _sar(not_metni(coin, z, g.coinler_ozet))
    return "\n".join(s)


def hesap_metni(p: dict, coin: str, m: Maliyet) -> str:
    """SAT altındaki iki yönlü hesap: sat, sonra düşüşte ya da yükselişte geri al."""
    dusus, yukselis = iki_yonlu_hesap(p["s"], p["y"], p["b"], m)

    def degisim(x: float) -> str:
        return f"≈ {yuzde_bir(x)} {'artar' if x >= 0 else 'azalır'}"

    para = "" if p["b"] >= 1 else f" paranın {yuzde_ek(p['b'], 'ile')}"
    kalan = "" if p["b"] >= 1 else " (Kalan para nakitte kalır.)"
    return (f"Hesap: {yuzde_tam(p['s'])} satıp fiyat {yuzde_tam(p['y'])} düşünce{para} geri "
            f"alırsan toplam {coin}'n {degisim(dusus)}; fiyat {yuzde_tam(p['y'])} yükselip "
            f"geri alırsan {degisim(yukselis)}.{kalan}")


def aralik_metni(r: dict, simdi: float) -> list[str]:
    """30 GÜN cümleleri: tarihsel senaryo; olasılık ya da garanti değil.
    Aralık son bitmiş kapanıştan hesaplanır; yüzdeler şu anki fiyata uzaklıktır."""
    yil = round(r["pencere"] / 365)
    alt, ust = r["alt"] / simdi - 1, r["ust"] / simdi - 1
    metin = (f"Son {yil} yılın {r['ufuk']} günlük hareketleri bugüne uygulanırsa çoğunlukla "
             f"{fiyat_k(r['alt'])}–{fiyat_k(r['ust'])} $ arasında "
             f"({'-' if alt < 0 else '+'}{yuzde_tam(alt)} / "
             f"{'-' if ust < 0 else '+'}{yuzde_tam(ust)}).")
    uyari = "Garanti değil; daha aşağı da inebilir."
    if r.get("tarih"):
        uyari += f" (veri: {tarih(r['tarih'])})"
    return [metin, uyari]


def risk_metni(coin: str, deger: float, kur_: float | None, kapanislar: list) -> list[str]:
    """RİSK cümleleri: %50 düşüşte elindekinin değeri ve geçmişteki en büyük düşüş."""
    yarim = deger * 0.5
    para = f"{tl(yarim * kur_)} TL" if kur_ else f"{fiyat_k(yarim)} $"
    cumleler = [f"{coin} %50 düşerse elindekinin değeri ≈ {para} olur."]
    if len(kapanislar) >= 2:
        cumleler.append(f"Geçmişte {coin} zirvesinden "
                        f"{yuzde_tam(en_buyuk_dusus(kapanislar))} düştü.")
    return cumleler


def not_metni(coin: str, z: float, coinler_ozet: dict | None) -> str:
    """Son Not: satış kuralının geçmiş sonucu; varsa diğer coinlerdeki sonuç."""
    yon = "gerisinde" if z < 1 else "önünde"
    ek = ("Bunlar kural çıktısıdır, yatırım tavsiyesi değildir. "
          "Ayrıntı: python -m kripto_sinyal tavsiye --ayrinti")
    try:
        k = coinler_ozet["ozet"]["kisa"]
        toplam, gecen = int(k["toplam"]), int(k["gecen"])
    except (TypeError, KeyError, ValueError):
        toplam, gecen = 0, 0
    if toplam > 0:
        return (f"Not: Satış kuralı {coin}'de düz aylık alımın {yuzde_tam(z - 1)} {yon} kaldı; "
                f"aynı yöntem {toplam} coinde denendi, {sayi_ek(gecen, 'de')} düz alımı geçti. "
                + ek)
    return (f"Not: Satış kuralı geçmiş testte düz düzenli alımın {yuzde_tam(z - 1)} {yon} kaldı. "
            + ek)


# ---------- Veri toplama ----------

def _bitmis(ayar: dict, sembol: str):
    """Fiyatları sessizce günceller; ağ yoksa kayıtlı veri. Yalnız bitmiş günler."""
    try:
        df, _ = veri.guncelle(yol(ayar, "veri_klasoru"), sembol)
    except Exception:
        df = veri.oku(yol(ayar, "veri_klasoru"), sembol)
    bugun = datetime.now(timezone.utc).date().isoformat()
    return df[df["tarih"].astype(str) < bugun].reset_index(drop=True)


def _portfoy(ayar: dict, coin: str):
    klasor = yol(ayar, "gecmis_klasoru")
    if not klasor.exists() or not any(klasor.glob("*.csv")):
        return "yok"
    try:
        d = gecmis.defter_oku(klasor, coin)
    except Exception:
        return "okunamadi"
    if d is None:
        return "kayit_yok"
    son = d.turlar[-1] if d.turlar else None
    return Portfoy(d.coin, d.cep, d.giren, d.son,
                   son.ortalama_satis if son else None, son.zaman if son else None)


def _btc(ayar: dict) -> dict | None:
    try:
        df = _bitmis(ayar, ayar["coinler"].get("BTC", "BTCUSDT"))
        if veri.gunluk_uyari(df, datetime.now(timezone.utc).date()):
            return None
        kap = list(df["kapanis"].astype(float))
        if not kap:
            return None
        fiyat = veri.anlik_fiyat(ayar["coinler"].get("BTC", "BTCUSDT")) or kap[-1]
        try:
            fng = haber.fng_cek()["bugun"]
        except Exception:
            fng = None
        return {"fiyat": fiyat,
                "sma": sum(kap[-200:]) / 200 if len(kap) >= 200 else None,
                "c30": kap[-1] / kap[-31] - 1 if len(kap) >= 31 else None,
                "fng": fng}
    except Exception:
        return None


def komut_kisa(ayar: dict, coin: str | None = None, tutar: float | None = None) -> None:
    """Kısa görünümü yazar."""
    hedef = yol(ayar, "sonuc_dosyasi")
    if not hedef.exists():
        print("Önce 'python -m kripto_sinyal geritest' çalıştır.")
        return
    sonuc = json.loads(hedef.read_text(encoding="utf-8"))
    coin = (coin or ayar.get("ana_coin") or "DOGE").upper()
    if coin not in ayar["coinler"]:
        print(f"{coin} ayarlarda yok. Seçenekler: {', '.join(ayar['coinler'])}")
        return
    a = sonuc["coinler"].get(coin)
    if a is None:
        print(f"{coin}: geri test sonucu yok, 'geritest' çalıştır.")
        return
    sembol = ayar["coinler"][coin]
    bugun = datetime.now(timezone.utc).date()
    try:
        df = _bitmis(ayar, sembol)
        uyari = veri.gunluk_uyari(df, bugun)
    except (OSError, ValueError, KeyError):
        uyari = "fiyat verisi okunamadı"
    if uyari:
        print(f"{coin}: {uyari}; güncel sinyal hesaplanmadı. "
              "'python -m kripto_sinyal veri' çalıştır.")
        return
    kap = list(df["kapanis"].astype(float))
    simdi = veri.anlik_fiyat(sembol)
    canli = simdi is not None
    if not canli:
        simdi = kap[-1]
    try:
        ref = durum.kisa_referans(durum.oku(yol(ayar, "durum_dosyasi")), coin)
    except Exception:
        print(f"{coin}: işlem kaydı okunamadı; kişisel sinyal hesaplanmadı. "
              "durum.json dosyasını kontrol et.")
        return
    k = kur.kur_al()
    try:
        riskler = haber.riskli_basliklar(coin, list(ayar["coinler"]))
    except Exception:
        riskler = []
    eski = None
    try:
        if (bugun - date.fromisoformat(a["veri_son"])).days > 45:
            eski = a["veri_son"]
    except (KeyError, ValueError):
        pass
    print(ozet_metni(Girdi(
        coin=coin, analiz=a, kapanislar=kap, son_tarih=str(df["tarih"].iloc[-1]),
        simdi=simdi, canli=canli, ref=ref, kur=k[0] if k else None,
        kur_eski=bool(k) and not k[2],
        portfoy=_portfoy(ayar, coin), riskler=riskler,
        btc=None if coin == "BTC" else _btc(ayar), tutar=tutar, parametre_eski=eski,
        aralik=tarihsel_aralik(kap, tarihler=list(df["tarih"].astype(str))),
        maliyet=Maliyet(ayar["aylik_tutar"], ayar["komisyon"], ayar["kayma"]),
        coinler_ozet=_coinler_ozet(ayar))))


def _coinler_ozet(ayar: dict) -> dict | None:
    """sonuc/coinler.json (parametreler.json ile aynı klasör); yoksa ya da bozuksa None."""
    try:
        dosya = yol(ayar, "sonuc_dosyasi").parent / "coinler.json"
        return json.loads(dosya.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
