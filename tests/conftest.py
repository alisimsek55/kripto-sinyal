"""Ortak test ayarı: testler ağa çıkmaz, kur önbelleği geçici klasöre yazılır."""

import pytest
import requests

from kripto_sinyal import kur


@pytest.fixture(autouse=True)
def _ag_yok(monkeypatch, tmp_path):
    def ag_kapali(*a, **k):
        raise requests.ConnectionError("testte ağ kapalı")

    monkeypatch.setattr(requests, "get", ag_kapali)
    monkeypatch.setattr(kur, "DOSYA", tmp_path / "kur_onbellek.json")
