"""Socle commun des entités de l'intégration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .calculs import nom_modele
from .const import DOMAIN, PREFIXE
from .coordinator import CoordinateurZendure


class EntiteZendure(CoordinatorEntity[CoordinateurZendure]):
    """Entité rattachée à la batterie.

    Deux choses se jouent ici et méritent d'être explicites :

    1. L'entity_id est IMPOSÉ, et non déduit du nom. Home Assistant le
       déduirait sinon du nom affiché, lequel contient le modèle : deux
       utilisateurs aux modèles différents obtiendraient des identifiants
       différents, et le dashboard, qui les référence en dur, n'afficherait
       rien. C'est aussi ce qui permet aux installations venues de la version
       YAML de conserver leur historique.

    2. Le nom affiché, lui, est composé par Home Assistant à partir du nom de
       l'appareil (« Zendure SolarFlow 2400 AC+ ») et du nom de l'entité
       (« SOC »). Il suit donc le modèle réel, sans réglage.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinateur: CoordinateurZendure, suffixe: str,
                 domaine: str = "sensor") -> None:
        super().__init__(coordinateur)
        self._suffixe = suffixe
        self._attr_unique_id = f"{PREFIXE}_{suffixe}"
        self.entity_id = f"{domaine}.{PREFIXE}_{suffixe}"

    @property
    def device_info(self) -> DeviceInfo:
        donnees = self.coordinator.data
        sn = donnees.sn if donnees else ""
        modele = nom_modele(donnees.produit if donnees else None)
        return DeviceInfo(
            identifiers={(DOMAIN, sn or self.coordinator.entree.entry_id)},
            manufacturer="Zendure",
            model=modele,
            name=f"Zendure {modele}",
            serial_number=sn or None,
            configuration_url=f"http://{self.coordinator.shelly.hote}",
        )

    @property
    def available(self) -> bool:
        """Disponible tant que la batterie répond.

        Le coordinateur distingue volontairement une batterie muette d'un
        Shelly muet : seules les entités issues de la batterie disparaissent
        dans le premier cas, celles du Shelly restent lisibles.
        """
        return (
            super().available
            and self.coordinator.data is not None
            and self.coordinator.data.batterie_joignable
        )


class EntiteShelly(EntiteZendure):
    """Entité issue du Shelly, qui survit à une batterie injoignable."""

    @property
    def available(self) -> bool:
        return super(EntiteZendure, self).available
