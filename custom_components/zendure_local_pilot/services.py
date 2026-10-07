"""Services : consigne de puissance, plafonds, bornes SOC, écriture brute.

Ces services remplacent les scripts de la version YAML. Ils gardent les mêmes
noms de champs, pour que les automatisations existantes se transposent sans
réécriture.
"""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .calculs import echelle_soc
from .const import DOMAIN, LIMITE_REPLI, VC_CHARGE_MAX, VC_DECHARGE_MAX
from .coordinator import CoordinateurZendure, Donnees

_LOGGER = logging.getLogger(__name__)

SERVICE_PUISSANCE = "set_power"
SERVICE_PLAFONDS = "set_limits"
SERVICE_SOC = "set_soc"
SERVICE_ECRIRE = "write_properties"
SERVICE_REDEPLOYER = "redeploy_script"
SERVICE_RESET_SANTE = "reset_health"

_BASE = {vol.Optional("entry_id"): cv.string}

SCHEMA_PUISSANCE = vol.Schema({
    **_BASE,
    vol.Required("power"): vol.Coerce(int),
})

SCHEMA_PLAFONDS = vol.Schema({
    **_BASE,
    vol.Optional("decharge_max"): vol.All(vol.Coerce(int), vol.Range(min=0, max=10000)),
    vol.Optional("charge_max"): vol.All(vol.Coerce(int), vol.Range(min=0, max=10000)),
})

SCHEMA_SOC = vol.Schema({
    **_BASE,
    vol.Required("min_soc"): vol.All(vol.Coerce(int), vol.Range(min=0, max=50)),
    vol.Required("max_soc"): vol.All(vol.Coerce(int), vol.Range(min=70, max=100)),
})

SCHEMA_ECRIRE = vol.Schema({
    **_BASE,
    vol.Required("properties"): dict,
})

SCHEMA_RESET_SANTE = vol.Schema({**_BASE})

SCHEMA_REDEPLOYER = vol.Schema({
    **_BASE,
    vol.Required("chemin"): cv.string,
})


def plafonds_utilisateur(donnees: Donnees | None) -> tuple[int, int]:
    """Plafonds de décharge et de charge réglés sur le Shelly, en W."""
    def lire(composant: str) -> int:
        try:
            v = int(float(donnees.vc(composant))) if donnees else LIMITE_REPLI
        except (TypeError, ValueError):
            return LIMITE_REPLI
        return max(0, min(v, LIMITE_REPLI))
    return lire(VC_DECHARGE_MAX), lire(VC_CHARGE_MAX)


def _coordinateur(hass: HomeAssistant, appel: ServiceCall) -> CoordinateurZendure:
    """Retrouve l'installation visée.

    Avec une seule installation, le champ entry_id est superflu ; avec
    plusieurs, le deviner mènerait à piloter la mauvaise batterie.
    """
    installations: dict[str, CoordinateurZendure] = hass.data.get(DOMAIN, {})
    if not installations:
        raise HomeAssistantError("Aucune batterie Zendure n'est configurée.")

    entry_id = appel.data.get("entry_id")
    if entry_id:
        if entry_id not in installations:
            raise HomeAssistantError(f"Installation inconnue : {entry_id}")
        return installations[entry_id]

    if len(installations) > 1:
        raise HomeAssistantError(
            "Plusieurs batteries sont configurées : précise entry_id."
        )
    return next(iter(installations.values()))


def enregistrer_services(hass: HomeAssistant) -> None:
    """Déclare les services, une seule fois pour toute l'intégration."""
    if hass.services.has_service(DOMAIN, SERVICE_PUISSANCE):
        return

    async def consigne_puissance(appel: ServiceCall) -> None:
        coord = _coordinateur(hass, appel)
        # Bornée par les curseurs « décharge max » / « charge max » du Shelly,
        # comme la régulation. Pas par inverseMaxPower / chargeMaxLimit : sur
        # certains firmwares, ils suivent la consigne en cours, et la
        # consigne ne pourrait alors plus jamais augmenter.
        maxi_decharge, maxi_charge = plafonds_utilisateur(coord.data)

        p = int(appel.data["power"])
        p = min(p, maxi_decharge)
        p = max(p, -maxi_charge)

        # smartMode 1 : écriture volatile. Une consigne de puissance change
        # souvent ; l'écrire en flash userait la mémoire de la batterie.
        if p > 0:
            props = {"smartMode": 1, "acMode": 2, "outputLimit": p, "inputLimit": 0}
        elif p < 0:
            props = {"smartMode": 1, "acMode": 1, "inputLimit": -p, "outputLimit": 0}
        else:
            props = {"smartMode": 1, "outputLimit": 0, "inputLimit": 0}
        await coord.ecrire_batterie(props)

    async def plafonds(appel: ServiceCall) -> None:
        coord = _coordinateur(hass, appel)
        props: dict[str, int] = {}
        if "decharge_max" in appel.data:
            props["inverseMaxPower"] = int(appel.data["decharge_max"])
        if "charge_max" in appel.data:
            props["chargeMaxLimit"] = int(appel.data["charge_max"])
        if not props:
            raise HomeAssistantError(
                "Indique au moins decharge_max ou charge_max."
            )
        await coord.ecrire_batterie_persistant(props)

    async def bornes_soc(appel: ServiceCall) -> None:
        coord = _coordinateur(hass, appel)
        mini = int(appel.data["min_soc"])
        maxi = int(appel.data["max_soc"])
        if maxi <= mini:
            raise HomeAssistantError(
                f"Le SOC maximum ({maxi} %) doit dépasser le minimum ({mini} %)."
            )
        ech = echelle_soc(coord.data.proprietes if coord.data else {})
        await coord.ecrire_batterie_persistant(
            {"minSoc": mini * ech, "socSet": maxi * ech})

    async def ecrire_brut(appel: ServiceCall) -> None:
        coord = _coordinateur(hass, appel)
        # Porte de sortie assumée : la documentation zenSDK évolue plus vite
        # que cette intégration. On n'interprète rien, on transmet.
        await coord.ecrire_batterie(dict(appel.data["properties"]))

    async def redeployer(appel: ServiceCall) -> None:
        coord = _coordinateur(hass, appel)
        if coord.id_script is None:
            raise HomeAssistantError(
                "Aucun script de régulation n'a été repéré sur le Shelly."
            )
        chemin = appel.data["chemin"]
        if not hass.config.is_allowed_path(chemin):
            raise HomeAssistantError(
                f"{chemin} n'est pas dans un dossier autorisé "
                "(voir allowlist_external_dirs)."
            )

        def lire() -> str:
            with open(chemin, encoding="utf-8") as fichier:
                return fichier.read()

        code = await hass.async_add_executor_job(lire)
        await coord.shelly.script_deployer(coord.id_script, code)
        await coord.async_request_refresh()

    hass.services.async_register(
        DOMAIN, SERVICE_PUISSANCE, consigne_puissance, schema=SCHEMA_PUISSANCE)
    hass.services.async_register(
        DOMAIN, SERVICE_PLAFONDS, plafonds, schema=SCHEMA_PLAFONDS)
    hass.services.async_register(
        DOMAIN, SERVICE_SOC, bornes_soc, schema=SCHEMA_SOC)
    hass.services.async_register(
        DOMAIN, SERVICE_ECRIRE, ecrire_brut, schema=SCHEMA_ECRIRE)
    async def reset_sante(appel: ServiceCall) -> None:
        # Efface les capacités mesurées et les repères : la mesure repart au
        # prochain cycle de 25 points de SOC.
        _coordinateur(hass, appel).reinitialiser_sante()

    hass.services.async_register(
        DOMAIN, SERVICE_REDEPLOYER, redeployer, schema=SCHEMA_REDEPLOYER)
    hass.services.async_register(
        DOMAIN, SERVICE_RESET_SANTE, reset_sante, schema=SCHEMA_RESET_SANTE)


def retirer_services(hass: HomeAssistant) -> None:
    """Retire les services quand plus aucune installation ne subsiste."""
    if hass.data.get(DOMAIN):
        return
    for service in (SERVICE_PUISSANCE, SERVICE_PLAFONDS, SERVICE_SOC,
                    SERVICE_ECRIRE, SERVICE_REDEPLOYER, SERVICE_RESET_SANTE):
        hass.services.async_remove(DOMAIN, service)
