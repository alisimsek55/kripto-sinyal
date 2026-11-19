"""Binance işlem geçmişini gerçek ve varsayımsal sonuçlarla karşılaştırır."""

import csv
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from . import veri
from .ayarlar import yol
from .rapor import fiyat, tl_metni
from .simulasyon import Maliyet, coin_al

CSV_BASLIK = ["Date(UTC)", "Pair", "Side", "Price", "Executed", "Amount", "Fee",
              "orderNo", "aorConvertPair", "aorConvertRate"]
_TUTAR = re.compile(r"^([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)([A-Za-z0-9]+)$")


class GecmisHatasi(ValueError):
    """İşlem geçmişi okunamadığında oluşur."""


@dataclass(frozen=True)
class Islem:
    zaman: datetime
    parite: str
    yon: str
    fiyat: float
    executed: float
    base: str
    amount: float
    quote: str
    fee: float
    fee_asset: str
    order_no: str
    dosya: str
    sira: int


@dataclass
class Giris:
    """Dışarıdan para giren bir alım satırı.
    gercek_coin = net coin * dışarıdan para / maliyet (ücret türü ne olursa olsun)."""
    zaman: datetime
    tutar: float
    fiyat: float
    gercek_coin: float

    @property
    def satmadan_coin(self) -> float:
        """"Hiç satmasaydın"a yazılan coin: dışarıdan paranın aldığı net coin."""
        return self.gercek_coin


@dataclass
class SatisTuru:
    order_no: str
    zaman: datetime
    satilan: float = 0.0
    satis_fee_base: float = 0.0
    amount: float = 0.0
    alinan_usdt: float = 0.0
    harcanan_usdt: float = 0.0
    brut_alinan_coin: float = 0.0
    alinan_coin: float = 0.0
    bekleyen_usdt: float = 0.0

    @property
    def ortalama_satis(self) -> float:
        return self.amount / self.satilan if self.satilan else 0.0

    @property
    def ortalama_alis(self) -> float:
        return self.harcanan_usdt / self.brut_alinan_coin if self.brut_alinan_coin else 0.0

    @property
    def durum(self) -> str:
        esik = 1e-9 * max(1.0, self.alinan_usdt)
        if self.harcanan_usdt <= esik:
            return "cepte bekliyor"
        if self.bekleyen_usdt <= esik:
            return "tamamı geri alındı"
        return f"kısmen ({_usdt(self.bekleyen_usdt)} USDT cepte)"


@dataclass
class Defter:
    base: str
    coin: float = 0.0
    cep: float = 0.0
    giren: float = 0.0
    onceki_coin: float = 0.0
    komisyon_diger: dict[str, float] = field(default_factory=dict)
    girisler: list[Giris] = field(default_factory=list)
    turlar: list[SatisTuru] = field(default_factory=list)
    satir_sayisi: int = 0
    emir_sayisi: int = 0
    ilk: datetime | None = None
    son: datetime | None = None
    satis_fee_base: float = 0.0


@dataclass(frozen=True)
class Sonuc:
    ad: str
    coin: float
    nakit: float
    deger: float


@dataclass
class Analiz:
    defter: Defter
    p: float
    d: str
    gercek: Sonuc
    satmadan: Sonuc
    aylik: Sonuc
    ay_sayisi: int
    aylik_alim_tarihleri: list[str]
    kimlik_farki: float
    kimlik_duzeltme: float


def _usdt(x: float, isaretli: bool = False) -> str:
    """USDT tutarı: tam 2 ondalık, binlik ayracı yok."""
    return f"{x:+.2f}" if isaretli else f"{x:.2f}"


def _coin(x: float, isaretli: bool = False) -> str:
    """Coin miktarı: 100 ve üstü ondalıksız, altı 2 ondalık."""
    n = 0 if abs(x) >= 100 else 2
    return f"{x:+.{n}f}" if isaretli else f"{x:.{n}f}"


def _fyt(x: float) -> str:
    """Fiyat: 4 ondalık."""
    return f"{x:.4f}"


def miktar(x: float) -> str:
    """Coin miktarını sekiz ondalığa kadar gösterir."""
    return f"{x:.8f}".rstrip("0").rstrip(".") or "0"


def _sayili_deger(metin: str, alan: str, dosya: str) -> tuple[float, str]:
    eslesme = _TUTAR.fullmatch(metin.strip())
    if eslesme is None:
        raise GecmisHatasi(f"{dosya}: {alan} alanı okunamadı: {metin}")
    return float(eslesme.group(1)), eslesme.group(2).upper()


def csvleri_oku(klasor: Path) -> list[Islem]:
    """Klasördeki CSV satırlarını eskiden yeniye doğru okur."""
    dosyalar = sorted(klasor.glob("*.csv")) if klasor.exists() else []
    if not dosyalar:
        raise GecmisHatasi(
            f"CSV bulunamadı. Binance işlem geçmişi dışa aktarımını {klasor} klasörüne koy.")

    tum: list[Islem] = []
    araliklar: list[tuple[datetime, datetime, str]] = []
    for dosya in dosyalar:
        try:
            with dosya.open("r", encoding="utf-8-sig", newline="") as f:
                okuyucu = csv.reader(f)
                baslik = next(okuyucu, None)
                if baslik != CSV_BASLIK:
                    raise GecmisHatasi(f"{dosya.name}: CSV başlığı beklenen biçimde değil.")
                dosya_islemleri = []
                for sira, satir in enumerate(okuyucu):
                    if len(satir) != len(CSV_BASLIK):
                        raise GecmisHatasi(f"{dosya.name}: {sira + 2}. satırın alan sayısı yanlış.")
                    kayit = dict(zip(CSV_BASLIK, satir))
                    try:
                        zaman = datetime.strptime(kayit["Date(UTC)"], "%Y-%m-%d %H:%M:%S")
                        yon = kayit["Side"].upper()
                        if yon not in ("BUY", "SELL"):
                            raise ValueError
                        executed, base = _sayili_deger(kayit["Executed"], "Executed", dosya.name)
                        amount, quote = _sayili_deger(kayit["Amount"], "Amount", dosya.name)
                        fee, fee_asset = _sayili_deger(kayit["Fee"], "Fee", dosya.name)
                        islem = Islem(zaman, kayit["Pair"].upper(), yon, float(kayit["Price"]),
                                      executed, base, amount, quote, fee, fee_asset,
                                      kayit["orderNo"], dosya.name, sira)
                    except GecmisHatasi:
                        raise
                    except (TypeError, ValueError):
                        raise GecmisHatasi(f"{dosya.name}: {sira + 2}. satır okunamadı.") from None
                    dosya_islemleri.append(islem)
        except UnicodeDecodeError:
            raise GecmisHatasi(f"{dosya.name}: dosya UTF-8 olarak okunamadı.") from None

        if dosya_islemleri:
            araliklar.append((min(x.zaman for x in dosya_islemleri),
                              max(x.zaman for x in dosya_islemleri), dosya.name))
        tum.extend(dosya_islemleri)

    for i, (bas1, son1, ad1) in enumerate(araliklar):
        for bas2, son2, ad2 in araliklar[i + 1:]:
            if max(bas1, bas2) <= min(son1, son2):
                raise GecmisHatasi(f"Tarih aralıkları çakışıyor: {ad1} ve {ad2}.")

    return sorted(tum, key=lambda x: (x.zaman, x.dosya, -x.sira))


def _ucreti_ayir(islem: Islem) -> tuple[float, float, float]:
    """Baz, kotasyon ve diğer varlık ücretlerini döndürür."""
    return (islem.fee if islem.fee_asset == islem.base else 0.0,
            islem.fee if islem.fee_asset == islem.quote else 0.0,
            islem.fee if islem.fee_asset not in (islem.base, islem.quote) else 0.0)


def defteri_hesapla(islemler: list[Islem], base: str) -> Defter:
    """Bir varlığın gerçek para ve coin akışını hesaplar."""
    satirlar = [x for x in islemler if x.base == base and x.quote == "USDT"]
    d = Defter(base=base, satir_sayisi=len(satirlar),
               emir_sayisi=len({x.order_no for x in satirlar}))
    if not satirlar:
        return d
    d.ilk, d.son = satirlar[0].zaman, satirlar[-1].zaman
    tur_by_order: dict[str, SatisTuru] = {}
    kuyruk: list[SatisTuru] = []

    for islem in satirlar:
        fee_base, fee_quote, fee_diger = _ucreti_ayir(islem)
        if fee_diger:
            d.komisyon_diger[islem.fee_asset] = d.komisyon_diger.get(islem.fee_asset, 0.0) + fee_diger

        if islem.yon == "SELL":
            satilan_defter = islem.executed + fee_base
            if satilan_defter > d.coin:
                d.onceki_coin += satilan_defter - d.coin
                d.coin = 0.0
            else:
                d.coin -= satilan_defter
            net = islem.amount - fee_quote
            d.cep += net
            d.satis_fee_base += fee_base

            tur = tur_by_order.get(islem.order_no)
            if tur is None:
                tur = SatisTuru(islem.order_no, islem.zaman)
                tur_by_order[islem.order_no] = tur
                d.turlar.append(tur)
            tur.satilan += islem.executed
            tur.satis_fee_base += fee_base
            tur.amount += islem.amount
            tur.alinan_usdt += net
            tur.bekleyen_usdt += net
            if tur not in kuyruk:
                kuyruk.append(tur)
            continue

        maliyet = islem.amount + fee_quote
        cepten = min(d.cep, maliyet)
        disaridan = maliyet - cepten
        d.cep -= cepten
        net_coin = islem.executed - fee_base
        d.coin += net_coin

        kalan = cepten
        for tur in list(kuyruk):
            if kalan <= 1e-12:
                break
            kullanilan = min(kalan, tur.bekleyen_usdt)
            oran = kullanilan / maliyet if maliyet else 0.0
            tur.harcanan_usdt += kullanilan
            tur.brut_alinan_coin += islem.executed * oran
            tur.alinan_coin += net_coin * oran
            tur.bekleyen_usdt -= kullanilan
            kalan -= kullanilan
            if tur.bekleyen_usdt <= 1e-12:
                tur.bekleyen_usdt = 0.0
                kuyruk.remove(tur)

        if disaridan > 1e-12:
            # Maliyet = Amount (+ kotasyon ücreti); net coin = Executed (- baz ücreti).
            # Üçüncü varlık ücreti (ör. BNB) coin, cep ve maliyeti değiştirmez.
            d.giren += disaridan
            gercek_coin = net_coin * (disaridan / maliyet if maliyet else 0.0)
            d.girisler.append(Giris(islem.zaman, disaridan, islem.fiyat, gercek_coin))

    if abs(d.cep) <= 1e-10:
        d.cep = 0.0
    return d


def _ay_farki(bas: datetime, son: str) -> int:
    d = datetime.strptime(son, "%Y-%m-%d")
    return (d.year - bas.year) * 12 + d.month - bas.month + 1


def sonuclari_hesapla(d: Defter, fiyatlar: pd.DataFrame, m: Maliyet) -> Analiz:
    """Üç sonucu son bitmiş günlük mumla hesaplar."""
    if d.ilk is None or fiyatlar.empty:
        raise GecmisHatasi(f"{d.base}: hesaplama için veri yok.")
    tablo = fiyatlar.copy()
    tablo["tarih"] = tablo["tarih"].astype(str)
    tablo = tablo.sort_values("tarih").reset_index(drop=True)
    p, son_tarih = float(tablo["kapanis"].iloc[-1]), tablo["tarih"].iloc[-1]
    ay_sayisi = _ay_farki(d.ilk, son_tarih)
    if ay_sayisi <= 0:
        raise GecmisHatasi(f"{d.base}: fiyat verisi işlem geçmişinden önce bitiyor.")

    gercek = Sonuc("Gerçekte yaptığın", d.coin, d.cep, d.coin * p + d.cep)
    satmadan_coin = d.onceki_coin + sum(x.satmadan_coin for x in d.girisler)
    satmadan = Sonuc("Hiç satmasaydın", satmadan_coin, 0.0, satmadan_coin * p)

    parca = d.giren / ay_sayisi
    ilk_gun = d.ilk.strftime("%Y-%m-%d")
    aylar = pd.period_range(d.ilk.strftime("%Y-%m"), son_tarih[:7], freq="M")
    aylik_coin = d.onceki_coin
    alim_tarihleri: list[str] = []
    for no, ay in enumerate(aylar):
        uygun = tablo[tablo["tarih"].str.startswith(str(ay))]
        if no == 0:
            uygun = uygun[uygun["tarih"] >= ilk_gun]
        if uygun.empty:
            raise GecmisHatasi(f"{d.base}: {ay} için bitmiş fiyat mumu yok.")
        mum = uygun.iloc[0]
        aylik_coin += coin_al(parca, float(mum["acilis"]), m)
        alim_tarihleri.append(str(mum["tarih"]))
    aylik = Sonuc("Düz aylık alım", aylik_coin, 0.0, aylik_coin * p)

    tur_farki = sum(x.alinan_coin - x.satilan for x in d.turlar)
    dis_giris_duzeltme = sum(x.gercek_coin - x.satmadan_coin for x in d.girisler)
    # "Önceki coin hariç" satış denklemine önceki coin ve baz ücretleri geri eklenir.
    duzeltme = -d.onceki_coin - d.satis_fee_base + dis_giris_duzeltme
    takip_edilen_satis = sum(x.satilan for x in d.turlar) - d.onceki_coin
    sag = sum(x.alinan_coin for x in d.turlar) - takip_edilen_satis + duzeltme
    kimlik_farki = (gercek.coin - satmadan.coin) - sag
    return Analiz(d, p, son_tarih, gercek, satmadan, aylik, ay_sayisi,
                  alim_tarihleri, kimlik_farki, duzeltme)


def _kar_zarar(s: Sonuc, giren: float) -> str:
    fark = s.deger - giren
    oran = fark / giren if giren else None
    isaret = "+" if fark >= 0 else ""
    yuzde = f"%{oran * 100:.2f}" if oran is not None else "hesaplanamaz"
    return f"{isaret}{_usdt(fark)} USDT ({yuzde})"


def _sonuc_satiri(s: Sonuc, gercek: Sonuc, giren: float, base: str,
                  kur: float | None = None) -> list[str]:
    tl = f"; değer ≈ {tl_metni(s.deger * kur)} TL" if kur else ""
    satirlar = [f"{s.ad}: {_coin(s.coin)} {base}; {_usdt(s.deger)} USDT; "
                f"kâr/zarar {_kar_zarar(s, giren)}{tl}"]
    if s.ad != gercek.ad:
        coin_farki = s.coin - gercek.coin
        coin_orani = coin_farki / gercek.coin if gercek.coin else None
        deger_farki = s.deger - gercek.deger
        oran = f"%{coin_orani * 100:.2f}" if coin_orani is not None else "hesaplanamaz"
        satirlar.append(f"  Gerçeğe göre: {_coin(coin_farki, True)} {base} ({oran}); "
                        f"{_usdt(deger_farki, True)} USDT.")
    return satirlar


def analiz_metni(a: Analiz, kur: float | None = None) -> str:
    """Bir varlığın rapor metnini oluşturur. kur verilirse sonuçlara TL karşılığı eklenir."""
    d = a.defter
    satirlar = [f"=== {d.base} ===",
                f"Emir: {d.emir_sayisi}; satır: {d.satir_sayisi}.",
                f"Dönem: {d.ilk:%Y-%m-%d %H:%M:%S} .. {d.son:%Y-%m-%d %H:%M:%S} UTC.",
                f"Giren: {_usdt(d.giren)} USDT; cep: {_usdt(d.cep)} USDT."]
    if kur:
        satirlar.append(f"TL karşılıkları bugünkü kurla hesaplandı (1 USDT = {kur:.2f} TL); "
                        "geçmişteki alımların o günkü TL maliyetini göstermez.")
    if d.onceki_coin > 0:
        satirlar.append(f"Önceki coin: {_coin(d.onceki_coin)} {d.base}. Dosya bu coinlerin "
                        "nereden geldiğini göstermiyor; daha eski geçmiş eksik olabilir.")
    if d.komisyon_diger:
        metin = ", ".join(f"{_coin(tutar)} {varlik}" for varlik, tutar in sorted(d.komisyon_diger.items()))
        satirlar.append(f"Diğer varlık komisyonları: {metin}.")
    if d.coin > 0:
        satirlar.append(f"Başa baş fiyatı: {_fyt((d.giren - d.cep) / d.coin)} USDT.")
    satirlar.append(f"Son bitmiş kapanış: {_fyt(a.p)} USDT ({a.d}).")
    satirlar.extend(_sonuc_satiri(a.gercek, a.gercek, d.giren, d.base, kur))
    satirlar.extend(_sonuc_satiri(a.satmadan, a.gercek, d.giren, d.base, kur))
    satirlar.extend(_sonuc_satiri(a.aylik, a.gercek, d.giren, d.base, kur))
    satirlar.append(f"Düz aylık alım: {a.ay_sayisi} ay, ayda {_usdt(d.giren / a.ay_sayisi)} USDT.")

    satirlar.append("\nSatış turları")
    satirlar.append("Tarih | Satılan coin | Ort. satış | Alınan USDT | Geri alınan coin | Ort. geri alım | Coin farkı | Durum")
    for tur in d.turlar:
        fark = tur.alinan_coin - tur.satilan
        oran = fark / tur.satilan if tur.satilan else 0.0
        ort_alis = _fyt(tur.ortalama_alis) if tur.brut_alinan_coin else "-"
        satirlar.append(f"{tur.zaman:%Y-%m-%d} | {_coin(tur.satilan)} | "
                        f"{_fyt(tur.ortalama_satis)} | {_usdt(tur.alinan_usdt)} | "
                        f"{_coin(tur.alinan_coin)} | {ort_alis} | {_coin(fark, True)} "
                        f"(%{oran * 100:+.2f}) | {tur.durum}")
    tamamlanan = [x for x in d.turlar if x.harcanan_usdt > 1e-9]
    toplam_satilan = sum(x.satilan for x in tamamlanan)
    toplam_alinan = sum(x.alinan_coin for x in tamamlanan)
    satirlar.append(f"Toplam: {_coin(toplam_satilan)} {d.base} satıldı; {_coin(toplam_alinan)} {d.base} geri alındı; "
                    f"net {_coin(toplam_alinan - toplam_satilan, True)} {d.base}.")
    satirlar.append("Tutarlılık: gerçek - hiç satmasaydın = geri alınan - önceki coin hariç satış + düzeltme.")
    satirlar.append(f"Düzeltme önceki coin, baz satış ücreti ve giriş ücret payıdır: "
                    f"{_coin(a.kimlik_duzeltme, True)} {d.base}; kontrol farkı {a.kimlik_farki:+.12g} {d.base}.")
    return "\n".join(satirlar)


UYARILAR = [
    "Her dışa aktarma dosyası en fazla bir yılı kapsar; önceki işlemler eksik olabilir.",
    "Satıştan gelen USDT'nin borsada kaldığı ve sonraki alımlarda yeni paradan önce kullanıldığı varsayılır.",
    "Bir yıl ve birkaç satış turu beceriyi şanstan ayırmaya yetmez; bu karşılaştırma olanı anlatır, geleceği tahmin etmez.",
]


def fiyat_verisini_yukle(ayar: dict, coin: str) -> pd.DataFrame:
    """Fiyatı sessizce yeniler; ağ yoksa kayıtlı veriyi kullanır."""
    sembol = ayar["coinler"][coin]
    try:
        df, _ = veri.guncelle(yol(ayar, "veri_klasoru"), sembol)
    except Exception:
        df = veri.oku(yol(ayar, "veri_klasoru"), sembol)
    bugun = datetime.now(timezone.utc).date().isoformat()
    return df[df["tarih"].astype(str) < bugun].reset_index(drop=True)


def defter_oku(klasor: Path, coin: str) -> Defter | None:
    """Bir coinin defterini dosya yazmadan hesaplar; o coinin USDT işlemi yoksa None."""
    ilgili = [x for x in csvleri_oku(klasor) if x.parite == coin + "USDT"]
    return defteri_hesapla(ilgili, coin) if ilgili else None


def gecmis_raporu(ayar: dict, klasor: Path,
                  kur: float | None = None) -> tuple[str, list[Analiz]]:
    """Raporu üretir ve klasörde rapor.txt dosyasına yazar."""
    islemler = csvleri_oku(klasor)
    destek = {coin: sembol for coin, sembol in ayar["coinler"].items()
              if sembol == coin + "USDT"}
    sayilar = Counter(x.parite for x in islemler)
    atlanan = {parite: n for parite, n in sayilar.items()
               if parite not in set(destek.values())}
    satirlar: list[str] = []
    if atlanan:
        liste = ", ".join(f"{parite} ({n} satır)" for parite, n in sorted(atlanan.items()))
        satirlar.append(f"Uyarı: Atlanan pariteler: {liste}.")

    analizler = []
    m = Maliyet(ayar["aylik_tutar"], ayar["komisyon"], ayar["kayma"])
    for coin in destek:
        ilgili = [x for x in islemler if x.parite == destek[coin]]
        if not ilgili:
            continue
        d = defteri_hesapla(ilgili, coin)
        a = sonuclari_hesapla(d, fiyat_verisini_yukle(ayar, coin), m)
        analizler.append(a)
        if satirlar:
            satirlar.append("")
        satirlar.append(analiz_metni(a, kur))
    if not analizler:
        raise GecmisHatasi("Analiz edilebilen USDT paritesi bulunamadı.")
    satirlar.append("")
    satirlar.extend(UYARILAR)
    metin = "\n".join(satirlar) + "\n"
    klasor.mkdir(parents=True, exist_ok=True)
    (klasor / "rapor.txt").write_text(metin, encoding="utf-8")
    return metin, analizler
