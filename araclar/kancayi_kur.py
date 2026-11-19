"""Yayın kontrolünü git pre-push kancası olarak kurar.

Kullanım: python araclar/kancayi_kur.py
Tekrar çalıştırmak güvenlidir: kanca zaten kuruluysa dokunmaz. Başka bir kanca
varsa onu pre-push.yedek adıyla saklar.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ISARET = "# yayin_kontrol kancası (araclar/kancayi_kur.py kurdu)"

KANCA = f"""#!/bin/sh
{ISARET}
# Gönderilecek commitlerde bakiye, işlem geçmişi ya da gizli anahtar varsa push'u durdurur.
kok="$(git rev-parse --show-toplevel)" || exit 1
cd "$kok" || exit 1
if [ -x ".venv/Scripts/python.exe" ]; then
    py=".venv/Scripts/python.exe"
elif [ -x ".venv/bin/python" ]; then
    py=".venv/bin/python"
else
    echo "Yayın kontrolü: .venv bulunamadı; push durduruldu." >&2
    exit 1
fi
exec "$py" araclar/yayin_kontrol.py --pre-push "$@"
"""


def kur(kok: Path) -> str:
    git_dizini = subprocess.run(["git", "-C", str(kok), "rev-parse", "--git-common-dir"],
                                capture_output=True, text=True, check=True).stdout.strip()
    kancalar = (kok / git_dizini).resolve() / "hooks"
    kancalar.mkdir(parents=True, exist_ok=True)
    hedef = kancalar / "pre-push"
    if hedef.exists():
        eski = hedef.read_text(encoding="utf-8", errors="replace")
        if eski.replace("\r\n", "\n") == KANCA:
            return f"Kanca zaten kurulu: {hedef}"
        if ISARET not in eski:
            yedek = kancalar / "pre-push.yedek"
            yedek.write_text(eski, encoding="utf-8", newline="\n")
            mesaj_yedek = f" (eski kanca {yedek.name} olarak saklandı)"
        else:
            mesaj_yedek = " (eski sürüm güncellendi)"
    else:
        mesaj_yedek = ""
    hedef.write_text(KANCA, encoding="utf-8", newline="\n")
    hedef.chmod(0o755)
    return f"Kanca kuruldu: {hedef}{mesaj_yedek}"


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    print(kur(Path(__file__).resolve().parents[1]))
