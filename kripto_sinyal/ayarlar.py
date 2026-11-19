"""Ayar dosyasını (ayarlar.json) okur. Dosya yoksa varsayılanlar kullanılır."""

import json
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent

VARSAYILAN = {
    "aylik_tutar": 100.0,      # her ay alınan tutar (USDT)
    "komisyon": 0.001,         # %0.1
    "kayma": 0.0005,           # %0.05 fiyat kayması
    "coinler": {"DOGE": "DOGEUSDT", "BTC": "BTCUSDT"},
    "ana_coin": "DOGE",        # kısa tavsiye görünümünün coini
    "gecmis_klasoru": "gecmis",  # Binance işlem geçmişi dışa aktarımı
    "sonuc_dosyasi": "sonuc/parametreler.json",
    "durum_dosyasi": "durum.json",
    "veri_klasoru": "veri",
}


def ayarlari_oku(yol: Path | None = None) -> dict:
    """Varsayılanların üstüne ayarlar.json'daki değerleri yazar."""
    yol = yol or KOK / "ayarlar.json"
    ayar = dict(VARSAYILAN)
    if yol.exists():
        ayar.update(json.loads(yol.read_text(encoding="utf-8")))
    return ayar


def yol(ayar: dict, anahtar: str) -> Path:
    """Ayardaki göreli yolu proje köküne göre tam yola çevirir."""
    return KOK / ayar[anahtar]
