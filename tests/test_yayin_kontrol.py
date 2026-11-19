"""Yayın öncesi gizlilik kontrolünün testleri.

Yalnız geçici git depoları ve uydurma sayılar kullanılır. Örnek gizli bilgiler ve
CSV başlığı parça parça kurulur ki bu dosyanın kendisi taramaya takılmasın.
"""

import io
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "araclar"))
import kancayi_kur  # noqa: E402
import yayin_kontrol as yk  # noqa: E402

BASLIK = ",".join(f'"{a}"' for a in ["Date(UTC)", "Pair", "Side", "Price", "Executed",
                                      "Amount", "Fee", "order" + "No",
                                      "aorConvertPair", "aorConvertRate"])
# Uydurma işlemler: 52345.6 DOGE alınır, 12222.2 DOGE satılır.
# Elde 40123.4 DOGE; giren 5234.56; cep 1833.33; son kapanış 0.2 -> ~8024.68 USDT.
EMIR = "9876543210"
SATIRLAR = [
    f'"2025-01-02 10:00:00","DOGEUSDT","BUY","0.1","52345.6DOGE","5234.56USDT","0USDT","{EMIR}","",""',
    '"2025-02-03 10:00:00","DOGEUSDT","SELL","0.15","12222.2DOGE","1833.33USDT","0USDT","1122334455","",""',
]
KUR = 40.0  # uydurma -> portföy ~320987 TL


def _git(kok, *args):
    return subprocess.run(["git", "-C", str(kok), "-c", "user.name=t", "-c", "user.email=t@t",
                           *args], capture_output=True, text=True, check=True).stdout


def _yaz(kok, yol, metin):
    dosya = kok / yol
    dosya.parent.mkdir(parents=True, exist_ok=True)
    dosya.write_text(metin, encoding="utf-8")


@pytest.fixture
def depo(tmp_path):
    kok = tmp_path / "depo"
    kok.mkdir()
    _git(kok, "init", "-q", "-b", "main")
    _yaz(kok, ".gitignore", "/gecmis/\nveri/*.csv\nveri/kur.json\n")
    _yaz(kok, "gecmis/islem.csv", BASLIK + "\n" + "\n".join(SATIRLAR) + "\n")
    gunler = "\n".join(f"2025-{1 + i // 28:02d}-{1 + i % 28:02d},0.2,0.2,0.2,0.2,1" for i in range(130))
    _yaz(kok, "veri/DOGEUSDT_1d.csv", "tarih,acilis,yuksek,dusuk,kapanis,hacim\n" + gunler + "\n")
    _yaz(kok, "veri/kur.json", f'{{"kur": {KUR}}}')
    _yaz(kok, "README.md", "Merhaba. Sürüm 12, oran 3.5, tarih 2025-01-02.\n")
    _git(kok, "add", "-A")
    _git(kok, "commit", "-q", "-m", "ilk")
    return kok


def _calistir(kok, *argv, stdin=None):
    cikis = io.StringIO()
    kod = yk.calistir(list(argv), kok=kok, stdin=stdin, cikis=cikis)
    return kod, cikis.getvalue()


def _ekle(kok, yol, metin, mesaj="ekle", zorla=False):
    _yaz(kok, yol, metin)
    _git(kok, "add", *(["-f"] if zorla else []), yol)
    _git(kok, "commit", "-q", "-m", mesaj)


def test_temiz_depo_gecer(depo):
    kod, cikti = _calistir(depo, "--agac")
    assert kod == 0, cikti
    kod, cikti = _calistir(depo, "--commitler", "HEAD")
    assert kod == 0, cikti


@pytest.mark.parametrize("yol, icerik, kategori", [
    ("gecmis/islem.csv", BASLIK + "\n", "özel klasör gecmis/"),
    ("durum.json", "{}\n", "özel dosya"),
    ("veri/kur.json", "{}\n", "özel dosya"),
    ("takip/karne.json", "{}\n", "özel dosya"),
    (".env", "A=1\n", ".env dosyası"),
    ("anahtar/id_rsa", "x\n", "özel anahtar dosyası"),
    ("baska/disari.csv", BASLIK + "\n", "Binance işlem CSV'si"),
])
def test_yasak_yollar(depo, yol, icerik, kategori):
    _ekle(depo, yol, icerik, zorla=True)
    kod, cikti = _calistir(depo, "--agac")
    assert kod == 1 and kategori in cikti and yol in cikti


@pytest.mark.parametrize("metin, kategori, ham", [
    ("Elimde 40123 DOGE var", "elde tutulan coin", "40123"),
    ("Elimde 40.123 DOGE var", "elde tutulan coin", "40.123"),
    ("Elimde 40,123 DOGE var", "elde tutulan coin", "40,123"),
    ("Yatırdığım: 5234.56", "dışarıdan giren para", "5234.56"),
    ("Yatırdığım: 5.234,56", "dışarıdan giren para", "5.234,56"),
    ("Nakit 1,833.33 USDT", "cep (nakit)", "1,833.33"),
    ("Nakit 1833,33 USDT", "cep (nakit)", "1833,33"),
    ("aldım 52345.6 tane", "işlem miktarı", "52345.6"),
    ("ödedim 5234.56USDT", "dışarıdan giren para", "5234.56"),
    (f"emir {EMIR} tamam", "emir numarası", EMIR),
])
def test_bakiye_degerleri_maskeli_engellenir(depo, metin, kategori, ham):
    _ekle(depo, "notlar.txt", "giriş\n" + metin + "\n")
    kod, cikti = _calistir(depo, "--agac")
    assert kod == 1 and kategori in cikti and "notlar.txt:2" in cikti
    assert ham not in cikti and ham[:2] + "***" in cikti


def test_basa_bas_fiyati(depo):
    basa_bas = (5234.56 - 1833.33) / 40123.4
    for metin in (f"{basa_bas:.4f}", f"{basa_bas:.4f}".replace(".", ",")):
        _ekle(depo, "n.md", f"başa baş {metin}\n")
        kod, cikti = _calistir(depo, "--agac")
        assert kod == 1 and "başa baş fiyatı" in cikti and metin not in cikti


def test_binance_basligi_icerikte(depo):
    _ekle(depo, "kod.py", f"BASLIK = '{BASLIK}'\n")
    kod, cikti = _calistir(depo, "--agac")
    assert kod == 1 and "kod.py:1 [Binance CSV başlığı]" in cikti


@pytest.mark.parametrize("metin, birim", [
    ("Bakiyem 8.100 dolar", "USDT"),
    ("Bakiyem 8,050.5 dolar", "USDT"),
    ("Bakiyem 7950 dolar", "USDT"),
    ("Portföy 320.000 TL", "TL"),
    ("Portföy 322.500,75 TL", "TL"),
])
def test_portfoy_bandi_icinde_engellenir(depo, metin, birim):
    _ekle(depo, "n.md", metin + "\n")
    kod, cikti = _calistir(depo, "--agac")
    assert kod == 1 and f"portföy değeri ({birim})" in cikti
    sayi = metin.split()[1]
    assert sayi not in cikti


@pytest.mark.parametrize("metin", [
    "Bakiyem 8.300 dolar",       # +%3,4
    "Bakiyem 7.700 dolar",       # -%4
    "Portföy 340.000 TL",        # +%5,9
    "Fiyat 8.1",                 # 1000'den küçük
    "Tarih 2025-01-08 08:05",
])
def test_band_disi_engellenmez(depo, metin):
    _ekle(depo, "n.md", metin + "\n")
    kod, cikti = _calistir(depo, "--agac")
    assert kod == 0, cikti


@pytest.mark.parametrize("metin, kategori", [
    ("-" * 5 + "BEGIN RSA PRIVATE KEY" + "-" * 5, "özel anahtar bloğu"),
    ("api_" + "key = 'Q1w2E3r4T5y6U7i8'", "anahtar/şifre ataması"),
    ("BINANCE_SEC" + "RET=Zx9Yw8Vu7Ts6", "anahtar/şifre ataması"),
    ("Authori" + "zation: Bearer abcDEF123456789", "Bearer başlığı"),
    ("imza_" + "key: " + "ab12" * 10, "anahtar adlı uzun hex/base64"),
])
def test_gizli_anahtarlar(depo, metin, kategori):
    _ekle(depo, "ayar.txt", metin + "\n")
    kod, cikti = _calistir(depo, "--agac")
    assert kod == 1 and kategori in cikti


def test_zararsiz_atamalar_gecer(depo):
    _ekle(depo, "k.py", "api_" + "key = None\ntoken = os.environ['X']\n")
    kod, cikti = _calistir(depo, "--agac")
    assert kod == 0, cikti


def test_commit_gecmisi_ve_mesaji(depo):
    _ekle(depo, "n.md", "Bakiyem 8.100 dolar\n")
    _git(depo, "rm", "-q", "n.md")
    _git(depo, "commit", "-q", "-m", f"temizle; emir {EMIR}")
    kod, cikti = _calistir(depo, "--agac")
    assert kod == 0, cikti  # ağaç temiz, ama geçmişte kaldı
    kod, cikti = _calistir(depo, "--commitler", "HEAD")
    assert kod == 1
    assert "n.md:1 [portföy değeri (USDT)]" in cikti
    assert "(commit mesajı):1 [emir numarası" in cikti and EMIR not in cikti


def test_gecmis_csv_yoksa_bakiye_kontrolleri_atlanir(depo):
    (depo / "gecmis" / "islem.csv").unlink()
    _ekle(depo, "n.md", "Bakiyem 8.100 dolar\n")
    kod, cikti = _calistir(depo, "--agac")
    assert kod == 0 and "atlandı" in cikti
    _ekle(depo, "durum.json", "{}\n", zorla=True)
    assert _calistir(depo, "--agac")[0] == 1


def test_pre_push_yeni_dal_ve_silme(depo, tmp_path):
    uzak = tmp_path / "uzak.git"
    _git(tmp_path, "init", "-q", "--bare", str(uzak))
    _git(depo, "remote", "add", "origin", str(uzak))
    _git(depo, "push", "-q", "origin", "main")
    _git(depo, "checkout", "-q", "-b", "yeni")
    _ekle(depo, "n.md", "Portföy 320.000 TL\n")
    sha = _git(depo, "rev-parse", "HEAD").strip()
    sifir = "0" * 40

    assert yk.pre_push_shalari(depo, f"refs/heads/yeni {sha} refs/heads/yeni {sifir}\n") == [sha]
    girdi = (f"refs/heads/yeni {sha} refs/heads/yeni {sifir}\n"
             f"(delete) {sifir} refs/heads/eski {'1' * 40}\n")
    kod, cikti = _calistir(depo, "--pre-push", "origin", str(uzak), stdin=girdi)
    assert kod == 1 and "gönderilecek 1 commit" in cikti and "portföy değeri (TL)" in cikti

    # Yalnız silme: taranacak commit yok.
    kod, cikti = _calistir(depo, "--pre-push", stdin=f"(delete) {sifir} refs/heads/eski {'1' * 40}\n")
    assert kod == 0

    # Var olan dal: yalnız uzakta olmayan commitler taranır.
    ana = _git(depo, "rev-parse", "main").strip()
    kod, cikti = _calistir(depo, "--pre-push", stdin=f"refs/heads/main {ana} refs/heads/main {ana}\n")
    assert kod == 0, cikti


def test_sayi_yorumlari():
    assert 907015.0 in yk.sayi_yorumlari("907.015")
    assert 907.015 in yk.sayi_yorumlari("907.015")
    assert yk.sayi_yorumlari("1.234.567") == {1234567.0}
    assert yk.sayi_yorumlari("1,234.5") == {1234.5}
    assert yk.sayi_yorumlari("1.234,5") == {1234.5}


def test_kanca_kurulumu_tekrar_edilebilir(depo):
    hedef = depo / ".git" / "hooks" / "pre-push"
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text("#!/bin/sh\necho eski\n", encoding="utf-8")
    assert "saklandı" in kancayi_kur.kur(depo)
    assert (hedef.parent / "pre-push.yedek").read_text(encoding="utf-8").endswith("eski\n")
    assert "--pre-push" in hedef.read_text(encoding="utf-8")
    assert "zaten kurulu" in kancayi_kur.kur(depo)


@pytest.mark.parametrize("kodlama", ["utf-16", "utf-32"])
def test_windows_unicode_metinleri_taranir(kodlama):
    deger = "Q1w2E3r4T5y6U7i8"
    veri = ("api_" + "key = '" + deger + "'\n").encode(kodlama)
    bulgular = yk.dosya_tara(yk.Tarayici(yk.Hassas()), "", "not.txt", veri)
    assert any("gizli bilgi" in b.kategori for b in bulgular)
    assert all(deger not in b.metin() for b in bulgular)


@pytest.mark.parametrize("yol", ["GECMIS/islem.csv", "DURUM.JSON", "VERI/KUR.JSON", ".ENV"])
def test_windows_yasak_yollarda_buyuk_kucuk_harf(yol):
    assert yk.Tarayici(yk.Hassas()).yol(yol, None)


def test_var_olan_bozuk_gecmis_kontrolu_basarisiz_sayar(tmp_path):
    klasor = tmp_path / "gecmis"
    klasor.mkdir()
    (klasor / "islem.csv").write_text("yanlış başlık\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="defter hesaplanamadı"):
        yk.hassas_degerleri_hesapla(tmp_path)
