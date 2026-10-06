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
  tableau de bord qui s'importe tel quel. Le script `personnaliser.ps1`
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

Le script de régulation doit **déjà tourner sur le Shelly**. L'intégration le
vérifie et refuse la configuration s'il est absent : sans lui, il n'y aurait
rien à superviser et aucune batterie à découvrir. Voir le [README](../README.md)
pour le déploiement du script.

## Formulaire de configuration

| Champ | Rôle |
|---|---|
| Adresse IP du Shelly | C'est le seul point d'entrée. L'adresse de la batterie est découverte via le script. |
| Canal de la pince réseau | `em1:0`, `1` ou `2`. **Le canal que ta pince réseau mesure réellement.** |
| Nombre de packs | Détermine combien de jeux d'entités de pack sont créés. Les packs absents restent indisponibles. |
| Reprendre les entités de la version YAML | À cocher si tu viens des packages. Voir ci-dessous. |

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

L'intégration libère alors les anciennes entrées de registre puis reprend les
mêmes identifiants. **L'historique et les statistiques long terme sont rangés
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

En revanche, **toutes les mesures** (SOC, puissances, températures, énergies)
conservent leur identifiant et leur historique.

Pense à mettre à jour tes automatisations qui référençaient ces aides, et à
remplacer les appels `script.zendure_solarflow4000mix_set_power` par le
service `zendure_local_pilot.set_power`.

## Ce que l'intégration expose

### Mesures

Les mêmes que la version YAML : SOC, puissances d'entrée et de sortie,
production photovoltaïque, tensions, températures, détail par pack,
estimations d'énergie disponible et requise, état de la liaison.

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
| `switch` | Régulation (démarre ou arrête le script du Shelly) |
| `binary_sensor` | Script en marche, veille, défaut, liaison batterie |

Les réglages fins de la régulation (gain, zone morte, hystérésis…) sont
désactivés par défaut : active-les dans la page de l'appareil si tu sais ce
que tu fais.

### Services

| Service | Rôle |
|---|---|
| `zendure_local_pilot.set_power` | Consigne de puissance, bornée par les limites de la batterie |
| `zendure_local_pilot.set_limits` | Plafonds de décharge et de charge |
| `zendure_local_pilot.set_soc` | Bornes de charge, échelle du firmware détectée |
| `zendure_local_pilot.write_properties` | Écriture brute de propriétés zenSDK |
| `zendure_local_pilot.redeploy_script` | Redéploiement du script du Shelly, sans troncature |

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
- Les compteurs d'énergie cumulés de la version YAML
  (`platform: integration`, `utility_meter`) ne sont pas encore portés :
  garde-les en YAML si tu y tiens, ils cohabitent sans conflit.
- Les composants virtuels doivent exister sur le Shelly ; ils sont créés par
  le script.
- La Hyper 2000 reste incompatible : elle n'expose pas le zenSDK.

## Signaler un problème

[Ouvrir une issue](https://github.com/zarzak12/zendure-local-pilot/issues) en
joignant la sortie de `curl -s http://IP_BATTERIE/properties/report` et les
journaux de Home Assistant filtrés sur `zendure_local_pilot`.
