"""Enregistre la version et l'empreinte du script de régulation.

    python tools/verrouiller_script.py

Le script du Shelly a sa propre version (SCRIPT_VERSION), indépendante de
celle de l'intégration : une release qui ne touche pas au script ne doit pas
le faire redéployer chez tout le monde.

Le verrou (scripts/zendure_solarflow_4000_mix_pro.version) associe cette
version à une empreinte du code. Les tests échouent si le code change sans que
le verrou soit mis à jour, et ce script refuse de le mettre à jour si le code a
changé sans que SCRIPT_VERSION ait été montée : un script modifié porte
toujours une nouvelle version, donc il est toujours proposé à la mise à jour.

Il recopie aussi le script dans l'intégration, qui l'embarque.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(RACINE, "scripts", "zendure_solarflow_4000_mix_pro.js")
VERROU = os.path.join(RACINE, "scripts", "zendure_solarflow_4000_mix_pro.version")
EMBARQUE = os.path.join(RACINE, "custom_components", "zendure_local_pilot", "script", "zendure.js")

MOTIF_VERSION = re.compile(r'^let\s+SCRIPT_VERSION\s*=\s*"([^"]+)";\s*$', re.M)


def version_et_empreinte(code: str) -> tuple[str, str]:
    """Version déclarée, et empreinte du code HORS ligne de version."""
    code = code.replace("\r\n", "\n")
    m = MOTIF_VERSION.search(code)
    if not m:
        raise SystemExit("SCRIPT_VERSION introuvable dans le script")
    sans_version = MOTIF_VERSION.sub("", code)
    return m.group(1), hashlib.sha256(sans_version.encode("utf-8")).hexdigest()


def lire_verrou() -> tuple[str, str] | None:
    if not os.path.exists(VERROU):
        return None
    with open(VERROU, encoding="utf-8") as f:
        version, empreinte = f.read().split()
    return version, empreinte


def main() -> None:
    with open(SCRIPT, encoding="utf-8") as f:
        version, empreinte = version_et_empreinte(f.read())
    ancien = lire_verrou()
    if ancien and ancien[1] != empreinte and ancien[0] == version:
        raise SystemExit(
            f"le code du script a changé mais SCRIPT_VERSION est toujours {version} : "
            "monte-la, sinon les installations existantes ne seront pas mises à jour")
    with open(VERROU, "w", encoding="utf-8", newline="\n") as f:
        f.write(f"{version} {empreinte}\n")
    shutil.copyfile(SCRIPT, EMBARQUE)
    print(f"verrou : script {version}, empreinte {empreinte[:12]}… ; copie embarquée à jour")


if __name__ == "__main__":
    sys.exit(main())
