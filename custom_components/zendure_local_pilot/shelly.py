"""Client RPC du Shelly Pro 3EM qui héberge la régulation."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from .const import DELAI_HTTP

_LOGGER = logging.getLogger(__name__)

# Le Shelly refuse les scripts trop gros en une seule requête : PutCode doit
# être découpé. 1 024 octets passe confortablement sur toutes les générations.
TAILLE_MORCEAU = 1024


class ErreurShelly(Exception):
    """Le Shelly est injoignable ou a refusé l'appel."""


def kvs_vers_dict(items: Any) -> dict[str, Any]:
    """Réponse de KVS.GetMany -> {clé: valeur}, quel que soit le firmware.

    Les firmwares 1.x renvoient un dictionnaire {clé: {"value": …}}, les 2.x
    une liste [{"key": …, "value": …}]. Le script JS gère les deux depuis
    toujours (kvsToMap) ; l'intégration doit en faire autant.
    """
    if isinstance(items, dict):
        return {cle: (d or {}).get("value") for cle, d in items.items()
                if isinstance(d, dict)}
    if isinstance(items, list):
        return {d["key"]: d.get("value") for d in items
                if isinstance(d, dict) and "key" in d}
    return {}


class ClientShelly:
    """Appels RPC du Shelly, en HTTP local."""

    def __init__(self, session: aiohttp.ClientSession, hote: str) -> None:
        self._session = session
        self._hote = hote
        self._id = 0

    @property
    def hote(self) -> str:
        return self._hote

    async def appel(self, methode: str, params: dict[str, Any] | None = None) -> Any:
        """Exécute une méthode RPC et retourne son résultat."""
        self._id += 1
        corps: dict[str, Any] = {"id": self._id, "method": methode}
        if params is not None:
            corps["params"] = params
        try:
            async with self._session.post(
                f"http://{self._hote}/rpc",
                json=corps,
                timeout=aiohttp.ClientTimeout(total=DELAI_HTTP),
            ) as rep:
                rep.raise_for_status()
                donnees = await rep.json(content_type=None)
        except asyncio.TimeoutError as err:
            raise ErreurShelly(f"{self._hote} n'a pas répondu à temps") from err
        except aiohttp.ClientError as err:
            raise ErreurShelly(f"{methode} a échoué : {err}") from err

        if isinstance(donnees, dict) and "error" in donnees:
            raise ErreurShelly(f"{methode} : {donnees['error']}")
        if not isinstance(donnees, dict):
            raise ErreurShelly(f"{methode} : réponse inattendue")
        return donnees.get("result")

    # -- informations générales -------------------------------------------

    async def infos(self) -> dict[str, Any]:
        return await self.appel("Shelly.GetDeviceInfo")

    async def etat_complet(self) -> dict[str, Any]:
        """État de tous les composants, composants virtuels compris.

        En firmware 2.x, Shelly.GetStatus ne renvoie PLUS les composants
        virtuels (mode, curseurs, veille) : ils ne sont lisibles que par
        Shelly.GetComponents. Constaté en réel sur un Pro 3EM en 2.0.1, où le
        mode et tous les curseurs restaient « inconnus ».
        """
        etat = await self.appel("Shelly.GetStatus") or {}
        try:
            etat.update(await self.composants_virtuels())
        except ErreurShelly as err:
            # Firmware 1.x ancien sans GetComponents : ils sont alors déjà
            # dans GetStatus, rien n'est perdu.
            _LOGGER.debug("composants virtuels via GetComponents indisponibles : %s", err)
        return etat

    async def composants_virtuels(self) -> dict[str, Any]:
        """{clé: statut} des composants dynamiques, toutes pages lues."""
        statuts: dict[str, Any] = {}
        offset = 0
        while True:
            res = await self.appel("Shelly.GetComponents", {
                "dynamic_only": True, "include": ["status"], "offset": offset})
            composants = (res or {}).get("components") or []
            for c in composants:
                if isinstance(c, dict) and "key" in c and isinstance(c.get("status"), dict):
                    statuts[c["key"]] = c["status"]
            offset += len(composants)
            total = (res or {}).get("total", 0)
            if not composants or offset >= total:
                return statuts

    # -- magasin clé/valeur (réglages avancés) -----------------------------

    async def kvs_lire_tout(self) -> dict[str, Any]:
        res = await self.appel("KVS.GetMany", {"match": "zendure_*"})
        return kvs_vers_dict((res or {}).get("items"))

    async def kvs_ecrire(self, cle: str, valeur: Any) -> None:
        await self.appel("KVS.Set", {"key": cle, "value": valeur})

    # -- composants virtuels ------------------------------------------------

    async def vc_ecrire(self, composant: str, valeur: Any) -> None:
        """Écrit dans un composant virtuel, p. ex. « number:200 »."""
        type_, _, ident = composant.partition(":")
        if not ident.isdigit():
            raise ErreurShelly(f"composant virtuel invalide : {composant}")
        methode = f"{type_.capitalize()}.Set"
        await self.appel(methode, {"id": int(ident), "value": valeur})

    # -- script de régulation ----------------------------------------------

    async def scripts(self) -> list[dict[str, Any]]:
        res = await self.appel("Script.List")
        return (res or {}).get("scripts", [])

    async def trouver_script(self, nom_partiel: str = "zendure") -> dict[str, Any] | None:
        for s in await self.scripts():
            if nom_partiel.lower() in str(s.get("name", "")).lower():
                return s
        return None

    async def script_demarrer(self, ident: int) -> None:
        await self.appel("Script.Start", {"id": ident})

    async def script_arreter(self, ident: int) -> None:
        await self.appel("Script.Stop", {"id": ident})

    async def script_deployer(self, ident: int, code: str) -> None:
        """Remplace le code du script, par morceaux.

        L'éditeur web du Shelly tronque silencieusement au-delà d'environ 7 ko,
        ce qui produit un script syntaxiquement valide mais amputé : la
        régulation semble alors tourner tout en ne faisant plus rien. On passe
        donc toujours par PutCode, puis on relit tout et on compare.

        Le découpage se fait en CARACTÈRES : couper en octets tranche les
        accents en deux, et leurs moitiés seraient perdues à l'écriture.

        Le premier morceau REMPLACE le code (append False), les suivants
        s'ajoutent. Pas de « vidage » préalable par un code vide : le firmware
        2.x le refuse (« Length should be greater than 0 »).
        """
        code = code.replace("\r\n", "\n")   # le Shelly stocke en LF
        if not code:
            raise ErreurShelly("script vide : rien à déployer")
        await self.appel("Script.Stop", {"id": ident})
        ecrit = False
        try:
            for debut in range(0, len(code), TAILLE_MORCEAU):
                await self.appel(
                    "Script.PutCode",
                    {"id": ident, "code": code[debut:debut + TAILLE_MORCEAU],
                     "append": debut > 0},
                )
                ecrit = True
        except ErreurShelly:
            if not ecrit:
                # Rien n'a été écrit : l'ancien code est intact, on le relance
                # plutôt que de laisser la régulation à l'arrêt.
                await self._relancer_sans_echec(ident)
            raise
        relu = await self.script_lire(ident)
        if relu != code:
            ecart = next((i for i, (a, b) in enumerate(zip(relu, code)) if a != b),
                         min(len(relu), len(code)))
            raise ErreurShelly(
                f"script mal écrit : {len(relu)} caractères relus sur {len(code)}, "
                f"premier écart au caractère {ecart}. Le script reste arrêté."
            )
        # « Run on startup » : sans lui, le script ne repartirait pas après une
        # coupure de courant du Shelly.
        await self.appel("Script.SetConfig", {"id": ident, "config": {"enable": True}})
        await self.appel("Script.Start", {"id": ident})
        _LOGGER.info("script %s redéployé (%d caractères)", ident, len(code))

    async def _relancer_sans_echec(self, ident: int) -> None:
        try:
            await self.appel("Script.Start", {"id": ident})
            _LOGGER.warning("déploiement interrompu avant écriture : ancien script relancé")
        except ErreurShelly as err:
            _LOGGER.error("ancien script NON relancé après l'échec du déploiement : %s", err)

    async def script_lire(self, ident: int) -> str:
        """Relit le code complet. GetCode pagine, en OCTETS."""
        texte, offset = "", 0
        while True:
            res = await self.appel(
                "Script.GetCode", {"id": ident, "offset": offset, "len": TAILLE_MORCEAU})
            morceau = (res or {}).get("data", "")
            # Une page peut s'arrêter au milieu d'un caractère multi-octets :
            # ses octets orphelins arrivent en U+FFFD. On les écarte, l'offset
            # reste sur ce caractère, relu entier à la page suivante.
            morceau = morceau.rstrip("�")
            if not morceau:
                return texte
            texte += morceau
            offset += len(morceau.encode())
            if (res or {}).get("left", 0) <= 0:
                return texte
