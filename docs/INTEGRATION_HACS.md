# Intégration HACS — Zendure Local Pilot

> **État : bêta.** Cette intégration remplace les packages YAML par une
> installation en deux clics. Elle n'a pas encore été éprouvée sur une
> installation en production : si tu tiens à la stabilité, reste sur les
> packages YAML, qui restent pleinement pris en charge.

## Pourquoi une intégration ?

Les packages YAML fonctionnent, mais ils demandent de copier des fichiers à la
main, de redémarrer Home Assistant, puis de personnaliser le tableau de bord
parce que les entités du Shelly portent un identifiant propre à chaque
appareil (`shellypro3em_a1b2c3…`).

L'intégration supprime ces trois corvées :

- installation et mise à jour par HACS ;
- configuration par formulaire, sans toucher à `configuration.yaml` ;
- **identifiants d'entités stables**, identiques chez tout le monde, donc un
  tableau de bord qui se colle tel quel. Le script `personnaliser.ps1`
  devient inutile.

Ce qui **ne change pas** : la régulation continue de tourner **dans le
Shelly**. L'intégration ne régule pas. Si Home Assistant s'arrête, ou si tu
désinstalles l'intégration, l'autoconsommation continue.

## Installation

### Par HACS (recommandé)

1. HACS → menu ⋮ → **Dépôts personnalisés**.
2. URL : `https://github.com/zarzak12/zendure-local-pilot`, catégorie
   **Intégration**.
3. Cherche **Zendure Local Pilot**, puis **Télécharger**.
4. Redémarre Home Assistant.
5. **Paramètres → Appareils et services → Ajouter une intégration** →
   *Zendure Local Pilot*.

### À la main

Copie `custom_components/zendure_local_pilot/` dans le dossier
`custom_components/` de ta configuration, puis redémarre.

### Prérequis

Home Assistant **2024.11 ou plus récent**.

Le script de régulation doit **déjà tourner sur le Shelly**. L'intégration le
vérifie et refuse la configuration s'il est absent : sans lui, il n'y aurait
rien à superviser et aucune batterie à découvrir. Voir le [README](../README.md)
pour le déploiement du script.

### Tableau de bord

1. Installe **`apexcharts-card`** par HACS (onglet Frontend), puis vide le
   cache du navigateur (Ctrl+F5).
2. Tableau de bord → ✏️ **Modifier** → ⋮ → **Modifier en YAML**.
3. Colle le contenu de **`dashboard/dashboard_integration.yaml`**, sans rien
   modifier.

Ce fichier est **généré** à partir du tableau de bord de la version YAML par
`tools/generer_dashboard_integration.py` : les deux restent identiques, aux
identifiants près. Ne le modifie pas à la main, modifie la source puis relance
le générateur (les tests vérifient qu'il est à jour et qu'il ne cite que des
entités existantes).

## Formulaire de configuration

| Champ | Rôle |
|---|---|
| Adresse IP du Shelly | C'est le seul point d'entrée. L'adresse de la batterie est découverte via le script. Modifiable ensuite dans les options. |
| Nombre de packs | Détermine combien de jeux d'entités de pack sont créés. Les packs absents restent indisponibles. |
| Reprendre les entités de la version YAML | À cocher si tu viens des packages. Voir ci-dessous. |

Le **canal de la pince** n'est pas demandé : l'intégration reprend celui que
le script utilise déjà (clé `zendure_em`). Pour le changer, utilise l'entité
`select.zendure_solarflow4000mix_canal_em` (« Pince réseau lue »).

## Migration depuis les packages YAML

> **À lire avant de cliquer.** L'ordre des opérations décide de la
> conservation de ton historique.

Un identifiant d'entité ne peut appartenir qu'à une seule intégration à la
fois. Tant que les packages YAML sont chargés, c'est l'intégration `template`
qui détient `sensor.zendure_solarflow4000mix_soc`. Si l'intégration démarre
dans ces conditions, Home Assistant lui attribue
`sensor.zendure_solarflow4000mix_soc_2`, et ton historique reste accroché à
l'ancienne entité, qui ne se met plus à jour.

**La bonne marche à suivre :**

1. **Retire d'abord les packages**, c'est-à-dire les fichiers
   `packages/zendure_solarflow4000mix*.yaml` de ta configuration.
2. Redémarre Home Assistant.
3. Ajoute l'intégration, **case de migration cochée**.

L'intégration libère alors les anciennes entrées de registre **des seules
entités qu'elle reprend**, une seule fois, puis reprend les mêmes
identifiants. **L'historique et les statistiques long terme sont rangés
par identifiant d'entité : ils survivent.** Tes graphiques et ton tableau de
bord continuent comme si de rien n'était.

Si l'ordre n'a pas été respecté, une alerte de réparation apparaît dans
**Paramètres → Système → Réparations** et indique combien d'entités ont dû se
rabattre sur un suffixe `_2`. Corrige alors l'étape 1, puis recharge
l'intégration.

### Ce qui est perdu, et pourquoi

Les réglages étaient des `input_number`, `input_boolean` et `input_text` ;
ils deviennent des `number`, `switch` et `select`. **Le domaine change, donc
l'identifiant change** : `input_number.zendure_solarflow4000mix_soc_min_consigne`
devient `number.zendure_solarflow4000mix_soc_min_consigne`. Leur historique
n'est pas récupérable — c'est l'historique d'un curseur de réglage, sans grand
intérêt, mais autant le dire franchement.

En revanche, **toutes les mesures** de la version YAML (SOC, puissances,
températures, réseau, énergies, rendements, santé des packs, statistiques du
jour…) conservent leur identifiant et leur historique.

**Les compteurs reprennent là où ils en étaient.** À la première
installation, l'intégration lit la dernière valeur des compteurs d'énergie,
des capacités mesurées des packs (et de leurs repères), des rendements et de
la date de calibration, dans l'état courant ou à défaut dans l'historique.
Sans cela, un compteur d'énergie repartirait de zéro et le tableau Énergie
verrait une chute de plusieurs centaines de kWh. La santé des packs n'a pas
non plus à être réapprise. Les valeurs reprises sont listées dans le journal.

Seule exception : les compteurs **du jour** (PV du jour, commutations, temps
en zéro soutirage) repartent de zéro le jour de la migration.

Pense à mettre à jour tes automatisations qui référençaient ces aides, et à
remplacer les appels `script.zendure_solarflow4000mix_set_power` par le
service `zendure_local_pilot.set_power`.

## Ce que l'intégration expose

### Mesures

Toutes celles de la version YAML : SOC, puissance au point de livraison (lue
sur la pince que suit la régulation), puissances d'entrée et de sortie,
répartition du PV, puissance et état de la batterie, côté DC des packs,
tensions, températures, butée SOC, détail par pack, énergies disponible et
requise, temps de charge restant.

S'y ajoutent les grandeurs **à mémoire**, conservées d'un redémarrage à
l'autre :

| Famille | Entités |
|---|---|
| Énergie | `energie_chargee`, `energie_dechargee`, `energie_pv`, `pv_jour`, `pack_N_energie_dc` |
| Rendements | `rendement_global`, `rendement_charge`, `rendement_decharge`, `efficacite_*` (instantané et moyenne 7 jours) |
| Santé des packs | `pack_N_capacite_estimee`, `pack_N_sante`, `sante_min`, `mesure_sante_progression` |
| Statistiques du jour | `commutations_charge_jour`, `commutations_decharge_jour`, `commutations_jour`, `zero_soutirage_jour` |
| Calibration | `calibration`, `derniere_calibration`, `jours_depuis_calibration` |

La santé est estimée comme dans la version YAML : énergie DC échangée
rapportée à au moins 25 points de SOC, filtre de plausibilité (40 à 130 % du
nominal), lissage 70/30. Voir le [README](../README.md#état-de-santé-des-batteries).

Les entités portent le modèle réel dans leur **nom affiché** (« Zendure
SolarFlow 2400 AC+ SOC »), mais leur **identifiant reste
`zendure_solarflow4000mix_…`** quel que soit le modèle. Ce n'est pas une
étourderie : c'est ce qui permet à un même tableau de bord de fonctionner chez
tout le monde, et aux installations venues du YAML de garder leur historique.

### Réglages

| Domaine | Entités |
|---|---|
| `select` | Mode de régulation, injection PV, mode secours, pince lue |
| `number` | Bornes SOC, plafonds onduleur, marges de charge et de décharge, consigne manuelle, délai de veille, réglages fins |
| `switch` | Régulation (démarre ou arrête le script du Shelly) ; *Afficher l'aide* et *Afficher le PV* (préférences du tableau de bord) |
| `binary_sensor` | Script en marche, veille, erreur, liaison batterie, réseau connecté, zéro soutirage |

Les réglages fins de la régulation (gain, zone morte, hystérésis, délai et
seuil de bascule, lissage…) sont rangés dans la catégorie *Configuration* de
l'appareil et dans l'onglet Réglages du tableau de bord. Ne les modifie que si
tu sais ce que tu fais.

### Services

| Service | Rôle |
|---|---|
| `zendure_local_pilot.set_power` | Consigne de puissance, bornée par les curseurs *Décharge maximale* / *Charge maximale* |
| `zendure_local_pilot.set_limits` | Plafonds de décharge et de charge |
| `zendure_local_pilot.set_soc` | Bornes de charge, échelle du firmware détectée |
| `zendure_local_pilot.write_properties` | Écriture brute de propriétés zenSDK |
| `zendure_local_pilot.redeploy_script` | Redéploiement du script du Shelly, sans troncature |
| `zendure_local_pilot.reset_health` | Réinitialise l'estimation de santé des packs |

## Deux comportements à connaître

**Arrêter la régulation remet la batterie au repos.** Sans cela, elle
conserverait sa dernière consigne et continuerait d'injecter ou de tirer
indéfiniment. C'est le même repli de sécurité que l'automatisation de la
version YAML.

**Une batterie muette ne fait pas tout disparaître.** Les entités issues du
Shelly restent lisibles et modifiables : c'est justement le moment où l'on
veut pouvoir brider la régulation. Seules les entités de la batterie
deviennent indisponibles.

## Limites connues

- Non testée sur une installation réelle à ce jour.
- Les compteurs d'énergie sont calculés à partir des relevés toutes les 5 s
  et sauvegardés toutes les minutes : une coupure brutale de Home Assistant
  perd au plus une minute de cumul. Un trou de plus de 2 minutes (HA arrêté,
  batterie muette) n'est pas intégré plutôt que d'inventer de l'énergie.
- Les composants virtuels doivent exister sur le Shelly ; ils sont créés par
  le script.
- La Hyper 2000 reste incompatible : elle n'expose pas le zenSDK.

## Signaler un problème

[Ouvrir une issue](https://github.com/zarzak12/zendure-local-pilot/issues) en
joignant la sortie de `curl -s http://IP_BATTERIE/properties/report` et les
journaux de Home Assistant filtrés sur `zendure_local_pilot`.
