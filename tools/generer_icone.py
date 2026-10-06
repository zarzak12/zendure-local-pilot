"""Génère les ressources de marque exigées par HACS.

Pillow n'est pas nécessairement installé, et ajouter une dépendance pour
produire deux images serait disproportionné : l'encodeur PNG tient en
quelques lignes avec zlib. Le script est versionné pour que l'icône reste
reproductible plutôt que d'être un binaire tombé du ciel.

    python tools/generer_icone.py
"""

from __future__ import annotations

import math
import os
import struct
import zlib

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARQUE = os.path.join(RACINE, "custom_components", "zendure_local_pilot", "brand")

FOND_HAUT = (14, 32, 56)
FOND_BAS = (19, 94, 102)
VERT = (46, 204, 139)
ECLAIR = (255, 199, 44)
BLANC = (244, 248, 250)

SUPER = 3  # suréchantillonnage : les diagonales de l'éclair seraient sinon crénelées


def _distance_rect_arrondi(x: float, y: float, cx: float, cy: float,
                           demi_l: float, demi_h: float, rayon: float) -> float:
    """Distance signée à un rectangle arrondi : négative à l'intérieur."""
    dx = abs(x - cx) - (demi_l - rayon)
    dy = abs(y - cy) - (demi_h - rayon)
    dehors = math.hypot(max(dx, 0.0), max(dy, 0.0))
    dedans = min(max(dx, dy), 0.0)
    return dehors + dedans - rayon


def _dans_polygone(x: float, y: float, sommets: list[tuple[float, float]]) -> bool:
    dedans = False
    j = len(sommets) - 1
    for i, (xi, yi) in enumerate(sommets):
        xj, yj = sommets[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            dedans = not dedans
        j = i
    return dedans


def _melange(fond: tuple[int, int, int], dessus: tuple[int, int, int],
             alpha: float) -> tuple[int, int, int]:
    return tuple(int(round(f + (d - f) * alpha)) for f, d in zip(fond, dessus))


def _echantillon(x: float, y: float, taille: int) -> tuple[int, int, int, int]:
    """Couleur d'un point, en coordonnées image."""
    u, v = x / taille, y / taille

    # Fond : carré arrondi, dégradé vertical.
    d_fond = _distance_rect_arrondi(x, y, taille / 2, taille / 2,
                                    taille / 2, taille / 2, taille * 0.22)
    if d_fond > 0:
        return (0, 0, 0, 0)

    couleur = _melange(FOND_HAUT, FOND_BAS, v)

    # Corps de la batterie.
    cx, cy = taille * 0.5, taille * 0.56
    demi_l, demi_h = taille * 0.22, taille * 0.30
    rayon = taille * 0.06
    d_corps = _distance_rect_arrondi(x, y, cx, cy, demi_l, demi_h, rayon)
    # Borne supérieure.
    d_borne = _distance_rect_arrondi(x, y, cx, taille * 0.21,
                                     taille * 0.085, taille * 0.045,
                                     taille * 0.025)
    d_batterie = min(d_corps, d_borne)

    epaisseur = taille * 0.045
    if d_batterie < 0:
        couleur = _melange(couleur, VERT, 0.18)
    if -epaisseur < d_batterie < 0:
        couleur = BLANC

    # Éclair, en proportion du corps de la batterie.
    bolt = [
        (0.585, 0.335), (0.395, 0.585), (0.505, 0.585),
        (0.425, 0.790), (0.625, 0.520), (0.505, 0.520),
    ]
    if _dans_polygone(u, v, [(px, py) for px, py in bolt]):
        couleur = ECLAIR

    return (*couleur, 255)


def _rendre(taille: int) -> bytes:
    lignes = bytearray()
    for py in range(taille):
        lignes.append(0)  # filtre « None »
        for px in range(taille):
            r = v = b = a = 0
            for sy in range(SUPER):
                for sx in range(SUPER):
                    e = _echantillon(px + (sx + 0.5) / SUPER,
                                     py + (sy + 0.5) / SUPER, taille)
                    r += e[0] * e[3]
                    v += e[1] * e[3]
                    b += e[2] * e[3]
                    a += e[3]
            n = SUPER * SUPER
            if a == 0:
                lignes += bytes(4)
            else:
                lignes += bytes((r // a, v // a, b // a, a // n))
    return bytes(lignes)


def _png(taille: int, donnees: bytes) -> bytes:
    def morceau(nom: bytes, charge: bytes) -> bytes:
        return (struct.pack(">I", len(charge)) + nom + charge
                + struct.pack(">I", zlib.crc32(nom + charge) & 0xFFFFFFFF))

    entete = struct.pack(">IIBBBBB", taille, taille, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n"
            + morceau(b"IHDR", entete)
            + morceau(b"IDAT", zlib.compress(donnees, 9))
            + morceau(b"IEND", b""))


def main() -> None:
    os.makedirs(MARQUE, exist_ok=True)
    for nom, taille in (("icon.png", 256), ("logo.png", 256)):
        chemin = os.path.join(MARQUE, nom)
        with open(chemin, "wb") as fichier:
            fichier.write(_png(taille, _rendre(taille)))
        print(f"  écrit : {chemin} ({taille}x{taille})")


if __name__ == "__main__":
    main()
