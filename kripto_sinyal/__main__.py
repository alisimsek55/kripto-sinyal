"""Komut satırı: python -m kripto_sinyal <veri|geritest|tavsiye|islem|takip-baslat|karne|gecmis|coinler>"""

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import durum, kur, veri
from .arama import coin_analizi
from .ayarlar import KOK, ayarlari_oku, yol
from .coinler import komut_coinler
from .gecmis import GecmisHatasi, gecmis_raporu
from .ozet import komut_kisa
from .rapor import geritest_raporu, tavsiye_metni
from .simulasyon import Maliyet, Seri
from .takip import TakipHatasi, karne, takip_baslat


def _maliyet(ayar: dict) -> Maliyet:
    return Maliyet(ayar["aylik_tutar"], ayar["komisyon"], ayar["kayma"])


def komut_veri(ayar: dict) -> None:
    for coin, sembol in ayar["coinler"].items():
        try:
            df, yeni = veri.guncelle(yol(ayar, "veri_klasoru"), sembol)
        except Exception:
            print(f"{coin}: veri güncellenemedi; bağlantıyı ve veri klasörünü kontrol et.")
            continue
        if df.empty:
            print(f"{coin}: fiyat verisi yok; daha sonra 'veri' komutunu yeniden çalıştır.")
            continue
        print(f"{coin}: {len(df)} gün ({df['tarih'].iloc[0]} .. {df['tarih'].iloc[-1]}), {yeni} yeni gün.")
        bos = veri.bosluklar(df)
        if bos:
            print(f"  Uyarı: {len(bos)} veri boşluğu var: {', '.join(bos[:5])}")


def komut_geritest(ayar: dict) -> None:
    m = _maliyet(ayar)
    cikti = {"olusturma": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
             "ayarlar": {"aylik_tutar": m.aylik, "komisyon": m.komisyon, "kayma": m.kayma},
             "coinler": {}}
    for coin, sembol in ayar["coinler"].items():
        df = veri.oku(yol(ayar, "veri_klasoru"), sembol, datetime.now(timezone.utc).date())
        try:
            a = coin_analizi(Seri.tablodan(df), m)
        except ValueError as e:
            print(f"{coin}: {e}")
            continue
        cikti["coinler"][coin] = a
        print(geritest_raporu(coin, a))
        print()
    if not cikti["coinler"]:
        print("Analiz edilebilen fiyat verisi yok; sonuç kaydedilmedi. Önce 'veri' çalıştır.")
        return
    hedef = yol(ayar, "sonuc_dosyasi")
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text(json.dumps(cikti, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Parametreler kaydedildi: {hedef}")


def _haber(coinler: list[str]) -> str:
    try:
        from .haber import haber_ozeti
        return haber_ozeti(coinler)
    except ImportError:
        return "Haberler şu an kullanılamıyor."
    except Exception:
        return "Haberler şu an kullanılamıyor."


def komut_tavsiye(ayar: dict) -> None:
    hedef = yol(ayar, "sonuc_dosyasi")
    if not hedef.exists():
        print("Önce 'python -m kripto_sinyal geritest' çalıştır.")
        return
    sonuc = json.loads(hedef.read_text(encoding="utf-8"))
    try:
        kayit = durum.oku(yol(ayar, "durum_dosyasi"))
    except (OSError, ValueError):
        print("İşlem kaydı okunamadı; kişisel sinyal hesaplanmadı. durum.json dosyasını kontrol et.")
        return
    bugun = datetime.now(timezone.utc).date()
    takip_tablolari = []
    for coin, sembol in ayar["coinler"].items():
        a = sonuc["coinler"].get(coin)
        if a is None:
            print(f"{coin}: geri test sonucu yok, 'geritest' çalıştır.\n")
            continue
        try:
            try:
                df, _ = veri.guncelle(yol(ayar, "veri_klasoru"), sembol)
            except Exception:
                df = veri.oku(yol(ayar, "veri_klasoru"), sembol)
                print(f"({coin}: veri güncellenemedi, kayıtlı veri kullanılıyor.)")
            df = df[df["tarih"].astype(str) < bugun.isoformat()].reset_index(drop=True)
            uyari = veri.gunluk_uyari(df, bugun)
        except (OSError, ValueError, KeyError):
            uyari = "fiyat verisi okunamadı"
        if uyari:
            print(f"{coin}: {uyari}; güncel sinyal hesaplanmadı. Önce 'veri' çalıştır.\n")
            continue
        takip_tablolari.append(df)
        kap = list(df["kapanis"].astype(float))
        simdi = veri.anlik_fiyat(sembol)
        kaynak = "Binance anlık"
        if simdi is None:
            simdi, kaynak = kap[-1], f"anlık fiyat alınamadı, {df['tarih'].iloc[-1]} kapanışı"
        print(tavsiye_metni(coin, a, kap, simdi, kaynak, durum.kisa_referans(kayit, coin), bugun))
        yas = (bugun - datetime.fromisoformat(a["veri_son"]).date()).days
        if yas > 45:
            print(f"  Not: parametreler {a['veri_son']} verisiyle seçildi; 'geritest'i yeniden çalıştır.")
        print()
    print("Haberler:")
    print(_haber(list(ayar["coinler"])))
    print()
    takip_yolu = KOK / "takip" / "baslangic.json"
    if takip_yolu.exists():
        try:
            takip_kaydi = json.loads(takip_yolu.read_text(encoding="utf-8"))
            baslangic = takip_kaydi["baslangic"]
            n = min(sum(df["tarih"].astype(str) > baslangic) for df in takip_tablolari)
            print(f"Takip: {baslangic} tarihinden beri {n} gün; ayrıntı için: "
                  "python -m kripto_sinyal karne")
        except (KeyError, ValueError, json.JSONDecodeError):
            pass
    kur_satiri = kur.kur_satiri(kur.kur_al())
    if kur_satiri:
        print(kur_satiri)
    print("Bu, geçmiş veriden çıkan kurala dayalı bir sinyaldir; yatırım tavsiyesi değildir.")


def komut_islem(ayar: dict, a: argparse.Namespace) -> None:
    yolu = yol(ayar, "durum_dosyasi")
    if a.tur == "liste":
        for i in durum.oku(yolu)["islemler"]:
            print(i)
        return
    if a.coin is None or a.fiyat is None:
        print("Coin ve --fiyat gerekli. Örnek: islem sat DOGE --fiyat 0.25 --yuzde 20")
        sys.exit(2)
    try:
        k = durum.ekle(yolu, a.tur, a.coin, a.fiyat, a.yuzde, a.miktar, a.kural, a.tarih)
    except ValueError as e:
        print(f"Hata: {e}")
        sys.exit(2)
    print(f"Kaydedildi: {k['tarih']} {k['coin']} {k['tur']} {k['fiyat']} $ ({k['kural']})")


def main(argv: list[str] | None = None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="python -m kripto_sinyal",
                                 description="Kurala dayalı kripto sinyali ve geri test.")
    alt = ap.add_subparsers(dest="komut", required=True)
    alt.add_parser("veri", help="Günlük mumları indir / güncelle")
    alt.add_parser("geritest", help="Parametre ara, yıl yıl dürüst test et, sonucu kaydet")
    tv = alt.add_parser("tavsiye", help="Ana coin için kısa özet (--ayrinti: tam çıktı)")
    tv.add_argument("--ayrinti", action="store_true",
                    help="Eski tam çıktı: tüm coinler, kanıt satırları, haberler")
    tv.add_argument("--tutar", type=float, help="Yatıracağın para (TL); kaç coin ettiğini yazar")
    tv.add_argument("--coin", help="Kısa özetin coini (varsayılan ayarlardaki ana_coin)")
    tb = alt.add_parser("takip-baslat", help="İleriye dönük takibi başlat")
    tb.add_argument("--klasor", type=Path, default=KOK / "takip", help="Takip klasörü")
    tb.add_argument("--tarih", help="YYYY-AA-GG; yalnız geçmiş veri gösterimi")
    tb.add_argument("--yeniden", action="store_true", help="Eski başlangıcı arşivleyip yeniden başlat")
    k = alt.add_parser("karne", help="İleriye dönük takip karnesini göster")
    k.add_argument("--klasor", type=Path, default=KOK / "takip", help="Takip klasörü")
    alt.add_parser("coinler", help="Aynı kuralları başka coinlerde de dene (sonuc/coinler.json)")
    g = alt.add_parser("gecmis", help="Gerçek işlem geçmişini karşılaştır")
    g.add_argument("--klasor", type=Path, default=KOK / "gecmis", help="İşlem geçmişi klasörü")
    i = alt.add_parser("islem", help="Gerçek işlemini kaydet (al/sat) ya da listele")
    i.add_argument("tur", choices=["al", "sat", "liste"])
    i.add_argument("coin", nargs="?", help="DOGE, BTC ...")
    i.add_argument("--fiyat", type=float, help="İşlem fiyatı ($)")
    i.add_argument("--yuzde", type=float, help="Satışta elindekinin, alımda nakdinin yüzdesi")
    i.add_argument("--miktar", type=float, help="Satışta coin adedi, alımda USDT tutarı")
    i.add_argument("--kural", choices=["kisa", "uzun", "duzenli"], default="kisa",
                   help="Hangi kurala göre yaptın (varsayılan kisa; aylık alım için duzenli)")
    i.add_argument("--tarih", help="YYYY-AA-GG (varsayılan bugün, UTC)")
    a = ap.parse_args(argv)
    ayar = ayarlari_oku()
    if a.komut == "veri":
        komut_veri(ayar)
    elif a.komut == "geritest":
        komut_geritest(ayar)
    elif a.komut == "tavsiye":
        if a.tutar is not None and (not math.isfinite(a.tutar) or a.tutar <= 0):
            print("Hata: --tutar sonlu ve sıfırdan büyük olmalı (TL).")
            sys.exit(2)
        if a.ayrinti:
            komut_tavsiye(ayar)
        else:
            komut_kisa(ayar, a.coin, a.tutar)
    elif a.komut == "takip-baslat":
        try:
            takip_baslat(ayar, a.klasor, a.tarih, a.yeniden)
        except TakipHatasi as e:
            print(f"Hata: {e}")
            sys.exit(2)
    elif a.komut == "karne":
        try:
            karne(ayar, a.klasor)
        except TakipHatasi as e:
            print(f"Hata: {e}")
            sys.exit(2)
    elif a.komut == "coinler":
        komut_coinler(ayar)
    elif a.komut == "gecmis":
        try:
            k = kur.kur_al()
            metin, _ = gecmis_raporu(ayar, a.klasor, k[0] if k else None)
            print(metin, end="")
        except GecmisHatasi as e:
            print(f"Hata: {e}")
            sys.exit(2)
    else:
        komut_islem(ayar, a)


if __name__ == "__main__":
    main()
