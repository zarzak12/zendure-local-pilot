"""Client de l'API locale zenSDK de la batterie Zendure."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aiohttp

from .const import DELAI_HTTP

_LOGGER = logging.getLogger(__name__)

# L'appareil rejette les corps de requête trop gros. L'implémentation de
# référence annonce 512 octets ; on garde une marge et on refuse plus tôt,
# pour échouer franchement plutôt que de laisser passer une écriture tronquée
# qui serait silencieusement ignorée par la batterie.
TAILLE_MAX_ECRITURE = 480


class ErreurZendure(Exception):
    """La batterie est injoignable ou répond quelque chose d'inattendu."""


class ClientZendure:
    """Lit et écrit les propriétés de la batterie en HTTP local."""

    def __init__(self, session: aiohttp.ClientSession, hote: str) -> None:
        self._session = session
        self._hote = hote

    @property
    def hote(self) -> str:
        return self._hote

    @hote.setter
    def hote(self, valeur: str) -> None:
        self._hote = valeur

    async def rapport(self) -> dict[str, Any]:
        """Retourne le rapport complet : sn, product, properties, packData."""
        if not self._hote:
            raise ErreurZendure("adresse de la batterie inconnue")
        url = f"http://{self._hote}/properties/report"
        try:
            async with self._session.get(
                url, timeout=aiohttp.ClientTimeout(total=DELAI_HTTP)
            ) as rep:
                rep.raise_for_status()
                # La batterie n'annonce pas toujours application/json :
                # on force l'interprétation plutôt que de la croire sur parole.
                donnees = json.loads(await rep.text())
        except asyncio.TimeoutError as err:
            raise ErreurZendure(f"{self._hote} n'a pas répondu à temps") from err
        except (aiohttp.ClientError, json.JSONDecodeError) as err:
            raise ErreurZendure(f"lecture de {self._hote} impossible : {err}") from err

        if not isinstance(donnees, dict) or "properties" not in donnees:
            raise ErreurZendure("réponse inattendue : pas de bloc « properties »")
        return donnees

    async def ecrire(self, sn: str, proprietes: dict[str, Any]) -> None:
        """Écrit des propriétés. Le numéro de série est exigé par l'API."""
        if not self._hote:
            raise ErreurZendure("adresse de la batterie inconnue")
        if not sn:
            raise ErreurZendure("numéro de série inconnu, écriture refusée")

        corps = json.dumps({"sn": sn, "properties": proprietes},
                           separators=(",", ":"))
        if len(corps.encode()) > TAILLE_MAX_ECRITURE:
            raise ErreurZendure(
                f"écriture de {len(corps.encode())} octets : au-delà de ce que "
                f"l'appareil accepte ({TAILLE_MAX_ECRITURE}), découpe la demande"
            )

        url = f"http://{self._hote}/properties/write"
        try:
            async with self._session.post(
                url,
                data=corps,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=DELAI_HTTP),
            ) as rep:
                rep.raise_for_status()
        except asyncio.TimeoutError as err:
            raise ErreurZendure("la batterie n'a pas accusé réception") from err
        except aiohttp.ClientError as err:
            raise ErreurZendure(f"écriture refusée : {err}") from err
        _LOGGER.debug("écrit sur %s : %s", self._hote, proprietes)
