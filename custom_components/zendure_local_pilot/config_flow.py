"""Formulaire de configuration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_EM_CANAL,
    CONF_MAJ_AUTO,
    CONF_MIGRER,
    CONF_NB_PACKS,
    CONF_SHELLY_HOST,
    DEFAUT_NB_PACKS,
    DOMAIN,
)
from .shelly import ClientShelly, ErreurShelly

_LOGGER = logging.getLogger(__name__)


async def _verifier(hass, hote: str) -> dict[str, Any]:
    """Vérifie qu'on parle bien au Shelly porteur de la régulation."""
    client = ClientShelly(async_get_clientsession(hass), hote)
    infos = await client.infos()
    script = await client.trouver_script()
    kvs = await client.kvs_lire_tout()
    return {
        "id_appareil": (infos or {}).get("id", ""),
        "modele": (infos or {}).get("model", ""),
        "script": script,
        "kvs": kvs,
    }


class FluxConfiguration(ConfigFlow, domain=DOMAIN):
    """Ajout d'une installation."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        erreurs: dict[str, str] = {}

        if user_input is not None:
            hote = user_input[CONF_SHELLY_HOST].strip()
            try:
                sonde = await _verifier(self.hass, hote)
            except ErreurShelly as err:
                _LOGGER.debug("validation du Shelly %s : %s", hote, err)
                erreurs["base"] = "injoignable"
            else:
                if not sonde["id_appareil"]:
                    erreurs["base"] = "pas_un_shelly"
                elif sonde["script"] is None:
                    # Sans le script, il n'y a tout simplement pas de
                    # régulation : mieux vaut le dire tout de suite que de
                    # laisser l'utilisateur découvrir un tableau de bord vide.
                    erreurs["base"] = "script_absent"
                else:
                    await self.async_set_unique_id(sonde["id_appareil"])
                    self._abort_if_unique_id_configured()
                    # Le canal n'est pas demandé : le script crée toujours la
                    # clé zendure_em, et c'est elle qui fait foi. Le demander ici
                    # risquerait d'écraser le réglage d'un utilisateur venu du
                    # YAML. Il se change ensuite par l'entité « Pince réseau lue ».
                    canal = sonde["kvs"].get("zendure_em", 0)
                    return self.async_create_entry(
                        title=f"Zendure ({hote})",
                        data={
                            CONF_SHELLY_HOST: hote,
                            CONF_EM_CANAL: int(canal or 0),
                            CONF_NB_PACKS: user_input[CONF_NB_PACKS],
                            CONF_MIGRER: user_input[CONF_MIGRER],
                        },
                    )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SHELLY_HOST,
                    default=(user_input or {}).get(CONF_SHELLY_HOST, ""),
                ): str,
                vol.Required(CONF_NB_PACKS, default=DEFAUT_NB_PACKS): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=4)
                ),
                vol.Required(CONF_MIGRER, default=True): bool,
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=erreurs
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return FluxOptions()


class FluxOptions(OptionsFlow):
    """Modification des réglages après coup."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        actuel = {**self.config_entry.data, **self.config_entry.options}
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SHELLY_HOST, default=actuel.get(CONF_SHELLY_HOST, "")
                ): str,
                vol.Required(
                    CONF_NB_PACKS, default=actuel.get(CONF_NB_PACKS, DEFAUT_NB_PACKS)
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=4)),
                vol.Required(
                    CONF_MAJ_AUTO, default=actuel.get(CONF_MAJ_AUTO, True)
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
