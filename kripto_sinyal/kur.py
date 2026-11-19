"""USDT/TRY kuru (Binance, herkese açık fiyat). Hiçbir durumda hata fırlatmaz.

Başarılı olursa kur veri/kur.json dosyasına yazılır. Ağ yoksa son kayıtlı kur
"taze değil" diye döner; kayıt da yoksa None döner.
"""

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import requests

from .ayarlar import KOK

URL = "https://api.binance.com/api/v3/ticker/price"
BASLIK = {"User-Agent": "kripto-sinyal/0.1"}
ZAMAN_ASIMI = 10
DOSYA = KOK / "veri" / "kur.json"


def _gecerli(kur) -> float:
    kur = float(kur)
    if not math.isfinite(kur) or kur <= 0:
        raise ValueError("geçersiz kur")
    return kur


def kur_al(dosya: Path | None = None) -> tuple[float, str, bool] | None:
    """(kur, zaman_utc, taze) döner. Ağ yoksa kayıtlı kur (taze=False), o da yoksa None."""
    dosya = Path(dosya) if dosya is not None else DOSYA
    try:
        r = requests.get(URL, params={"symbol": "USDTTRY"}, headers=BASLIK, timeout=ZAMAN_ASIMI)
        r.raise_for_status()
        kur = _gecerli(r.json()["price"])
        zaman = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            dosya.parent.mkdir(parents=True, exist_ok=True)
            dosya.write_text(json.dumps({"kur": kur, "zaman_utc": zaman}), encoding="utf-8")
        except OSError:
            pass
        return kur, zaman, True
    except Exception:
        pass
    try:
        kayit = json.loads(dosya.read_text(encoding="utf-8"))
        return _gecerli(kayit["kur"]), str(kayit["zaman_utc"]), False
    except Exception:
        return None


def zaman_metni(zaman: str) -> str:
    """ISO zamanı '15.11.2026 20:30' biçimine çevirir (UTC)."""
    try:
        t = datetime.fromisoformat(zaman)
        if t.tzinfo is not None:
            t = t.astimezone(timezone.utc)
        return t.strftime("%d.%m.%Y %H:%M")
    except (TypeError, ValueError):
        return str(zaman)


def kur_satiri(sonuc: tuple[float, str, bool] | None) -> str | None:
    """'Kur: 1 USDT = 50.70 TL (Binance, 15.11.2026 20:30 UTC)'; kur yoksa None."""
    if sonuc is None:
        return None
    kur, zaman, taze = sonuc
    ek = "" if taze else "; kayıtlı kur, güncel değil"
    return f"Kur: 1 USDT = {kur:.2f} TL (Binance, {zaman_metni(zaman)} UTC{ek})"
