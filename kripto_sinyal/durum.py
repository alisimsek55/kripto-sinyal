"""Kullanıcının gerçek işlemlerini durum.json'a yazar/okur.

tavsiye komutu, kısa vadeli geri alım seviyesini kullanıcının GERÇEK son satışına
göre hesaplar. Kayıt yoksa "şu seviyeden satarsan..." diye varsayımsal söyler.
"""

import json
import math
from datetime import date, datetime, timezone
from pathlib import Path


def oku(yol: Path) -> dict:
    if not yol.exists():
        return {"islemler": []}
    return json.loads(yol.read_text(encoding="utf-8"))


def ekle(yol: Path, tur: str, coin: str, fiyat: float, yuzde: float | None,
         miktar: float | None, kural: str, tarih: str | None = None) -> dict:
    if tur not in ("al", "sat"):
        raise ValueError("işlem türü 'al' ya da 'sat' olmalı")
    if not math.isfinite(fiyat) or fiyat <= 0:
        raise ValueError("fiyat sonlu ve sıfırdan büyük olmalı")
    if (yuzde is None) == (miktar is None):
        raise ValueError("--yuzde ya da --miktar'dan birini (yalnız birini) ver")
    if yuzde is not None and (not math.isfinite(yuzde) or not 0 < yuzde <= 100):
        raise ValueError("yüzde sonlu, sıfırdan büyük ve en fazla 100 olmalı")
    if miktar is not None and (not math.isfinite(miktar) or miktar <= 0):
        raise ValueError("miktar sonlu ve sıfırdan büyük olmalı")
    if tarih is not None:
        try:
            if date.fromisoformat(tarih).isoformat() != tarih:
                raise ValueError
        except ValueError:
            raise ValueError("tarih YYYY-AA-GG biçiminde geçerli bir gün olmalı") from None
    kayit = {
        "tarih": tarih or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "tur": tur, "coin": coin.upper(), "fiyat": fiyat,
        "yuzde": yuzde, "miktar": miktar, "kural": kural,
    }
    veri = oku(yol)
    veri["islemler"].append(kayit)
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(json.dumps(veri, ensure_ascii=False, indent=2), encoding="utf-8")
    return kayit


def kisa_referans(veri: dict, coin: str) -> dict:
    """Kısa vade için motorla aynı mantık:
    satış -> merdiven ve geri alım referansı = satış fiyatı;
    alım  -> geri alım referansı = alım fiyatı, merdiven sıfırlanır."""
    ref = {"satis_ref": None, "alim_ref": None, "son_satis_tarih": None, "son_islem": None}
    islemler = [i for i in veri.get("islemler", [])
                if i["coin"] == coin.upper() and i.get("kural", "kisa") == "kisa"]
    for i in sorted(islemler, key=lambda i: i["tarih"]):
        if i["tur"] == "sat":
            ref.update(satis_ref=i["fiyat"], alim_ref=i["fiyat"], son_satis_tarih=i["tarih"])
        else:
            ref.update(satis_ref=None, alim_ref=i["fiyat"])
        ref["son_islem"] = i
    return ref
