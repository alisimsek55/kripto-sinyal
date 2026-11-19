"""geritest raporu ve tavsiye metni (sade Türkçe)."""

from datetime import date

KURAL_AD = {"kisa": "Kısa vade", "uzun": "Uzun vade", "birlesik": "Birlikte (kısa + uzun)",
            "alim": "Alım ayarı (satış yok)"}


def fiyat(p: float) -> str:
    if p >= 1000:
        return f"{p:,.0f}".replace(",", ".")
    if p >= 1:
        return f"{p:.2f}"
    return f"{p:.4f}" if p >= 0.01 else f"{p:.6f}"


def binlik(x: float) -> str:
    """Tam sayı, binlik ayracı nokta: 250000 -> '250.000'."""
    return f"{x:,.0f}".replace(",", ".")


def tl_metni(x: float) -> str:
    """TL: 100'ün altında 2 ondalık, üstünde tam sayı ve binlik ayracı."""
    return f"{x:.2f}" if abs(x) < 100 else binlik(x)


def yuzde(x: float) -> str:
    return f"%{x * 100:.0f}"


# Sayının okunuşunun son kelimesine göre belirtme hali eki (%20'sini, %30'unu, %100'ünü)
_EK = {1: "ini", 2: "sini", 3: "ünü", 4: "ünü", 5: "ini", 6: "sını", 7: "sini", 8: "ini",
       9: "unu", 10: "unu", 20: "sini", 30: "unu", 40: "ını", 50: "sini", 60: "ını",
       70: "ini", 80: "ini", 90: "ını", 100: "ünü"}


def sayi_ek(n: int, hal: str) -> str:
    """Tam sayıya ek: hal='i' -> "4'ünü", 'ile' -> "4'üyle", 'de' -> "4'ünde" (iyelik + bulunma)."""
    n = int(n)
    if n == 0:
        ek = "ını"
    else:
        anahtar = n % 10 or n % 100 or 100
        ek = _EK.get(anahtar, "ini")
    if hal == "ile":
        ek = ek[:-2] + ("yle" if ek[-1] in "iü" else "yla")
    elif hal == "de":
        ek = ek[:-1] + ("de" if ek[-1] in "iü" else "da")
    return f"{n}'{ek}"


def yuzde_ek(x: float, hal: str) -> str:
    """hal='i' -> '%20'sini'; hal='ile' -> '%20'siyle'."""
    return "%" + sayi_ek(round(x * 100), hal)


def oran_metni(r: float) -> str:
    """1.12 -> 'x1.12 (%12 önde)'."""
    fark = (r - 1) * 100
    yon = "önde" if fark >= 0 else "geride"
    return f"x{r:.2f} (%{abs(fark):.0f} {yon})"


def hukum(iy: dict) -> str:
    z, h = iy["zincir_oran"], iy["en_iyi_yil_haric"]
    if z < 1.0:
        return "Görmediği yıllarda düz düzenli alımı GEÇEMEDİ. Düz alım daha iyiydi."
    if h < 1.0:
        return (f"Düz alımı geçti ama kazancın çoğu tek yıldan ({iy['en_iyi_yil']}) geliyor; "
                "o yıl çıkarılınca geride kalıyor. Güvenme.")
    return "Görmediği yıllarda düz alımı geçti. Yine de geçmiş geleceği garanti etmez."


def _kisa_ozet(p: dict | None) -> str:
    if p is None:
        return "kapalı"
    t = "-" if p["t"] == 0 else f"{p['t']}g"
    return f"{p['n']}g+{p['x']*100:.0f}% s{p['s']*100:.0f} y{p['y']*100:.0f} b{p['b']*100:.0f} t{t}"


def _uzun_ozet(p: dict | None) -> str:
    if p is None:
        return "kapalı"
    t = "-" if p["t"] == 0 else f"{p['t']}g"
    return f"u{p['u']:g} s{p['sl']*100:.0f} l{p['l']:g} b{p['bl']*100:.0f} t{t}"


def _alim_ozet(p: dict | None) -> str:
    if p is None:
        return "kapalı"
    t = "-" if p["t"] == 0 else f"{p['t']}g"
    return f"u{p['u']:g} k{p['k']*100:.0f} l{p['l']:g} g{p['g']*100:.0f} t{t}"


def geritest_raporu(coin: str, a: dict) -> str:
    s = [f"=== {coin}  (veri {a['veri_bas']} .. {a['veri_son']}) ==="]
    for tur in ("kisa", "uzun", "birlesik"):
        k = a["kurallar"][tur]
        iy = k["ileri_yuruyus"]
        s.append(f"\n-- {KURAL_AD[tur]} --")
        if tur != "birlesik":
            s.append(f"Şimdiki seçim (tüm veri, {k['kombinasyon']} kombinasyon): {k['metin']}")
            s.append(f"  Eğitim içi sonuç (iyimser, kanıt değil): {oran_metni(k['egitim_ici_oran'])}")
        else:
            s.append(f"  Eğitim içi sonuç (iyimser, kanıt değil): {oran_metni(k['egitim_ici_oran'])}")
        s.append("  Yıl   Seçilen parametre (yalnız önceki yıllarla)      Yıl oranı  Birikimli  İşlem")
        for y, sc in zip(iy["yillar"], k["kat_secimleri"]):
            if tur == "kisa":
                ps = _kisa_ozet(sc["kisa"])
            elif tur == "uzun":
                ps = _uzun_ozet(sc["uzun"])
            else:
                ps = f"{_kisa_ozet(sc['kisa'])} | {_uzun_ozet(sc['uzun'])}"
            eksik = "*" if y["eksik_yil"] else " "
            s.append(f"  {y['yil']}{eksik} {ps:<47.47} {y['oran']:>8.3f}  {y['birikimli']:>9.3f}  {y['islem']:>5}")
        s.append(f"  Zincir sonucu ({iy['baslangic']}..{iy['bitis']}): düz alıma göre {oran_metni(iy['zincir_oran'])}")
        s.append(f"  En iyi yıl ({iy['en_iyi_yil']}) çıkarılınca: {oran_metni(iy['en_iyi_yil_haric'])}")
        s.append(f"  En büyük düşüş: strateji {yuzde(iy['max_dusus'])}, düz alım {yuzde(iy['taban_max_dusus'])}"
                 f" | işlem: {iy['islem_sayisi']} | düz alımın önünde olduğu gün: {yuzde(iy['onde_gun_orani'])}"
                 f" | coin miktarı düz alıma göre: x{iy['coin_oran']:.2f}")
        s.append(f"  HÜKÜM: {hukum(iy)}")

    k = a["kurallar"]["alim"]
    iy = k["ileri_yuruyus"]
    s.append(f"\n-- {KURAL_AD['alim']} --")
    s.append(f"Şimdiki seçim (tüm veri, {k['kombinasyon']} kombinasyon): {k['metin']}")
    s.append(f"  Eğitim içi sonuç (iyimser, kanıt değil): {oran_metni(k['egitim_ici_oran'])}")
    s.append("  Yıl   Seçilen parametre (yalnız önceki yıllarla)      Yıl oranı  Birikimli  İşlem")
    for y, sc in zip(iy["yillar"], k["kat_secimleri"]):
        ps = _alim_ozet(sc["alim"])
        eksik = "*" if y["eksik_yil"] else " "
        s.append(f"  {y['yil']}{eksik} {ps:<47.47} {y['oran']:>8.3f}  {y['birikimli']:>9.3f}  {y['islem']:>5}")
    s.append(f"  Zincir sonucu ({iy['baslangic']}..{iy['bitis']}): düz alıma göre {oran_metni(iy['zincir_oran'])}")
    s.append(f"  En iyi yıl ({iy['en_iyi_yil']}) çıkarılınca: {oran_metni(iy['en_iyi_yil_haric'])}")
    s.append(f"  {iy['yil_sayisi']} yılın {sayi_ek(iy['onde_yil'], 'de')} önde | zaman ortalamalı yedek: "
             f"{yuzde(iy['ortalama_yedek_orani'])} | en büyük yedek: {fiyat(iy['en_buyuk_yedek'])} USDT")
    b = iy["bolgeler"]
    s.append(f"  Aylar: pahalı {b['pahalı']} / ucuz {b['ucuz']} / normal {b['normal']}")
    s.append(f"  En büyük düşüş: strateji {yuzde(iy['max_dusus'])}, düz alım {yuzde(iy['taban_max_dusus'])}")
    s.append(f"  HÜKÜM: {hukum(iy)}")
    s.append("\n(* = yıl henüz bitmedi. Yıl oranı 1'in üstü = o yıl düz alıma göre öne geçti.)")
    return "\n".join(s)


def kisa_satis_seviyesi(p: dict, kapanislar: list, ref: dict) -> tuple[float, float]:
    """Kısa kuralın satış seviyesi: (n gün önceki kapanış, seviye).
    kapanislar son elemanı dünse seviye bugünün kapanışı içindir. Kayıtlı satış varsa merdiven."""
    taban = kapanislar[-p["n"]]
    sat = taban * (1 + p["x"])
    if ref["satis_ref"] is not None:
        sat = max(sat, ref["satis_ref"] * (1 + p["x"] / 2))
    return taban, sat


def tavsiye_metni(coin: str, a: dict, kapanislar: list, simdi: float, simdi_kaynak: str,
                  ref: dict, bugun: date) -> str:
    """kapanislar: yalnız bitmiş günlerin kapanışları (son eleman = dün)."""
    s = [f"### {coin} şu an {fiyat(simdi)} $ ({simdi_kaynak})."]
    kisa = a["kurallar"]["kisa"]
    uzun = a["kurallar"]["uzun"]
    gereken = max(200, kisa["secilen"]["n"] if kisa["secilen"] else 0)
    if len(kapanislar) < gereken:
        s.append(f"En az {gereken} günlük kapanış gerekli; veri yetersiz, sinyal hesaplanmadı.")
        return "\n".join(s)

    # --- Kısa vade ---
    p = kisa["secilen"]
    if p is None:
        s.append("Kısa vade: geçmiş veride bu tür kural düz alımı geçemedi; kural önerilmiyor. "
                 "Düzenli alıma devam.")
    else:
        taban, sat = kisa_satis_seviyesi(p, kapanislar, ref)
        satir =(f"Kısa vade: gün sonu kapanış {fiyat(sat)} $'ın üstünde olursa "
                 f"({p['n']} gün önceki {fiyat(taban)} $'a göre +{yuzde(p['x'])}"
                 + (", son satışına göre merdiven" if ref["satis_ref"] is not None else "")
                 + f") ertesi gün elindekinin {yuzde_ek(p['s'], "i")} sat.")
        if simdi >= sat:
            satir += " ŞU AN BU SEVİYENİN ÜSTÜNDE."
        s.append(satir)
        if ref["alim_ref"] is not None:
            al = ref["alim_ref"] * (1 - p["y"])
            s.append(f"  Son işlemin {fiyat(ref['alim_ref'])} $ ({ref['son_islem']['tarih']}). "
                     f"Fiyat {fiyat(al)} $'a düşerse nakdinin {yuzde_ek(p['b'], "ile")} geri al.")
        else:
            s.append(f"  Kayıtlı satışın yok. {fiyat(sat)} $'dan satarsan geri alım seviyesi "
                     f"{fiyat(sat * (1 - p['y']))} $ olur (nakdinin {yuzde_ek(p['b'], "ile")}).")
        if p["t"]:
            s.append(f"  Satıştan sonra {p['t']} gün geri alım olmazsa nakdi 3 ayda eşit parçalarla geri al.")
            if ref["son_satis_tarih"] and ref["alim_ref"] == ref["satis_ref"]:
                gecen = (bugun - date.fromisoformat(ref["son_satis_tarih"])).days
                if gecen >= p["t"]:
                    s.append(f"  Son satışından {gecen} gün geçti: kademeli geri alım zamanı geldi.")
        else:
            s.append("  Geri alım seviyesi gelmezse nakit bekler (süre sınırı yok).")

    # --- Uzun vade ---
    sma = sum(kapanislar[-200:]) / 200
    q = uzun["secilen"]
    bas = f"Uzun vade: 200 günlük ortalama {fiyat(sma)} $ (fiyat/ortalama = {simdi / sma:.2f})."
    if q is None:
        s.append(bas + " Bu tür kural geçmişte düz alımı geçemedi; kural önerilmiyor.")
    else:
        s.append(bas + f" Fiyat {fiyat(q['u'] * sma)} $'ı geçerse elindekinin {yuzde_ek(q['sl'], "i")} sat "
                 f"(sonra {fiyat(q['u'] * 1.25 * sma)} $'da bir {yuzde(q['sl'])} daha). "
                 f"{fiyat(q['l'] * sma)} $'ın altına inerse nakdinin {yuzde_ek(q['bl'], "i")} kullan (en fazla ayda bir).")
        if q["t"]:
            s.append(f"  Uzun vade satışından sonra {q['t']} gün alım olmazsa nakdi 3 ayda eşit parçalarla geri al.")

    # --- Alım ayarı ---
    alim = a["kurallar"].get("alim")
    if alim is not None:
        p = alim["secilen"]
        if p is None:
            s.append("Alım ayarı (satış yok): geçmişte düz alımı geçemedi; kural önerilmiyor.")
        else:
            r = simdi / sma
            bolge = "pahalı" if r > p["u"] else "ucuz" if r < p["l"] else "normal"
            s.append(f"Alım ayarı (satış yok): 200 günlük ortalama {fiyat(sma)} $, "
                     f"fiyat/ortalama = {r:.2f}.")
            if p["k"] == 0:
                s.append(f"  Fiyat {fiyat(p['u'] * sma)} $'ın üstündeyken aylık alımı yapma, "
                         "tamamını yedeğe ayır.")
            else:
                s.append(f"  Fiyat {fiyat(p['u'] * sma)} $'ın üstündeyken aylık alımının "
                         f"{yuzde_ek(p['k'], 'i')} yap, kalanını yedeğe ayır.")
            s.append(f"  Fiyat {fiyat(p['l'] * sma)} $'ın altındayken aylık alımına ek olarak "
                     f"yedeğinin {yuzde_ek(p['g'], 'i')} kullan.")
            s.append(f"  Arada normal alım yap. Şu an: {bolge} bölge.")
            if p["t"]:
                s.append(f"  Yedek {p['t']} günden uzun süre kullanılmazsa 3 ayda eşit parçalarla alıma girer.")

    # --- Kanıt ---
    s.append("Kanıt (her yıl yalnız önceki yıllarla seçilip görmediği yılda denendi, düz aylık alıma göre):")
    kanit_turleri = ["kisa", "uzun", "birlesik"] + (["alim"] if alim is not None else [])
    for tur in kanit_turleri:
        iy = a["kurallar"][tur]["ileri_yuruyus"]
        yillar = " ".join(f"{y['yil']}:{y['oran']:.2f}" for y in iy["yillar"])
        s.append(f"  {KURAL_AD[tur]}: {oran_metni(iy['zincir_oran'])}; yıllar {yillar}. {hukum(iy)}")
    if alim is not None and alim["ileri_yuruyus"]["zincir_oran"] > 1:
        iy = alim["ileri_yuruyus"]
        fark = (iy["zincir_oran"] - 1) * 100
        s.append(f"  UYARI: Alım ayarı kuralı görmediği yıllarda %{fark:.0f} öndeydi ve "
                 f"{iy['yil_sayisi']} yılın {sayi_ek(iy['onde_yil'], 'de')} öne geçti; aynı veride denenen "
                 "dördüncü kural ailesi olduğu için küçük bir üstünlük şans olabilir.")
    elif all(a["kurallar"][t]["ileri_yuruyus"]["zincir_oran"] < 1 for t in kanit_turleri):
        s.append(f"  UYARI: {coin} için hiçbir kural düz düzenli alımı geçemedi. "
                 "En dürüst öneri: aylık düzenli alıma devam et, satış seviyelerini yalnız bilgi olarak gör.")
    return "\n".join(s)
