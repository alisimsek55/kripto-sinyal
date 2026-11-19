"""coinler komutu: aynı kuralları başka coinlerde de dener (kanıtın genelliği için).

Kurallar ve seçim yöntemi değişmez (arama.coin_analizi). Her coin için yalnız
"görmediği yıllardaki" zincir sonucu (düz aylık alıma oranı) kaydedilir.
Sonuç sonuc/coinler.json dosyasına yazılır; kişisel bilgi içermez.
"""

import json
import math
from datetime import datetime, timezone

from . import veri
from .arama import coin_analizi
from .ayarlar import yol
from .simulasyon import Maliyet, Seri

EK_SEMBOLLER = ["ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "BNBUSDT", "LTCUSDT",
                "LINKUSDT", "TRXUSDT", "SHIBUSDT"]
KURALLAR = {"kisa": "kisa", "uzun": "uzun", "birlikte": "birlesik", "alim": "alim"}
KURAL_AD = {"kisa": "Kısa (satış)", "uzun": "Uzun (satış)", "birlikte": "Birlikte",
            "alim": "Alım ayarı"}


def dosya_yolu(ayar: dict):
    """sonuc/coinler.json: parametreler.json ile aynı klasör."""
    return yol(ayar, "sonuc_dosyasi").parent / "coinler.json"


def semboller(ayar: dict) -> dict:
    """{coin: sembol}: ayarlardaki coinler (DOGE, BTC) + sabit liste."""
    sonuc = dict(ayar["coinler"])
    for s in EK_SEMBOLLER:
        coin = s.removesuffix("USDT")
        sonuc.setdefault(coin, s)
    return sonuc


def ozetle(coinler: dict) -> dict:
    """Her kural için: düz alımı geçen coin sayısı, toplam, oranların geometrik ortalaması."""
    ozet = {}
    for kural in KURALLAR:
        oranlar = [c[kural] for c in coinler.values()]
        ozet[kural] = {
            "gecen": sum(o > 1 + 1e-9 for o in oranlar),
            "toplam": len(oranlar),
            "geometrik_ortalama": (math.exp(sum(math.log(o) for o in oranlar) / len(oranlar))
                                   if oranlar else None),
        }
    return ozet


def _tablo(ayar: dict, sembol: str, guncelle: bool):
    klasor = yol(ayar, "veri_klasoru")
    if guncelle:
        try:
            veri.guncelle(klasor, sembol)
        except Exception:
            pass  # ağ yoksa kayıtlı veri
    return veri.oku(klasor, sembol, datetime.now(timezone.utc).date())


def komut_coinler(ayar: dict, guncelle: bool = True) -> dict:
    """Coinleri indirir, her birinde coin_analizi çalıştırır, sonucu yazar ve tabloyu basar."""
    m = Maliyet(ayar["aylik_tutar"], ayar["komisyon"], ayar["kayma"])
    sonuc, atlanan = {}, []
    for coin, sembol in semboller(ayar).items():
        df = _tablo(ayar, sembol, guncelle)
        if len(df) == 0:
            atlanan.append(f"{coin} (veri yok)")
            continue
        try:
            a = coin_analizi(Seri.tablodan(df), m)
        except ValueError:
            atlanan.append(f"{coin} (geçmişi çok kısa: {len(df)} gün)")
            continue
        sonuc[coin] = {k: float(a["kurallar"][ad]["ileri_yuruyus"]["zincir_oran"])
                       for k, ad in KURALLAR.items()}
    cikti = {"tarih": datetime.now(timezone.utc).date().isoformat(), "coinler": sonuc,
             "ozet": ozetle(sonuc)}
    hedef = dosya_yolu(ayar)
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text(json.dumps(cikti, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(tablo_metni(cikti, atlanan))
    print(f"Kaydedildi: {hedef}")
    return cikti


def tablo_metni(cikti: dict, atlanan: list[str] | None = None) -> str:
    """Kısa Türkçe tablo: her coin ve kural için düz aylık alıma oran."""
    s = ["Görmediği yıllarda düz aylık alıma göre sonuç (1'in üstü = düz alımı geçti):",
         f"{'Coin':<6}" + "".join(f"{KURAL_AD[k]:>14}" for k in KURALLAR)]
    for coin, r in cikti["coinler"].items():
        s.append(f"{coin:<6}" + "".join(f"{r[k]:>14.3f}" for k in KURALLAR))
    s.append("")
    for k, o in cikti["ozet"].items():
        g = o["geometrik_ortalama"]
        s.append(f"{KURAL_AD[k]}: {o['toplam']} coinin {o['gecen']} tanesinde düz alımı geçti; "
                 f"ortalama oran x{g:.3f}." if g is not None else f"{KURAL_AD[k]}: sonuç yok.")
    if atlanan:
        s.append("Atlanan: " + ", ".join(atlanan))
    s.append("Bunlar geçmiş testtir; yatırım tavsiyesi değildir.")
    return "\n".join(s)
