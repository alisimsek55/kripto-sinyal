"""Yayın öncesi gizlilik kontrolü.

Herkese açık bir depoya gönderilmeden önce bakiye, işlem geçmişi ve gizli anahtar
sızıntısını arar. Hassas değerler yalnız çalışma anında, bellekte hesaplanır;
hiçbir dosyaya yazılmaz ve ekrana yalnız maskeli biçimde basılır.

Kullanım:
    python araclar/yayin_kontrol.py --agac
    python araclar/yayin_kontrol.py --commitler <rev-aralığı>
    python araclar/yayin_kontrol.py --pre-push   (git kancası; stdin'den okur)

Çıkış kodu: 0 temiz, 1 engellendi, 2 kullanım/çalışma hatası.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

PROJE = Path(__file__).resolve().parents[1]
if str(PROJE) not in sys.path:
    sys.path.insert(0, str(PROJE))

SIFIR_SHA = "0" * 40
BAND = 0.015          # portföy değeri için ±%1,5
PORTFOY_ALT = 1000.0  # bundan küçük sayılar portföy kontrolüne girmez
GUN_SAYISI = 120      # son kaç günlük kapanış kullanılır

# Binance başlığı parça parça kurulur ki bu dosya kendini yakalamasın.
_BASLIK_ALANLARI = ["Date\\(UTC\\)", "Pair", "Side", "Price", "Executed", "Amount",
                    "Fee", "order" + "No"]
BASLIK_DESENI = re.compile(r'\s*,\s*'.join(r'"?' + a + r'"?' for a in _BASLIK_ALANLARI))

OZEL_YOLLAR = {"durum.json", "veri/kur.json", "takip/karne.json"}
ANAHTAR_DOSYALARI = re.compile(
    r"(^|/)(id_rsa|id_dsa|id_ecdsa|id_ed25519)$|\.(pem|key|p12|pfx|keystore|jks)$", re.I)

_TIRE5 = "-" * 5
GIZLI_DESENLER = [
    ("özel anahtar bloğu", re.compile(_TIRE5 + r"BEGIN[A-Z0-9 ]*" + _TIRE5 + "?")),
    ("anahtar/şifre ataması", re.compile(
        r"(?i)\b[\w-]*(api[_-]?key|api[_-]?secret|secret[_-]?key|secret|access[_-]?token|"
        r"auth[_-]?token|token|passwd|password|private[_-]?key)\b[\"']?\s*[:=]\s*[\"']?"
        r"([A-Za-z0-9_\-+/=.]{8,})")),
    ("Bearer başlığı", re.compile(r"(?i)authorization\s*:\s*bearer\s+([A-Za-z0-9_\-.+/=]{8,})")),
    ("AWS anahtarı", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub belirteci", re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})")),
    ("API anahtarı (sk-)", re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}")),
    ("Slack belirteci", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("anahtar adlı uzun hex/base64", re.compile(
        r"(?i)\b[\w-]*(key|secret|token|signature|imza|anahtar)[\w-]*\b[\"']?\s*[:=]\s*[\"']?"
        r"([A-Fa-f0-9]{32,}|[A-Za-z0-9+/]{40,}={0,2})")),
]
# Bir atamanın değeri bunlardan biriyse gerçek gizli bilgi sayılmaz.
_ZARARSIZ = re.compile(r"(?i)^(none|null|true|false|os\.environ.*|getenv.*|ayar.*|\$\{?\w+\}?)$")

SAYI = re.compile(r"(?<![\w])\d(?:[\d.,]*\d)?")


@dataclass
class Bulgu:
    yer: str
    kategori: str
    maske: str = ""

    def metin(self) -> str:
        return f"{self.yer} [{self.kategori}]" + (f" {self.maske}" if self.maske else "")


@dataclass
class Hassas:
    """Gerçek CSV'lerden bellekte türetilen değerler."""
    kesin: dict[str, str] = field(default_factory=dict)   # biçim -> kategori
    emirler: set[str] = field(default_factory=set)
    portfoy: list[tuple[float, str]] = field(default_factory=list)  # (değer, kategori)
    not_: str = ""

    @property
    def bos(self) -> bool:
        return not (self.kesin or self.emirler or self.portfoy)


def maskele(deger: str) -> str:
    """Değerin yalnız ilk iki karakterini gösterir."""
    deger = deger.strip()
    return (deger[:2] if len(deger) > 4 else deger[:1]) + "***"


# ---------------------------------------------------------------- sayı biçimleri

def _binlik(tam: str, ayrac: str) -> str:
    parcalar = []
    while len(tam) > 3:
        parcalar.insert(0, tam[-3:])
        tam = tam[:-3]
    parcalar.insert(0, tam)
    return ayrac.join(parcalar)


def tam_bicimleri(n: int) -> set[str]:
    """12345 / 12.345 / 12,345"""
    s = str(abs(n))
    return {s, _binlik(s, "."), _binlik(s, ",")}


def ondalik_bicimleri(x: float, basamak: int) -> set[str]:
    """Nokta ve virgül ondalıklı, binlik ayraçlı ve ayraçsız biçimler."""
    s = f"{abs(x):.{basamak}f}"
    tam, kesir = s.split(".")
    return {f"{tam}.{kesir}", f"{tam},{kesir}",
            f"{_binlik(tam, ',')}.{kesir}", f"{_binlik(tam, '.')},{kesir}"}


def anlamli_basamak(s: str) -> int:
    rakam = s.replace(".", "").replace(",", "").lstrip("0")
    if "." not in s and "," not in s:
        rakam = rakam.rstrip("0")
    return len(rakam)


def sayi_yorumlari(belirtec: str) -> set[float]:
    """Bir sayı yazımının olası değerleri (binlik/ondalık ayraç belirsizliği için)."""
    sonuc: set[float] = set()
    for ondalik, binlik in ((".", ","), (",", ".")):
        govde = belirtec
        if binlik in govde:
            ana, _, kuyruk = govde.partition(ondalik)
            if binlik in kuyruk:
                continue
            gruplar = ana.split(binlik)
            if not (1 <= len(gruplar[0]) <= 3 and all(len(g) == 3 for g in gruplar[1:])):
                continue
            govde = govde.replace(binlik, "")
        if govde.count(ondalik) > 1:
            # Hepsi binlik ayracı olabilir: 1.234.567
            gruplar = govde.split(ondalik)
            if 1 <= len(gruplar[0]) <= 3 and all(len(g) == 3 for g in gruplar[1:]):
                sonuc.add(float("".join(gruplar)))
            continue
        try:
            sonuc.add(float(govde.replace(ondalik, ".")))
        except ValueError:
            pass
        # Tek ayraç ve 3 haneli kuyruk binlik de olabilir: 907.015
        if govde.count(ondalik) == 1:
            ana, kuyruk = govde.split(ondalik)
            if 1 <= len(ana) <= 3 and len(kuyruk) == 3:
                sonuc.add(float(ana + kuyruk))
    return sonuc


def _tarih_parcasi(satir: str, bas: int, son: int) -> bool:
    """2026-11-14 ya da 12:30:00 gibi tarih/saat parçası mı?"""
    once = satir[bas - 2:bas] if bas >= 2 else ""
    sonra = satir[son:son + 2]
    return (len(once) == 2 and once[1] in "-:/" and once[0].isdigit()) or \
           (len(sonra) == 2 and sonra[0] in "-:/" and sonra[1].isdigit())


# ---------------------------------------------------------------- hassas değerler

def _ham_csv(dosya: Path) -> list[dict[str, str]]:
    metin = dosya.read_text(encoding="utf-8-sig", errors="replace")
    satirlar = list(csv.reader(io.StringIO(metin)))
    if not satirlar:
        return []
    return [dict(zip(satirlar[0], s)) for s in satirlar[1:]]


def hassas_degerleri_hesapla(kok: Path) -> Hassas:
    h = Hassas()
    klasor = kok / "gecmis"
    dosyalar = sorted(klasor.glob("*.csv")) if klasor.is_dir() else []
    if not dosyalar:
        h.not_ = "Not: gecmis/ içinde CSV yok; bakiye ve portföy kontrolleri atlandı."
        return h

    # Ham alanlar: emir numaraları, Executed ve Amount (yazıldığı gibi).
    sayi_on = re.compile(r"^[+-]?(\d+(?:\.\d*)?|\.\d+)")
    for dosya in dosyalar:
        for kayit in _ham_csv(dosya):
            emir = (kayit.get("orderNo") or "").strip()
            if len(emir) >= 6:
                h.emirler.add(emir)
            for alan in ("Executed", "Amount"):
                e = sayi_on.match((kayit.get(alan) or "").strip())
                if not e:
                    continue
                ham = e.group(1)
                if anlamli_basamak(ham) < 4:
                    continue
                h.kesin[ham] = "işlem miktarı"
                if "." in ham:
                    kisa = ham.rstrip("0").rstrip(".")
                    if anlamli_basamak(kisa) >= 4:
                        h.kesin[kisa] = "işlem miktarı"
                    h.kesin[ham.replace(".", ",")] = "işlem miktarı"

    # Defter: gecmis.py fonksiyonlarıyla.
    try:
        from kripto_sinyal.gecmis import csvleri_oku, defteri_hesapla
        islemler = csvleri_oku(klasor)
    except Exception as hata:  # noqa: BLE001
        raise RuntimeError(f"defter hesaplanamadı ({type(hata).__name__}); "
                           "gizlilik kontrolü tamamlanamadı.") from None

    kur = None
    kur_dosyasi = kok / "veri" / "kur.json"
    if kur_dosyasi.exists():
        try:
            kur = float(json.loads(kur_dosyasi.read_text(encoding="utf-8"))["kur"])
        except Exception:  # noqa: BLE001
            kur = None

    tabanlar = sorted({x.base for x in islemler if x.quote == "USDT"})
    for taban in tabanlar:
        d = defteri_hesapla(islemler, taban)
        if d.coin >= 1:
            for b in tam_bicimleri(round(d.coin)):
                if anlamli_basamak(b) >= 3:
                    h.kesin[b] = "elde tutulan coin"
        for ad, deger in (("dışarıdan giren para", d.giren), ("cep (nakit)", d.cep)):
            if abs(deger) >= 1:
                for b in ondalik_bicimleri(deger, 2):
                    h.kesin[b] = ad
        if d.coin > 0 and d.giren - d.cep > 0:
            for b in ondalik_bicimleri((d.giren - d.cep) / d.coin, 4):
                if anlamli_basamak(b) >= 3:
                    h.kesin[b] = "başa baş fiyatı"

        fiyat_dosyasi = kok / "veri" / f"{taban}USDT_1d.csv"
        if d.coin > 0 and fiyat_dosyasi.exists():
            import pandas as pd
            kapanis = pd.read_csv(fiyat_dosyasi)["kapanis"].astype(float).tail(GUN_SAYISI)
            for k in kapanis:
                h.portfoy.append((d.coin * k, "portföy değeri (USDT)"))
                if kur:
                    h.portfoy.append((d.coin * k * kur, "portföy değeri (TL)"))
    return h


# ---------------------------------------------------------------- tarama

class Tarayici:
    def __init__(self, hassas: Hassas):
        self.h = hassas
        self._kesin = None
        if hassas.kesin:
            alternatif = "|".join(re.escape(b) for b in sorted(hassas.kesin, key=len, reverse=True))
            self._kesin = re.compile(rf"(?<![\w.,])({alternatif})(?![\d]|[.,]\d)")
        self._portfoy = sorted(hassas.portfoy)

    def _portfoyde(self, deger: float) -> str | None:
        if deger < PORTFOY_ALT:
            return None
        for hedef, kategori in self._portfoy:
            if abs(deger - hedef) <= BAND * hedef:
                return kategori
        return None

    def yol(self, yol: str, ilk_satir: str | None) -> list[str]:
        """Yol kurallarını uygular; kategori listesi döndürür."""
        yol = yol.replace("\\", "/").lower()
        sonuc = []
        if yol.startswith("gecmis/"):
            sonuc.append("özel klasör gecmis/")
        if yol in OZEL_YOLLAR:
            sonuc.append("özel dosya")
        ad = yol.rsplit("/", 1)[-1]
        if ad == ".env" or ad.startswith(".env."):
            sonuc.append(".env dosyası")
        if ANAHTAR_DOSYALARI.search(yol):
            sonuc.append("özel anahtar dosyası")
        if yol.lower().endswith(".csv") and ilk_satir is not None and \
                BASLIK_DESENI.search(ilk_satir.lstrip("﻿")):
            sonuc.append("Binance işlem CSV'si")
        return sonuc

    def metin(self, metin: str) -> list[tuple[int, str, str]]:
        """(satır no, kategori, maske) listesi."""
        bulgular = []
        for no, satir in enumerate(metin.splitlines(), 1):
            if BASLIK_DESENI.search(satir):
                bulgular.append((no, "Binance CSV başlığı", ""))
            for emir in self.h.emirler:
                if emir in satir:
                    bulgular.append((no, "emir numarası (orderNo)", maskele(emir)))
            for ad, desen in GIZLI_DESENLER:
                for e in desen.finditer(satir):
                    deger = e.group(e.lastindex) if e.lastindex else e.group(0)
                    if _ZARARSIZ.match(deger):
                        continue
                    bulgular.append((no, f"gizli bilgi: {ad}", maskele(deger)))
            gorulen = set()
            if self._kesin:
                for e in self._kesin.finditer(satir):
                    bulgular.append((no, self.h.kesin[e.group(1)], maskele(e.group(1))))
                    gorulen.add(e.start(1))
            if self._portfoy:
                for e in SAYI.finditer(satir):
                    if e.start() in gorulen or _tarih_parcasi(satir, e.start(), e.end()):
                        continue
                    for deger in sayi_yorumlari(e.group(0)):
                        kategori = self._portfoyde(deger)
                        if kategori:
                            bulgular.append((no, kategori, maskele(e.group(0))))
                            break
        return bulgular


def _git(kok: Path, *args: str, girdi: bytes | None = None) -> bytes:
    sonuc = subprocess.run(["git", "-C", str(kok), *args], input=girdi,
                           capture_output=True, check=False)
    if sonuc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: "
                           + sonuc.stderr.decode("utf-8", "replace").strip())
    return sonuc.stdout


def _metne(veri: bytes) -> str | None:
    """İkili dosyaysa None."""
    # Windows PowerShell metni UTF-16 ile yazabilir. NUL baytlarını ikili dosya
    # sanmadan önce BOM'lu Unicode metinleri çöz (UTF-32 önce: BOM'lar örtüşür).
    for bom, kodlama in ((b"\xff\xfe\x00\x00", "utf-32"), (b"\x00\x00\xfe\xff", "utf-32"),
                         (b"\xff\xfe", "utf-16"), (b"\xfe\xff", "utf-16")):
        if veri.startswith(bom):
            return veri.decode(kodlama, errors="replace")
    if b"\0" in veri[:8000]:
        return None
    return veri.decode("utf-8", errors="replace")


def _ilk_satir(metin: str | None) -> str | None:
    return metin.split("\n", 1)[0] if metin is not None else None


def dosya_tara(t: Tarayici, onek: str, yol: str, veri: bytes) -> list[Bulgu]:
    metin = _metne(veri)
    bulgular = [Bulgu(f"{onek}{yol}", k) for k in t.yol(yol, _ilk_satir(metin))]
    if metin is not None:
        bulgular += [Bulgu(f"{onek}{yol}:{no}", k, m) for no, k, m in t.metin(metin)]
    return bulgular


def agaci_tara(kok: Path, t: Tarayici) -> list[Bulgu]:
    bulgular = []
    for yol in _git(kok, "ls-files", "-z").decode("utf-8").split("\0"):
        if not yol:
            continue
        dosya = kok / yol
        if not dosya.is_file():
            continue
        bulgular += dosya_tara(t, "", yol, dosya.read_bytes())
    return bulgular


def commitleri_tara(kok: Path, t: Tarayici, shalar: list[str]) -> list[Bulgu]:
    bulgular = []
    for sha in shalar:
        kisa = sha[:7]
        mesaj = _git(kok, "log", "-1", "--format=%B", sha).decode("utf-8", "replace")
        bulgular += [Bulgu(f"{kisa} (commit mesajı):{no}", k, m) for no, k, m in t.metin(mesaj)]
        cikti = _git(kok, "diff-tree", "-r", "--root", "-m", "--no-commit-id", "-z",
                     "--name-only", "--diff-filter=ACMRT", sha).decode("utf-8")
        for yol in dict.fromkeys(x for x in cikti.split("\0") if x):
            try:
                veri = _git(kok, "show", f"{sha}:{yol}")
            except RuntimeError:
                continue
            bulgular += dosya_tara(t, f"{kisa} ", yol, veri)
    return bulgular


def rev_list(kok: Path, *args: str) -> list[str]:
    return _git(kok, "rev-list", *args).decode().split()


def pre_push_shalari(kok: Path, girdi: str) -> list[str]:
    """pre-push stdin satırlarından taranacak commit listesini çıkarır."""
    shalar: list[str] = []
    for satir in girdi.splitlines():
        parca = satir.split()
        if len(parca) != 4:
            continue
        _yerel_ref, yerel_sha, _uzak_ref, uzak_sha = parca
        if set(yerel_sha) == {"0"}:
            continue  # dal silme
        if set(uzak_sha) == {"0"}:
            yeni = rev_list(kok, yerel_sha, "--not", "--remotes")
        else:
            try:
                yeni = rev_list(kok, f"{uzak_sha}..{yerel_sha}")
            except RuntimeError:
                yeni = rev_list(kok, yerel_sha, "--not", "--remotes")
        shalar += [s for s in yeni if s not in shalar]
    return shalar


def calistir(argv: list[str], kok: Path | None = None, stdin: str | None = None,
             cikis=None) -> int:
    cikis = cikis or sys.stdout
    p = argparse.ArgumentParser(description="Yayın öncesi gizlilik kontrolü")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--agac", action="store_true", help="izlenen dosyaları tara")
    g.add_argument("--commitler", metavar="ARALIK", help="commit aralığını tara (ör. HEAD)")
    g.add_argument("--pre-push", action="store_true", help="git pre-push kancası kipi")
    a, _fazla = p.parse_known_args(argv)  # kanca uzak adı/URL'si gönderir; yok sayılır

    if kok is None:
        kok = Path(_git(Path.cwd(), "rev-parse", "--show-toplevel").decode().strip())
    hassas = hassas_degerleri_hesapla(kok)
    if hassas.not_:
        print(hassas.not_, file=cikis)
    t = Tarayici(hassas)

    if a.agac:
        bulgular = agaci_tara(kok, t)
        kapsam = "izlenen dosyalar"
    elif a.commitler:
        shalar = rev_list(kok, a.commitler)
        bulgular = commitleri_tara(kok, t, shalar)
        kapsam = f"{len(shalar)} commit"
    else:
        girdi = stdin if stdin is not None else sys.stdin.read()
        shalar = pre_push_shalari(kok, girdi)
        bulgular = commitleri_tara(kok, t, shalar)
        kapsam = f"gönderilecek {len(shalar)} commit"

    if not bulgular:
        print(f"Yayın kontrolü temiz ({kapsam}).", file=cikis)
        return 0
    print(f"ENGELLENDİ: {kapsam} içinde {len(bulgular)} hassas bulgu var.", file=cikis)
    for b in bulgular:
        print("  " + b.metin(), file=cikis)
    print("Bu değerleri çıkarmadan herkese açık depoya gönderme.", file=cikis)
    return 1


def main() -> int:
    for akis in (sys.stdout, sys.stderr):
        try:
            akis.reconfigure(encoding="utf-8")
        except AttributeError:
            pass
    try:
        return calistir(sys.argv[1:])
    except RuntimeError as hata:
        print(f"Yayın kontrolü çalışamadı: {hata}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
