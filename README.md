# Zendure SolarFlow — pilotage 100 % local (Shelly Pro 3EM + Home Assistant)

[![Licence : MIT](https://img.shields.io/badge/Licence-MIT-green.svg)](LICENSE)
![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.10%2B-41BDF5?logo=homeassistant&logoColor=white)
![Shelly Pro 3EM](https://img.shields.io/badge/Shelly-Pro%203EM-FF5C00)
![100 % local](https://img.shields.io/badge/Cloud-non%20requis-success)

Pilotage **entièrement local** d'une batterie **Zendure SolarFlow** via l'API locale
[zenSDK](https://github.com/Zendure/zenSDK), avec une régulation **autoconsommation
(injection zéro)** qui tourne **directement dans le Shelly Pro 3EM**.

Développé sur une **SolarFlow 4000 MIX PRO**, le projet fonctionne sur **tous les appareils
qui exposent le zenSDK** : SolarFlow 2400 AC / AC+ / Pro, 800 / 800 Plus / 800 Pro,
1600 AC+, 3000 et 4000 MIX. Rien à adapter d'un modèle à l'autre : la batterie
bride d'elle-même ce qu'elle ne peut pas fournir.
Voir [Modèles compatibles](#modèles-compatibles).

> **Pourquoi ce projet ?**
> L'intégration HACS [Zendure-HA](https://github.com/Zendure/Zendure-HA) ne gère pas encore
> la 4000 MIX PRO ([issue #1550](https://github.com/Zendure/Zendure-HA/issues/1550)).
> Ce dépôt s'appuie sur zenSDK et s'inspire du travail de
> [Gielz1986/Zendure-HA-zenSDK](https://github.com/Gielz1986/Zendure-HA-zenSDK).

---

## Deux façons d'installer

Dans les deux cas, la régulation tourne **dans le Shelly** : les étapes
[1](#étape-1--activer-lapi-locale-de-la-zendure),
[2](#étape-2--préparer-le-shelly-pro-3em) et
[3](#étape-3--installer-le-script-de-régulation-dans-le-shelly) ci-dessous
(API locale de la Zendure, préparation du Shelly, script de régulation) sont
**obligatoires**. Seule la partie Home Assistant diffère :

| | **Intégration HACS** (bêta) | **Packages YAML** (stable) |
|---|---|---|
| Installation | HACS + un formulaire (l'IP du Shelly) | copie de 4 fichiers + `configuration.yaml` |
| Intégration Shelly officielle | inutile pour la régulation ; garde-la si tes compteurs d'énergie (Tempo, cumuls…) l'utilisent | requise (étape 4) |
| Tableau de bord | [`dashboard_integration.yaml`](dashboard/dashboard_integration.yaml), à coller tel quel | à personnaliser avec `tools/personnaliser.ps1` |
| Mises à jour | par HACS | à la main |
| Suite des étapes | étapes 1 à 3, puis **[Option A](#option-a--intégration-hacs-recommandée)** | étapes 1 à 3, puis **[Option B](#option-b--packages-yaml)** (étapes 4 à 7) |

Tu viens des packages YAML et veux passer à l'intégration ? Suis la section
[Migrer depuis les packages YAML](#migrer-depuis-les-packages-yaml) : ton
historique, tes compteurs d'énergie et la santé mesurée de tes packs sont
conservés.

---

## Sommaire

- [Modèles compatibles](#modèles-compatibles)
- [Principe de fonctionnement](#principe-de-fonctionnement)
- [Ce que contient le dépôt](#ce-que-contient-le-dépôt)
- [Prérequis](#prérequis)
- [Installation pas à pas](#installation-pas-à-pas)
  - [Étape 1 — Activer l'API locale de la Zendure](#étape-1--activer-lapi-locale-de-la-zendure)
  - [Étape 2 — Préparer le Shelly Pro 3EM](#étape-2--préparer-le-shelly-pro-3em)
  - [Étape 3 — Installer le script de régulation dans le Shelly](#étape-3--installer-le-script-de-régulation-dans-le-shelly)
- [Option A — Intégration HACS (recommandée)](#option-a--intégration-hacs-recommandée)
  - [A1 — Vérifier les prérequis](#a1--vérifier-les-prérequis)
  - [A2 — Ajouter le dépôt dans HACS](#a2--ajouter-le-dépôt-dans-hacs)
  - [A3 — Télécharger l'intégration](#a3--télécharger-lintégration)
  - [A4 — Ajouter l'intégration](#a4--ajouter-lintégration)
  - [A5 — Vérifier que tout est en place](#a5--vérifier-que-tout-est-en-place-5-minutes)
  - [A6 — Installer le tableau de bord](#a6--installer-le-tableau-de-bord)
  - [A7 — Régler la régulation](#a7--régler-la-régulation)
  - [A8 — Mettre à jour](#a8--mettre-à-jour)
  - [A9 — Recharger en heures creuses](#a9--recharger-en-heures-creuses-facultatif)
  - [Migrer depuis les packages YAML](#migrer-depuis-les-packages-yaml)
  - [Dépannage de l'intégration](#dépannage-de-lintégration)
- [Option B — Packages YAML](#option-b--packages-yaml)
  - [Étape 4 — Ajouter le Shelly à Home Assistant](#étape-4--ajouter-le-shelly-à-home-assistant)
  - [Étape 5 — Installer les packages Home Assistant](#étape-5--installer-les-packages-home-assistant)
  - [Étape 6 — Renseigner l'IP du Shelly et le canal de la pince](#étape-6--renseigner-lip-du-shelly-et-le-canal-de-la-pince)
  - [Étape 7 — Installer le dashboard](#étape-7--installer-le-dashboard)
- [Utilisation](#utilisation)
- [Mettre à jour](#mettre-à-jour)
- [Référence des réglages](#référence-des-réglages)
- [Référence des entités](#référence-des-entités)
- [État de santé des batteries](#état-de-santé-des-batteries)
- [Pour les experts](#pour-les-experts)
  - [Découverte automatique de la Zendure](#découverte-automatique-de-la-zendure)
  - [Garde-fous : pourquoi la batterie ne peut plus rester figée](#garde-fous--pourquoi-la-batterie-ne-peut-plus-rester-figée)
- [Dépannage](#dépannage)
- [Sécurité et avertissements](#sécurité-et-avertissements)
- [Licence](#licence)
- [Crédits](#crédits)

---

## Modèles compatibles

Le seul critère est l'**API locale zenSDK**. Si `http://IP_BATTERIE/properties/report`
répond un JSON, le projet fonctionne. Tous ces appareils partagent le même contrat
d'API : mêmes points d'entrée, mêmes noms de propriétés.

| Appareil | Chaîne `product` | Charge | Décharge | Remarques |
|---|---|---|---|---|
| SolarFlow 4000 MIX PRO | `solarFlow4000MixPro` | 3000 W | 3000 W | modèle de développement, validé en réel |
| SolarFlow 4000 MIX AC+ | `solarFlow4000MixAC+` | 3000 W | 3000 W | |
| SolarFlow 3000 MIX AC+ | `solarFlow3000MixAC+` | 3000 W | 3000 W | |
| SolarFlow 2400 AC | `solarFlow2400AC` | 2400 W | 2400 W | **sans entrée PV** : les capteurs solaires restent à 0 |
| SolarFlow 2400 AC+ | `solarFlow2400AC+` | 3200 W | 2400 W | |
| SolarFlow 2400 Pro | `solarFlow2400Pro` | 3200 W | 2400 W | |
| SolarFlow 1600 AC+ | `solarFlow1600AC+` | 1600 W | 1600 W | |
| SolarFlow 800 / Plus / Pro | `solarFlow800…` | 800–1200 W | 800–1000 W | |

Les puissances ci-dessus sont **indicatives** : le script ne s'en sert pas. La
régulation est bornée par les curseurs *Décharge max* et *Charge max* (4000 W par
défaut), et la batterie bride d'elle-même ce que son matériel ne peut pas fournir.
Règle ces curseurs à la puissance de ton modèle si tu veux une borne exacte.

> ⚠️ Le script ne s'appuie **pas** sur `inverseMaxPower` et `chargeMaxLimit`. Sur
> certains modèles ou firmwares, ces champs suivent les consignes que le script
> vient d'écrire au lieu de rester fixes. Une version précédente les utilisait
> comme plafonds, ce qui provoquait de fortes oscillations ; elle pouvait aussi
> abaisser la valeur des curseurs *Décharge max* / *Charge max*. Après la mise à
> jour, vérifie que ces deux curseurs sont revenus à la valeur que tu souhaites.

De même, la **capacité des packs** est déduite du préfixe de leur numéro de série
(AB1000, AB2000, AB3000, AIO2400, packs internes I2400 et I8000…), comme le fait
l'intégration officielle. Rien à déclarer.

### Hyper 2000 : non compatible, et ça ne changera pas

Le **Hyper 2000 n'expose pas le zenSDK** et ne l'exposera pas. Ce n'est pas une limite de
ce projet mais une décision de Zendure, confirmée à plusieurs reprises par un membre de
leur équipe :

> *« it will not support zenSDK-style local control features such as mDNS or local API
> access […] I do not see a realistic path »*
> — zenSDK [#61](https://github.com/Zendure/zenSDK/issues/61), voir aussi
> [#18](https://github.com/Zendure/zenSDK/issues/18)

Son module de connectivité a été développé par un tiers et se pilote uniquement en MQTT,
avec un mécanisme (`function/invoke`, `deviceAutomation`) sans rapport avec le
`/properties/write` utilisé ici. Les autres projets de l'écosystème font le même constat et
le codent en dur comme non supporté. **Merci de ne pas ouvrir d'issue à ce sujet.**

### Préfixe des entités

Les **noms affichés** suivent ton modèle : « Zendure SolarFlow 2400 AC+ SOC », « Zendure
SolarFlow 800 Pro puissance »… c'est automatique, déduit de ce que la batterie annonce.

En revanche, les **identifiants techniques** restent `…_zendure_solarflow4000mix_…`, quel que
soit ton modèle. C'est un **préfixe historique**, conservé volontairement : le renommer
casserait l'historique, les statistiques à long terme, les automatisations et les dashboards
de tous ceux qui ont déjà installé le projet. Ce n'est qu'un identifiant, invisible au
quotidien.

---

## Principe de fonctionnement

```
   ┌──────────────────┐   HTTP (LAN)   ┌──────────────────────────┐
   │  Shelly Pro 3EM  │◄──────────────►│  Zendure SolarFlow 4000  │
   │  (script JS)     │  GET  /properties/report                  │
   │  pince réseau    │  POST /properties/write                   │
   └────────┬─────────┘                └──────────┬───────────────┘
            │ entités virtuelles                  │ REST lecture
            │ (mode, consignes)                   │ + écriture ponctuelle
            ▼                                     ▼
   ┌────────────────────────────────────────────────────────────┐
   │                      Home Assistant                        │
   │   paramétrage · supervision · graphiques · sécurité        │
   └────────────────────────────────────────────────────────────┘
```

**Point clé : Home Assistant n'est PAS dans la boucle de régulation.**
Le Shelly lit sa propre pince de courant et pilote la Zendure toutes les 2 secondes,
même si HA est éteint, en cours de mise à jour ou planté. HA sert uniquement à :

- choisir le mode et les consignes,
- afficher l'état, l'énergie, les rendements,
- remettre la Zendure à 0 W si le script Shelly s'arrête (sécurité).

### Algorithme de régulation

À chaque cycle (2 s par défaut) :

```
puissance_ac_actuelle = outputHomePower - gridInputPower
buffer   = buffer_décharge si (puissance_ac_actuelle + puissance_réseau) ≥ 0
           buffer_charge   sinon
consigne = puissance_ac_actuelle + (puissance_réseau - buffer) × gain
```

- `puissance_réseau` : mesure du Shelly (canal `em1` configurable), **+ = soutirage**, **− = injection**
- `buffer` : point de fonctionnement visé sur la pince, de **−200 à +200 W**.
  Positif = soutirage résiduel volontaire (marge anti-injection) ; `0` = injection
  zéro stricte ; **négatif = injection résiduelle tolérée**, utile si ton compteur
  arrondit à la baisse ou si tu préfères garantir zéro soutirage.
  Deux valeurs distinctes existent : l'une appliquée quand la batterie **décharge**,
  l'autre quand elle **charge**. Tu peux ainsi viser +20 W en décharge (aucune
  injection) et −10 W en charge (récupérer tout le surplus).
- `gain` : amortissement (0,75 = 75 % de la correction par cycle → pas d'oscillation)

La consigne est ensuite :
1. bridée selon le mode (charge seule → ≤ 0, décharge seule → ≥ 0),
2. forcée à 0 si le SOC est en butée (`socLimit`),
3. bornée par *décharge max* / *charge max*,
4. forcée à 0 si `|consigne| < zone morte`,
5. **écrite seulement si** `|consigne − consigne_actuelle| > hystérésis` (limite l'usure flash).

### Anti-battement charge ↔ décharge

Inverser le sens de la batterie fait commuter le relais de l'onduleur (`acMode`). Écrire
**0 W**, en revanche, ne le touche pas. Le script s'appuie sur cette différence :

1. la référence est l'**état du relais**, pas le signe de la consigne. Une batterie arrêtée
   à 0 W reste « en charge » ou « en décharge » côté relais ;
2. une demande dans le sens opposé au relais est ramenée à **0 W** : la batterie s'arrête,
   le relais ne bouge pas ;
3. le relais ne bascule que si cette demande se maintient **sans interruption** :
   `zendure_flip` secondes (8 s par défaut) si elle atteint `zendure_flipw` (100 W par
   défaut), **cinq fois plus longtemps** sinon. Un petit surplus durable finit donc
   toujours par être stocké. Pendant l'attente, la batterie est à 0 W : la mesure du
   Shelly reflète la vraie consommation de la maison.

Une maison qui oscille autour de l'équilibre (nuage, appareil qui démarre et s'arrête)
ne remplit jamais ces deux conditions : la batterie se met à 0 W et attend, sans
claquement de relais. Un vrai changement de situation (surplus solaire durable, gros
appareil allumé) bascule après `zendure_flip` secondes.

Pour encore moins de bascules, augmente `zendure_flip` (30–60 s) et/ou `zendure_flipw`
(200–300 W). Mets `zendure_flip` à `0` pour désactiver la protection.

> 💡 Cette protection ne concerne **que les inversions de sens**. Dans un même sens, la
> puissance suit la maison librement, toujours bornée par *Décharge max* et *Charge max*.

Après N minutes à 0 W, le script passe la Zendure en **veille profonde** (`smartMode: 0`)
et ne la réveille que si la consigne dépasse le *seuil de réveil*.

---

## Ce que contient le dépôt

| Fichier | Rôle |
|---|---|
| `scripts/zendure_solarflow_4000_mix_pro.js` | **Le cœur du système.** Script Shelly : régulation + entités virtuelles + config KVS |
| `packages/zendure_solarflow4000mix.yaml` | Lecture REST de la Zendure, ~30 capteurs, compteurs d'énergie, scripts d'écriture, sécurité |
| `packages/zendure_solarflow4000mix_dashboard.yaml` | Capteurs dérivés pour le dashboard (rendements, flux PV, statistiques) |
| `packages/zendure_solarflow4000mix_reglages.yaml` | Édition des réglages avancés du Shelly (KVS) depuis HA |
| `packages/zendure_solarflow4000mix_sante.yaml` | Estimation par la mesure de l'état de santé (SOH) de chaque pack |
| `dashboard/dashboard HA.yaml` | Dashboard 4 vues : Zendure, Santé, Historique, Réglages |
| `dashboard/dashboard_integration.yaml` | Le même, pour l'[intégration HACS](docs/INTEGRATION_HACS.md) : à coller tel quel (généré par `tools/generer_dashboard_integration.py`) |
| `tools/deploy_shelly.ps1` | Téléversement fiable du script dans le Shelly, **avec vérification par relecture** |
| `tools/personnaliser.ps1` / `.sh` | Génère `dashboard-perso.yaml` adapté à ton Shelly |

---

## Prérequis

### Matériel

- **Zendure SolarFlow 4000 MIX PRO** avec un firmware supportant zenSDK (API locale HTTP)
- **Shelly Pro 3EM** (ou Pro EM / Pro 3EM-400) avec une **pince sur l'arrivée générale**
- Les deux appareils sur **le même réseau local** que Home Assistant

### Logiciel

| Composant | Version minimale | Note |
|---|---|---|
| Home Assistant | 2024.11+ (intégration) · 2024.10+ (YAML) | en YAML, `default_entity_id` sur les templates demande 2025.x, voir [Dépannage](#dépannage) |
| Firmware Shelly | 1.0.0+ | nécessaire pour les **composants virtuels** et le **KVS** ; 2.x pris en charge |
| [HACS](https://hacs.xyz) | — | pour l'intégration, et pour `apexcharts-card` |
| `apexcharts-card` | — | via HACS, uniquement pour les graphiques du tableau de bord |

### Compétences

- Savoir redémarrer Home Assistant et installer un dépôt dans HACS
- Pour l'option YAML seulement : savoir éditer `configuration.yaml` (via l'add-on
  **File Editor**, **Studio Code Server** ou SSH)

---

## Installation pas à pas

L'installation se fait en deux temps :

1. **Le matériel, commun à tous** : [étapes 1 à 3](#étape-1--activer-lapi-locale-de-la-zendure)
   ci-dessous. Elles mettent la régulation en place dans le Shelly. À ce
   stade, l'autoconsommation fonctionne déjà, même sans Home Assistant.
2. **Home Assistant, au choix** :
   - **[Option A — Intégration HACS](#option-a--intégration-hacs-recommandée)**
     (recommandée) : un formulaire, un tableau de bord à coller tel quel,
     des mises à jour automatiques ;
   - **[Option B — Packages YAML](#option-b--packages-yaml)** : la méthode
     historique, étapes 4 à 7.

Tu as déjà les packages YAML et tu veux passer à l'intégration ? Fais
directement la [migration](#migrer-depuis-les-packages-yaml).

### Étape 1 — Activer l'API locale de la Zendure

1. Dans l'application **Zendure**, ouvre ta SolarFlow 4000 MIX PRO.
2. **Ajoute un HEMS** dans les réglages de l'appareil, puis **quitte l'écran** pour appliquer.
   👉 C'est cette manipulation qui active le serveur HTTP local (voir la note EN 18031 du
   [README zenSDK](https://github.com/Zendure/zenSDK)).
3. **Tu n'as pas besoin de connaître son adresse IP** : le script Shelly la
   découvre et la transmet à Home Assistant (voir
   [Découverte automatique](#découverte-automatique-de-la-zendure)).

   > 💡 Une réservation DHCP dans ton routeur reste un confort : elle évite
   > la coupure d'environ une minute le jour où le bail se déplace.
   >
   > ⚠️ Sur ce modèle, la MAC **Wi-Fi est aléatoire** : une réservation DHCP
   > peut rester sans effet. En **RJ45** en revanche elle fonctionne.
4. **Vérifie** depuis un PC du réseau, en remplaçant `IP_ZENDURE` :

   ```bash
   curl -s http://IP_ZENDURE/properties/report
   ```

   Tu dois obtenir un JSON de ce type :

   ```json
   {"timestamp":1789722224,"sn":"XXXXXXXXXXXXXXX","product":"solarFlow4000MixPro",
    "properties":{"electricLevel":17,"outputHomePower":0,"gridInputPower":0,
    "solarInputPower":0,"outputLimit":181,"inputLimit":0,"smartMode":1,...},
    "packData":[{"sn":"YYYYYYYYYYYYYYY","socLevel":17,...}]}
   ```

   ⚠️ Si tu obtiens une erreur de connexion, l'API locale n'est pas activée : refais l'étape 2.
   Le `sn` est requis dans toutes les écritures — le système le lit et le mémorise tout seul.

   > 💡 Le champ `product` t'indique ton modèle exact. S'il apparaît dans
   > [Modèles compatibles](#modèles-compatibles), tu n'as **aucune adaptation à faire** :
   > la capacité des batteries est détectée automatiquement.

> 💡 **Trouver l'IP de la Zendure** (utile seulement pour ce test) : elle
> s'annonce en mDNS sous `Zendure-<Modèle>-<12 derniers caractères MAC>`.
> Linux : `avahi-browse -r _zendure._tcp` — macOS : `dns-sd -B _zendure._tcp`.
> Sinon, regarde la liste des appareils connectés dans ton routeur.

---

### Étape 2 — Préparer le Shelly Pro 3EM

1. Donne-lui une **IP fixe** (réservation DHCP dans ton routeur). C'est la
   **seule adresse que tu auras à saisir** dans tout le projet : note-la.
2. Interface web du Shelly → **Settings → Device profile** → choisis **Monophasé
   (« Single-phase / Triphase monitor »)**.
3. **Repère laquelle des trois pinces mesure l'arrivée générale.** Elles sont
   numérotées `em1:0`, `em1:1` et `em1:2`, et rien n'impose que ce soit la
   première : cela dépend de ton câblage. Dans **Status**, regarde laquelle suit
   la consommation de toute la maison (allume un gros appareil pour lever le
   doute). **Note son numéro** — tu le saisiras à l'étape 6.
   L'outil `tools/personnaliser.ps1` affiche les trois pinces pour t'aider.
4. Vérifie le signe de la mesure : la puissance active de ta pince doit être
   **positive quand tu soutires** et **négative quand tu injectes**.
   Si c'est inversé, retourne la pince ou active l'inversion dans les réglages du canal.
5. Mets le firmware à jour (**Settings → Firmware**).

> ⚠️ Si tu utilises le Shelly en **triphasé**, ce script ne convient pas tel quel :
> il faudrait lire `em:0.total_act_power` au lieu de `em1:N.act_power`
> (voir [Pour les experts](#pour-les-experts)).

---

### Étape 3 — Installer le script de régulation dans le Shelly

> 🛑 **Ne colle pas le script dans l'éditeur web du Shelly.**
> L'éditeur **tronque silencieusement** les collages volumineux : au-delà de ~7 ko, la fin
> du code est perdue. Le script fait ~18 ko. Pire, si la coupure tombe à l'intérieur d'un
> commentaire, le reste du fichier est avalé par ce commentaire : le script **démarre sans
> aucune erreur** (`running: true`) mais ne régule rien, et le seul indice est un
> **`cpu` à 0 %**. Utilise le déployeur fourni, qui vérifie par relecture.

1. Interface web du Shelly → onglet **Scripts** → **Add script**, nomme-le `Zendure`,
   **Save** sans rien coller. Note l'**ID** attribué (visible dans l'URL `.../script/1`).
   Ce projet suppose **`id=1`**.
2. **Rien à modifier dans le script** : aucune adresse IP n'y est codée.
   Le script découvre la Zendure tout seul au premier démarrage (voir
   [Découverte automatique](#découverte-automatique-de-la-zendure)).

   ```js
   let DEFAULTS = { zendure_ip: "", zendure_sn: "", zendure_em: 0, zendure_tick: 250, zendure_period: 1000,
       zendure_gain: 0.9, zendure_dead: 30, zendure_hyst: 25, zendure_wake: 80, zendure_flip: 8 };
   ```

   > 💡 Si tu connais déjà l'IP de ta batterie, tu peux la mettre dans
   > `zendure_ip` : tu gagneras les ~30 s de recherche initiale. Ce n'est
   > en rien obligatoire.

3. Téléverse depuis un terminal, à la racine du dépôt, en remplaçant
   `IP_SHELLY` par l'adresse notée à l'étape 2 :

   ```powershell
   powershell -ExecutionPolicy Bypass -File tools\deploy_shelly.ps1 -Ip IP_SHELLY
   ```

   Ajoute `-Id 2` si ton script porte un autre identifiant. Le déployeur arrête le script,
   écrit par blocs de 1 ko, **relit tout et compare** (3 tentatives), puis redémarre.
   Il doit afficher `verification OK` — sinon **n'utilise pas** le résultat.

4. Active **« Run on startup »** (l'interrupteur à côté du script) — sinon il ne redémarrera
   pas après une coupure de courant.
5. Regarde la console du script : tu dois voir, au bout de quelques dizaines
   de secondes, la batterie être trouvée :

   ```
   Zendure cfg: {"ip":"","tick":250,"period":1000,"gain":0.9,...}
   Zendure injoignable : recherche sur 192.168.x.0/24
   Zendure retrouvée sur 192.168.x.y - SN XXXXXXXXXXXXXXX
   Zendure: prêt
   ```

6. **Contrôle final**, une fois un mode régulé sélectionné :

   ```
   http://IP_SHELLY/rpc/Script.GetStatus?id=1
   ```

   `cpu` doit être **nettement supérieur à 0** (~30 % en régulation active) et `mem_peak`
   dépasser 14 000. Un `cpu` à 0 % signifie que le code est incomplet : recommence l'étape 3.

<details>
<summary>Pas de PowerShell (Linux / macOS) ?</summary>

Colle le script dans l'éditeur web, **Save**, puis vérifie impérativement la taille reçue :

```bash
curl -s 'http://IP_SHELLY/rpc/Script.GetCode?id=1&offset=0&len=1' | grep -o '"left":[0-9]*'
```

`left` + 1 doit égaler la taille du fichier en **octets** (`wc -c` sur le `.js`).
Si le compte n'y est pas, le collage a été tronqué.
</details>

Au premier démarrage, le script crée **8 composants virtuels** dans le Shelly :

| Composant | Type | Rôle |
|---|---|---|
| `enum:200` | Liste | Mode de régulation |
| `number:200` | Nombre | Décharge max (W) |
| `number:201` | Nombre | Charge max (W) |
| `number:202` | Nombre | Consigne manuelle (W) |
| `number:203` | Nombre | Buffer décharge (W) |
| `number:204` | Nombre | Délai de veille (min) |
| `number:205` | Nombre | Buffer charge (W) |
| `boolean:200` | Booléen | Zendure en veille (lecture seule) |

Le script est **idempotent** : il réaligne la configuration des composants
existants (`SetConfig`) au lieu d'en recréer, et supprime au démarrage tout
composant `Zendure*` en doublon. Le Shelly plafonne à 10 composants virtuels.

Vérifie-les dans l'onglet **Components / Virtual components** du Shelly.

---

## Option A — Intégration HACS (recommandée)

L'intégration **Zendure Local Pilot** remplace les packages YAML : un
formulaire à remplir, des identifiants d'entités identiques chez tout le
monde, un tableau de bord à coller tel quel, et des mises à jour par HACS,
**script du Shelly compris**.

Ce qui ne change pas : la régulation tourne toujours **dans le Shelly**.
L'intégration règle, supervise et protège, mais ne régule pas. Si Home
Assistant s'arrête, l'autoconsommation continue.

> **Bêta.** Elle est en service sur une SolarFlow 4000 MIX PRO avec un Shelly
> Pro 3EM en firmware 2.0.1. Si tu rencontres un problème, la
> [section Dépannage](#dépannage-de-lintégration) liste ceux déjà rencontrés.
> La référence complète (entités, services, comportements) est dans
> [docs/INTEGRATION_HACS.md](docs/INTEGRATION_HACS.md).

### A1 — Vérifier les prérequis

Avant de commencer, assure-toi que :

- [ ] **les étapes 1 à 3 sont faites** : `curl http://IP_ZENDURE/properties/report`
      répond un JSON, et le script tourne dans le Shelly (onglet **Scripts** :
      *running*). Sans script, l'intégration refuse de s'installer ;
- [ ] **le Shelly a une IP fixe** (réservation DHCP), c'est la seule adresse
      que tu saisiras ;
- [ ] **Home Assistant est en 2024.11 ou plus récent** (Paramètres →
      À propos) ;
- [ ] **HACS est installé** ([hacs.xyz](https://hacs.xyz)).

Tu viens des packages YAML ? Ne suis pas les étapes A2 à A5 telles quelles :
fais la [migration](#migrer-depuis-les-packages-yaml), qui les reprend dans
le bon ordre.

### A2 — Ajouter le dépôt dans HACS

1. Ouvre **HACS**, puis le menu **⋮** en haut à droite → **Dépôts
   personnalisés**.
2. **Dépôt** : `https://github.com/zarzak12/zendure-local-pilot`
   — l'adresse du dépôt **seule**, sans `/tree/…` ni nom de branche.
3. **Type** : **Intégration** → **Ajouter**.

> ⚠️ « Repository structure for vX is not compliant » : l'adresse contient
> `/tree/…`, ou HACS a gardé en cache une ancienne version. Supprime le
> dépôt de la liste (corbeille) et ajoute-le de nouveau, avec l'adresse
> exacte ci-dessus.

### A3 — Télécharger l'intégration

1. Dans HACS, cherche **Zendure Local Pilot** et ouvre-la.
2. **Télécharger** → garde la version proposée (la plus récente) →
   **Télécharger**.
3. **Redémarre Home Assistant** : Paramètres → Système → ⏻ en haut à droite →
   *Redémarrer Home Assistant*. Indispensable : sans redémarrage,
   l'intégration n'apparaît pas.

### A4 — Ajouter l'intégration

1. **Paramètres → Appareils et services** → **+ Ajouter une intégration**
   (en bas à droite) → tape **Zendure** → **Zendure Local Pilot**.
2. Remplis le formulaire :

   | Champ | Quoi mettre |
   |---|---|
   | **Adresse IP du Shelly** | l'IP fixe du Shelly Pro 3EM. Celle de la batterie n'est pas demandée : le script la découvre |
   | **Nombre de packs batterie** | le nombre de packs réellement présents (1 pour une 4000 MIX PRO sans extension). En trop, les packs absents apparaissent indisponibles |
   | **Reprendre les entités de la version YAML** | **coché** si tu migres depuis les packages, sans effet sinon |

3. **Valider**. L'intégration vérifie le Shelly avant de créer quoi que ce
   soit :

   | Message | Signification | Que faire |
   |---|---|---|
   | *Aucune réponse à cette adresse* | Shelly injoignable | vérifie l'IP (navigateur : `http://IP_SHELLY`) |
   | *Cet appareil a répondu, mais ce n'est pas un Shelly* | mauvaise IP | celle du Shelly, pas celle de la batterie |
   | *Aucun script de régulation Zendure trouvé* | script absent | refais l'[étape 3](#étape-3--installer-le-script-de-régulation-dans-le-shelly) ; son nom doit contenir « zendure » |
   | *Unknown error occurred* | bug | voir [Dépannage](#dépannage-de-lintégration) et les journaux |

Un appareil **« Zendure &lt;ton modèle&gt; »** apparaît, avec toutes ses
entités. Elles sont toutes nommées `…zendure_solarflow4000mix_…` quel que soit
ton modèle : c'est voulu, c'est ce qui rend le tableau de bord universel.

### A5 — Vérifier que tout est en place (5 minutes)

Ouvre **Paramètres → Appareils et services → Zendure Local Pilot → l'appareil**
et contrôle :

| Où | Entité | Attendu |
|---|---|---|
| Capteurs | **Script état** | *En marche* |
| Diagnostic | **Script version** | la dernière version. Si le script de ton Shelly était plus ancien, l'intégration l'a **mis à jour toute seule** au démarrage (quelques secondes, réglages conservés) |
| Diagnostic | **Script CPU** | au-dessus de 0 % dans un mode régulé |
| Capteurs | **Liaison batterie** | *Connecté* |
| Contrôles | **Mode** | ton mode habituel (*Autoconsommation* pour un usage normal) |
| Capteurs | **Réseau** | la même valeur que la pince du Shelly, au signe près (+ soutirage, − injection) |

Puis vérifie la **pince** : **Configuration → Pince réseau lue**. Elle vaut 0
par défaut. Si ton arrivée générale est sur la 2e ou la 3e pince, choisis-la
maintenant (*Pince 2 (em1:1)* ou *Pince 3 (em1:2)*). Pour savoir laquelle :
allume un gros appareil et regarde quelle pince suit, dans l'interface du
Shelly ou dans l'intégration Shelly officielle. Le réglage est enregistré dans
le Shelly et survit à toutes les mises à jour.

Enfin, **Paramètres → Système → Réparations** ne doit rien signaler.

### A6 — Installer le tableau de bord

1. **apexcharts-card**, pour les graphiques : HACS → cherche
   `apexcharts-card` (catégorie Tableau de bord) → **Télécharger**, puis
   recharge la page du navigateur (**Ctrl+F5**).
2. Ouvre [dashboard/dashboard_integration.yaml](dashboard/dashboard_integration.yaml)
   sur GitHub → bouton **Copy raw file** (icône de copie). HACS ne télécharge
   que l'intégration, pas ce fichier.
3. Crée un tableau de bord : **Paramètres → Tableaux de bord → + Ajouter un
   tableau de bord** → *Nouveau tableau de bord à partir de zéro* → nomme-le
   (par exemple « Batterie ») → ouvre-le.
4. ✏️ **Modifier** → **⋮** → **Modifier en YAML** → remplace tout le contenu
   par ce que tu as copié → **Enregistrer**.

Rien à personnaliser. Tu obtiens 4 vues : **Zendure** (flux, SOC, packs),
**Santé**, **Historique** et **Réglages**. Ce dernier réunit tous les réglages
de la régulation, l'état du script du Shelly et les boutons *Relancer* /
*Redéployer*.

Pour **ajouter** ces vues à un tableau de bord existant plutôt que d'en créer
un, ne colle que le contenu de la clé `views:` à la suite des tiennes.

### A7 — Régler la régulation

Tout se règle depuis l'appareil ou l'onglet **Réglages** du tableau de bord :

| Réglage | Entité | Pour |
|---|---|---|
| Mode | `select.…_mode` | Autoconsommation, Charge seule, Décharge seule, Manuel, Arrêt |
| Plafonds | `number.…_decharge_max`, `…_charge_max` | limiter la puissance (± 3000 W par exemple) |
| Marges | `number.…_buffer`, `…_buffer_charge` | viser un léger soutirage (+) ou une légère injection (−) |
| Veille | `number.…_delai_veille` | minutes à 0 W avant la veille profonde (0 = jamais) |
| Bornes SOC | `number.…_soc_min_consigne`, `…_soc_max_consigne` | écrites dans la batterie (mémoire flash) |
| Réglages fins | catégorie *Configuration* | gain, zone morte, hystérésis, bascule, lissage : voir [Référence des réglages](#référence-des-réglages) |

L'interrupteur **Régulation** arrête le script du Shelly ; la batterie est
alors remise à 0 W.

Dans **Configurer** (sur la carte de l'intégration) : IP du Shelly, nombre de
packs, et **mise à jour automatique du script**. Désactive-la si tu as
modifié le script à la main (profil triphasé, par exemple), sinon ta
modification sera remplacée à la prochaine mise à jour.

### A8 — Mettre à jour

1. HACS signale la nouvelle version (et *Paramètres → Mises à jour*).
2. **Mettre à jour** → **redémarre Home Assistant**.
3. Si la nouvelle version apporte un nouveau script, il est poussé sur le
   Shelly **automatiquement** au démarrage, vérifié par relecture, réglages
   conservés. Sinon, rien ne se passe côté Shelly.

En cas d'échec de la mise à jour du script, une alerte apparaît dans
*Réparations*, et l'entité **Script de régulation** de *Paramètres → Mises à
jour* permet de relancer l'installation d'un clic.

### A9 — Recharger en heures creuses (facultatif)

Après plusieurs jours sans soleil, la batterie reste vide. Le blueprint
**Recharge en heures creuses** la recharge depuis le réseau pendant ta fenêtre
d'heures creuses, jusqu'à un SOC cible.

[![Importer le blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fzarzak12%2Fzendure-local-pilot%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fzendure_local_pilot%2Frecharge_heures_creuses.yaml)

1. Clique sur le bouton ci-dessus, ou va dans **Paramètres → Automatisations
   et scènes → Blueprints → Importer un blueprint** et colle l'adresse
   `https://github.com/zarzak12/zendure-local-pilot/blob/main/blueprints/automation/zendure_local_pilot/recharge_heures_creuses.yaml`.
2. **Créer une automatisation** à partir du blueprint, puis règle :

   | Réglage | Par défaut | Rôle |
   |---|---|---|
   | Début / fin des heures creuses | 22:00 / 06:00 | la fenêtre de recharge (elle peut passer minuit) |
   | SOC cible | 20 % | recharge jusqu'à ce niveau |
   | Puissance de charge | 600 W | tirée du réseau, bornée par *Charge maximale* |
   | Marge de relance | 2 points | après la cible, ne reprend que si le SOC retombe d'autant |
   | Mode à rétablir | Autoconsommation | le mode remis en place après la recharge |

   Les entités Zendure sont déjà renseignées : leurs identifiants sont les
   mêmes chez tout le monde.

Pendant la recharge, la régulation passe en mode **Manuel** avec une consigne
de charge. Elle reprend ton mode habituel dès que la cible est atteinte, ou à
la fin de la fenêtre, y compris si Home Assistant était arrêté à ce moment-là.
Un mode Manuel que tu as choisi toi-même n'est jamais remplacé.

#### Variante : selon Tempo et la prévision solaire

Pour les abonnés **Tempo** : le blueprint **Charge de nuit selon Tempo et
prévision solaire** ne charge que les nuits qui précèdent une couleur choisie
(Blanc et Rouge par défaut), vise un SOC d'autant plus bas que le lendemain
s'annonce ensoleillé, et réduit la charge pour que la maison et la batterie
restent sous la puissance de ton abonnement.

[![Importer le blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fzarzak12%2Fzendure-local-pilot%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fzendure_local_pilot%2Fcharge_tempo_solaire.yaml)

Il te faut :
- un capteur de **couleur Tempo** pour aujourd'hui et un pour demain (par
  exemple l'intégration *RTE Tempo*). Les valeurs « Bleu / Blanc / Rouge » et
  « blue / white / red » sont reconnues ;
- un capteur de **production solaire prévue** pour aujourd'hui et un pour
  demain, en kWh (par exemple *Forecast.Solar* ou *Solcast*).

Les capteurs « demain » sont lus avant minuit, ceux « aujourd'hui » après :
c'est toujours la journée à préparer qui décide. La décision est reprise
chaque minute, sans mémoire : un redémarrage de Home Assistant en pleine nuit
ne laisse jamais la batterie bloquée en charge.

N'active pas les deux blueprints en même temps : ils se disputeraient le mode
Manuel.

---

### Migrer depuis les packages YAML

L'historique, les statistiques long terme, les compteurs d'énergie et la santé
mesurée des packs sont **conservés** : l'intégration reprend les mêmes
identifiants d'entités, et relit à l'installation la dernière valeur des
compteurs et des capacités mesurées. **L'ordre des étapes compte.**

1. **Sauvegarde** : Paramètres → Système → Sauvegardes → *Créer une
   sauvegarde*. C'est ton retour arrière.
2. **Télécharge l'intégration** ([A2](#a2--ajouter-le-dépôt-dans-hacs) et
   [A3](#a3--télécharger-lintégration)), **sans redémarrer** pour l'instant.
3. **Retire les 4 packages** de `/config/packages/` (File Editor ou Studio
   Code Server), en les gardant de côté :
   - `zendure_solarflow4000mix.yaml`
   - `zendure_solarflow4000mix_dashboard.yaml`
   - `zendure_solarflow4000mix_reglages.yaml`
   - `zendure_solarflow4000mix_sante.yaml`

   **Les 4**, sans exception : un package resté chargé garde ses entités, et
   l'intégration doit alors se rabattre sur des identifiants en `_2`. La
   ligne `packages: !include_dir_named packages` de `configuration.yaml` peut
   rester.
4. **Garde l'intégration Shelly officielle** si tu l'as : tes compteurs
   d'énergie (Tempo, cumuls…) basés sur la pince en dépendent. Elle cohabite
   avec l'intégration Zendure.
5. **Redémarre Home Assistant.**
6. **Ajoute l'intégration** ([A4](#a4--ajouter-lintégration)), case
   **« Reprendre les entités de la version YAML » cochée**.
7. **Vérifie la reprise** :
   - **Réparations** : aucune alerte « Les packages YAML sont encore
     chargés ». Sinon, un package est resté : retire-le, redémarre, puis
     recharge l'intégration ;
   - `sensor.zendure_solarflow4000mix_energie_chargee` affiche une valeur
     proche de celle d'avant, et non 0 ;
   - **Pack 1 santé** affiche ta santé mesurée, si tu en avais une ;
   - puis les contrôles de l'étape [A5](#a5--vérifier-que-tout-est-en-place-5-minutes).
8. **Remplace le tableau de bord** par `dashboard_integration.yaml`
   ([A6](#a6--installer-le-tableau-de-bord)).
9. **Fais le ménage** : Paramètres → Entités, filtre
   `zendure_solarflow4000mix`, et supprime celles marquées *n'est plus
   fournie* (`raw`, `reseau_shelly`, `config_shelly`…) : des capteurs internes
   de la version YAML.
10. **Mets à jour tes propres automatisations**, s'il y a lieu :

    | Avant (YAML) | Après (intégration) |
    |---|---|
    | `input_number.zendure_solarflow4000mix_…` | `number.zendure_solarflow4000mix_…` |
    | `sensor.zendure_solarflow4000mix_reseau_shelly` | `sensor.zendure_solarflow4000mix_reseau` |
    | `script.zendure_solarflow4000mix_set_power` | action `zendure_local_pilot.set_power` |
    | entités `shellypro3em_…_zendure_*` | inchangées si tu gardes l'intégration Shelly officielle, sinon `select.zendure_solarflow4000mix_mode`, etc. |

    Les automatisations de la version YAML (repli de sécurité, synchronisations,
    santé des packs…) n'ont pas à être recréées : l'intégration les fait.

**Ce qui est perdu** : l'historique des curseurs de réglage (ils passent
d'`input_number` à `number`, l'identifiant change), et les compteurs **du
jour** (PV du jour, commutations, zéro soutirage), qui repartent de zéro le
jour de la migration.

**Retour arrière** : supprime l'intégration, remets les 4 packages,
redémarre. L'historique des mesures est conservé dans tous les cas.

---

### Dépannage de l'intégration

| Symptôme | Cause | Solution |
|---|---|---|
| HACS : *Repository structure for vX is not compliant* | adresse avec `/tree/…`, ou cache HACS | supprime le dépôt et ajoute `https://github.com/zarzak12/zendure-local-pilot` |
| Formulaire : *Unknown error occurred* (Shelly en firmware 2.x) | version < 1.3.2 | mets l'intégration à jour, redémarre |
| **Mode** *unknown*, curseurs vides (firmware 2.x) | version < 1.3.5 | mets à jour, redémarre |
| Mise à jour du script : *Length should be greater than 0* | version < 1.3.3 | **relance d'abord la régulation** (interrupteur *Régulation*), puis mets à jour |
| Batterie *en défaut* alors que l'application Zendure est OK | version < 1.3.6 | mets à jour, redémarre |
| Entités en `_2`, alerte *Les packages YAML sont encore chargés* | un package YAML est encore chargé | retire-le (étape 3 de la migration), redémarre, recharge l'intégration |
| Journal : *config_shelly is longer than 255* | le package `…_reglages.yaml` est encore chargé | retire-le |
| Statistiques de *commutations* suspendues après migration | version < 1.3.4 | mets à jour : elles reprennent d'elles-mêmes |
| **Script état** *Arrêté*, batterie à 0 W | script du Shelly arrêté ; l'intégration a appliqué le repli de sécurité | allume **Régulation**, ou bouton **Relancer le script** ; regarde la console du Shelly si ça recommence |
| **Script en erreur** | plantage signalé par le Shelly (message en attribut de *Script état*) | bouton **Redéployer le script** |
| **Script CPU** à 0 % en mode régulé | script tronqué | bouton **Redéployer le script** |
| La puissance **Réseau** ne suit pas la consommation de la maison | mauvaise pince | **Pince réseau lue** (voir [A5](#a5--vérifier-que-tout-est-en-place-5-minutes)) |
| Mise à jour du script en échec (alerte *Réparations*) | Shelly occupé ou injoignable | *Paramètres → Mises à jour → Script de régulation → Installer* |

**Journaux** : Paramètres → Système → Journaux, filtre `zendure_local_pilot`.
Pour plus de détails, ajoute à `configuration.yaml` puis redémarre :

```yaml
logger:
  logs:
    custom_components.zendure_local_pilot: debug
```

Pour signaler un problème, [ouvre une issue](https://github.com/zarzak12/zendure-local-pilot/issues)
avec ces journaux, ta version de firmware Shelly et la sortie de
`curl -s http://IP_BATTERIE/properties/report` (masque ton `sn`).

---

## Option B — Packages YAML

La méthode historique, toujours prise en charge : des fichiers YAML copiés
dans ta configuration. Elle demande l'intégration Shelly officielle et un
tableau de bord personnalisé à ton Shelly.

### Étape 4 — Ajouter le Shelly à Home Assistant

1. HA → **Paramètres → Appareils et services → Ajouter une intégration → Shelly**.
2. Saisis l'IP du Shelly notée à l'étape 2.
3. Une fois ajouté, **les composants virtuels doivent apparaître comme entités** :

   - `select.<shelly>_zendure_mode`
   - `number.<shelly>_zendure_decharge_max`
   - `number.<shelly>_zendure_charge_max`
   - `number.<shelly>_zendure_consigne_manuelle`
   - `number.<shelly>_zendure_buffer` (buffer **décharge**)
   - `number.<shelly>_zendure_buffer_charge`
   - `number.<shelly>_zendure_delai_veille`
   - `binary_sensor.<shelly>_zendure_en_veille`

   ❗ Si elles n'apparaissent pas : **Paramètres → Appareils et services → Shelly →
   ⋮ → Recharger**. Les composants virtuels ne sont découverts qu'au (re)chargement.

   ❗ Si une entité porte un nom incohérent (`..._zendure_decharge_max_2` au lieu de
   `..._zendure_buffer_charge`), c'est une séquelle d'une version antérieure du script
   qui créait des composants en double. Home Assistant fige l'`entity_id` au premier
   enregistrement : renommer le composant côté Shelly ne le change pas. Corrige-le en
   cliquant sur l'entité → ⚙️ → **ID d'entité**, et supprime au passage les entités
   restées *indisponibles* (`..._zendure_mode_2`, `..._zendure_charge_max_2`…) qui
   correspondent aux doublons désormais effacés.

4. **Note le préfixe exact** de tes entités : il dérive du nom de ton appareil,
   par exemple `shellypro3em_a1b2c3d4e5f6`.
   👉 Utilise **Outils de développement → États** et filtre sur `shellypro`.

   Tu n'auras pas à le recopier à la main : le script de personnalisation de
   l'étape 7 le récupère tout seul.

---

### Étape 5 — Installer les packages Home Assistant

1. **Active les packages** dans `configuration.yaml` (à ne faire qu'une fois) :

   ```yaml
   homeassistant:
     packages: !include_dir_named packages
   ```

2. Crée le dossier `packages/` à côté de `configuration.yaml` s'il n'existe pas.
3. Copie-y les **4 fichiers** du dossier `packages/` de ce dépôt.
4. **Exclus l'entité brute du recorder** (elle change toutes les 5 s et contient tout le JSON) :

   ```yaml
   recorder:
     exclude:
       entities:
         - sensor.zendure_solarflow4000mix_raw
   ```

5. Ne redémarre pas encore : passe à l'étape 6.

<details>
<summary>📁 Arborescence attendue</summary>

```
/config/
├── configuration.yaml
└── packages/
    ├── zendure_solarflow4000mix.yaml
    ├── zendure_solarflow4000mix_dashboard.yaml
    ├── zendure_solarflow4000mix_reglages.yaml
    └── zendure_solarflow4000mix_sante.yaml
```
</details>

---

### Étape 6 — Renseigner l'IP du Shelly et le canal de la pince

**Aucun fichier à modifier.** Les packages ne contiennent aucune adresse IP :
tout se règle depuis l'interface de Home Assistant.

1. **Outils de développement → Vérifier la configuration**, puis **redémarre
   Home Assistant**.
2. Ouvre **Paramètres → Appareils et services → Entités**, cherche
   `zendure_solarflow4000mix_shelly_ip` et saisis **l'IP de ton Shelly**
   (celle notée à l'étape 2).
   Tu pourras aussi le faire depuis l'onglet **Réglages** du dashboard,
   une fois celui-ci installé à l'étape 7.
3. Si ta pince d'arrivée générale **n'est pas la première**, règle
   `zendure_solarflow4000mix_em_canal` sur **1** ou **2** (numéro relevé à
   l'étape 2). Laisse **0** dans le cas le plus courant.

C'est tout. Tant que ce champ est vide, les capteurs restent *indisponibles* :
c'est normal.

> 💡 **Comment savoir si le canal est le bon ?** Compare
> `sensor.zendure_solarflow4000mix_reseau` à ce qu'affiche ton compteur. Si la
> valeur reste proche de 0 alors que la maison consomme, ou qu'elle ne suit
> qu'un seul appareil, c'est que tu lis la mauvaise pince. La console du script
> signale par ailleurs un canal inexistant :
> `ATTENTION, aucune mesure sur em1:N`.

| Donnée | Comment elle est obtenue |
|---|---|
| IP du **Shelly** | 👉 **la seule que tu saisis**, une fois pour toutes |
| Canal de la pince | 👉 à vérifier une fois à l'installation (0 par défaut) |
| IP de la **Zendure** | découverte par le script, transmise à HA automatiquement |
| Numéro de série de la batterie | lu et mémorisé au premier contact |
| Préfixe d'entités du Shelly | appliqué au dashboard par `tools/personnaliser.ps1` (étape 7) |

> ⚠️ Si ton script Shelly porte un **ID différent de 1**, c'est la seule
> retouche manuelle qui reste : remplace `Script.GetStatus?id=1` par ton ID
> dans `packages/zendure_solarflow4000mix.yaml`.

> 💡 La **puissance réseau** n'a rien à personnaliser : elle est lue directement dans le
> Shelly par REST (`GET /rpc/EM1.GetStatus?id=0`), donc indépendamment du nommage des
> entités de l'intégration Shelly. Si tu préfères utiliser ton entité de l'intégration,
> change la ligne `state:` du capteur *Zendure SolarFlow4000Mix reseau* dans
> `zendure_solarflow4000mix_dashboard.yaml`.

La **capacité de ta batterie** n'a rien à éditer : **8 kWh** (un pack de type 70)
est posé automatiquement à la première installation. Si tu as plusieurs packs,
change la valeur depuis l'onglet **Réglages** du dashboard, ou dans
*Paramètres → Appareils et services → Entités* →
`input_number.zendure_solarflow4000mix_capacite`.

Elle est ensuite **conservée d'un redémarrage à l'autre** et survit aux mises à
jour du projet.

---

### Étape 7 — Installer le dashboard

1. Installe **`apexcharts-card`** : HACS → Frontend → recherche `apexcharts-card` → Installer.
   Vide le cache du navigateur (Ctrl+F5) ensuite.
2. **Génère ta version du dashboard.** Le fichier du dépôt contient le marqueur
   `SHELLY_ID`, qui doit être remplacé par le préfixe d'entités de ton Shelly.
   Depuis la racine du dépôt, en remplaçant `IP_SHELLY` :

   ```powershell
   powershell -ExecutionPolicy Bypass -File tools\personnaliser.ps1 -Ip IP_SHELLY
   ```

   ```bash
   ./tools/personnaliser.sh IP_SHELLY        # Linux / macOS
   ```

   Le script interroge le Shelly, en déduit le préfixe, vérifie au passage que
   les 8 composants virtuels existent bien, et écrit
   **`dashboard/dashboard-perso.yaml`**.

   <details>
   <summary>Si tu as renommé l'appareil dans Home Assistant</summary>

   Home Assistant construit l'`entity_id` à partir du **nom** de l'appareil.
   Si tu l'as renommé, le préfixe deviné sera faux : impose-le avec

   ```powershell
   powershell -ExecutionPolicy Bypass -File tools\personnaliser.ps1 -Ip IP_SHELLY -Prefixe mon_prefixe
   ```

   Pour le connaître : **Outils de développement → États**, filtre `zendure_mode`.
   </details>

   <details>
   <summary>Ou à la main, sans script</summary>

   Ouvre `dashboard/dashboard HA.yaml` et remplace partout `SHELLY_ID` par ton
   préfixe (étape 4.4). Un simple rechercher/remplacer suffit : 21 occurrences.
   </details>

3. HA → ton tableau de bord → ✏️ **Modifier** → ⋮ → **Modifier en YAML** (« Raw configuration editor »).
4. Colle le contenu de **`dashboard/dashboard-perso.yaml`**.
   ⚠️ Si tu **ajoutes** ces vues à un dashboard existant, ne colle que le contenu de la clé
   `views:` à la suite de tes vues existantes.
5. Sauvegarde, puis va dans l'onglet **Réglages** du dashboard pour vérifier
   que l'IP du Shelly est bien renseignée.

---

## Utilisation

### Les 5 modes

| Mode | Comportement |
|---|---|
| **Arrêt** | Le script n'écrit plus rien (une dernière écriture à 0 W est faite en sortant des autres modes). Mode à utiliser pour tester manuellement avec `script.zendure_solarflow4000mix_set_power`. |
| **Autoconsommation** | Régulation complète : charge le surplus PV, décharge pour couvrir la consommation, pour maintenir le compteur réseau au plus près de 0. **Mode normal.** |
| **Charge seule** | Ne charge que le surplus, ne décharge jamais. Utile en heures creuses ou pour préserver le cycle. |
| **Décharge seule** | Couvre la consommation, ne charge jamais depuis le réseau. |
| **Manuel** | Applique la *consigne manuelle* telle quelle (**+ = décharge**, **− = charge**). Idéal pour tester ou pour piloter par tes propres automatisations. |

### Piloter depuis tes propres automatisations

Passe le mode en **Manuel** et écris la consigne :

```yaml
- action: select.select_option
  target: {entity_id: select.shellypro3em_XXXX_zendure_mode}
  data: {option: manuel}
- action: number.set_value
  target: {entity_id: number.shellypro3em_XXXX_zendure_consigne_manuelle}
  data: {value: -1500}      # charge à 1500 W
```

> 💡 Passe toujours par les **entités du Shelly**, jamais par
> `script.zendure_solarflow4000mix_set_power` tant qu'un mode régulé est actif :
> les deux se battraient pour écrire la consigne.

---

## Mettre à jour

> **Tu utilises l'intégration HACS ?** Rien de ce qui suit ne te concerne :
> mets à jour l'intégration dans HACS, redémarre Home Assistant, et le
> nouveau script est poussé tout seul sur le Shelly (ou d'un clic dans
> *Paramètres → Mises à jour*). Voir [A8 — Mettre à jour](#a8--mettre-à-jour).

Un correctif a été publié sur GitHub et le projet est déjà installé chez toi ?
Voici la marche à suivre. **Aucun de tes réglages n'est perdu** — la procédure
est conçue pour ça, et la section *Ce qui est conservé* plus bas explique
pourquoi.

### 1. Récupérer la nouvelle version

```bash
cd zendure-local-pilot
git pull
```

Pas de dépôt cloné ? Retélécharge le ZIP depuis GitHub (**Code → Download ZIP**).

> Si `git pull` refuse à cause de modifications locales :
> `git stash` → `git pull` → `git stash pop`.

### 2. Appliquer ce qui a changé

Trois briques indépendantes : **ne mets à jour que celles qui ont bougé**. Pour
le savoir : `git log --oneline --name-only -5`, ou les notes de version.

| Brique | Comment | Redémarrage HA |
|---|---|---|
| `scripts/*.js` | `tools\deploy_shelly.ps1 -Ip <IP_DU_SHELLY>` | non |
| `packages/*.yaml` | recopie les fichiers dans `config/packages/` | **oui** |
| `dashboard/*.yaml` | relance `tools\personnaliser.ps1`, puis recolle | non |

Le déployeur relit le script après téléversement et affiche `verification OK` :
tant que tu ne vois pas ce message, la mise à jour n'est pas allée au bout
(l'éditeur web du Shelly tronque silencieusement au-delà de ~7 ko — d'où cet
outil).

### 3. Vérifier

1. Console du script : `http://IP_DU_SHELLY/#/script/1` → la ligne
   `Zendure cfg: {...}` doit afficher **tes** valeurs, pas celles par défaut.
2. Le mode est toujours le tien (voir l'avertissement ci-dessous).
3. Le compteur réseau revient vers 0 en quelques secondes.

### Ce qui est conservé

| Réglage | Où il vit | Sort d'une mise à jour |
|---|---|---|
| IP et SN de la batterie, **canal de la pince**, période, gain, zone morte, hystérésis, seuil de réveil, délai d'inversion | KVS du Shelly | **intact** : au démarrage le script ne crée que les clés *absentes*, il n'écrase jamais une clé existante |
| Mode, décharge/charge max, consigne manuelle, buffers, délai de veille | composants virtuels du Shelly | **intacts** : le redéploiement réécrit leur *configuration*, pas leur *valeur* |
| Bornes SOC, capacité, cases du dashboard | helpers Home Assistant | **intacts** : HA restaure la dernière valeur au redémarrage |
| Historique, statistiques, tableau Énergie | base de données HA | **intact** tant que les `entity_id` ne changent pas |

Autrement dit : les fichiers du dépôt ne contiennent que de la *logique*, jamais
tes valeurs. C'est précisément ce qui rend la mise à jour sans risque.

> ⚠️ **Une seule exception : le mode peut revenir sur *Arrêt*.** Si une version
> renomme ou ajoute une option de mode, le script détecte que la valeur
> enregistrée n'existe plus dans la nouvelle liste et repasse sur **Arrêt** par
> sécurité — plutôt que de régler sur une option au hasard. Resélectionne
> simplement ton mode. C'est signalé dans les notes de version quand ça arrive.

> 📌 **Tu avais modifié le script à la main pour lire une autre pince ?**
> Jusqu'ici le canal `em1:0` était écrit en dur : changer de pince imposait
> d'éditer le code, et **chaque mise à jour effaçait la modification** — la
> régulation repartait silencieusement sur la pince 0, donc sur une mesure qui
> n'était pas celle du compteur général.
> C'est corrigé : le canal est devenu un réglage (`zendure_em`), stocké dans le
> KVS du Shelly. Après cette mise à jour, **remets ton numéro de pince une
> dernière fois** dans l'onglet *Réglages* → « Canal pince réseau ». Il survivra
> à toutes les mises à jour suivantes.

### Revenir en arrière

```bash
git log --oneline          # repère le commit qui marchait
git checkout <sha> -- scripts/ packages/
```

Puis redéploie. Tes réglages, eux, n'ont pas bougé.

---

## Référence des réglages

### Réglages courants (composants virtuels du Shelly, en RAM + persistés)

| Entité | Défaut | Description |
|---|---|---|
| Mode | Arrêt | voir ci-dessus |
| Décharge max | 4000 W | plafond de la consigne de décharge |
| Charge max | 4000 W | plafond de la consigne de charge |
| Consigne manuelle | 0 W | utilisée uniquement en mode Manuel |
| Buffer décharge | 20 W | cible sur la pince quand la batterie décharge, −200 à 200 W (− = injection tolérée) |
| Buffer charge | 20 W | idem quand la batterie charge le surplus |
| Délai de veille | 10 min | temps à 0 W avant veille profonde (**0 = jamais**) |

### Réglages avancés (KVS du Shelly, éditables depuis l'onglet Réglages)

| Clé KVS | Entité HA | Défaut | Bornes | Effet |
|---|---|---|---|---|
| — | `input_text.zendure_solarflow4000mix_shelly_ip` | *(vide)* | IPv4 | **IP du Shelly — la seule valeur à saisir** |
| `zendure_ip` | `input_text.zendure_solarflow4000mix_ip` | *(vide)* | IPv4 | IP de la Zendure, **trouvée et mise à jour automatiquement** |
| `zendure_sn` | — | *(vide)* | texte | numéro de série appris au 1er contact, sert à identifier la batterie |
| `zendure_em` | `..._em_canal` | 0 | 0–2 | **canal de la pince qui mesure l'arrivée générale** (voir étape 2) |
| `zendure_tick` | `..._tick` | 250 ms | 100–2000 | pas de scrutation de la pince (lecture mémoire, sans réseau) |
| `zendure_period` | `..._periode` | 1000 ms | 1–10 s | rafraîchissement de l'état Zendure en tâche de fond |
| `zendure_gain` | `..._gain` | 0.9 | 0.1–1 | amortissement (↑ = plus réactif, risque d'oscillation) |
| `zendure_dead` | `..._zone_morte` | 30 W | 0–200 | consigne forcée à 0 en dessous |
| `zendure_hyst` | `..._hysteresis` | 25 W | 0–200 | écart minimal avant réécriture |
| `zendure_wake` | `..._seuil_reveil` | 80 W | 0–500 | consigne nécessaire pour sortir de veille |
| `zendure_flip` | `..._delai_bascule` | 8 s | 0–300 | durée pendant laquelle une demande inverse doit se maintenir avant de basculer le relais charge ↔ décharge (0 = protection désactivée) |
| `zendure_flipw` | `..._seuil_bascule` | 100 W | 0–1000 | demande inverse à partir de laquelle la bascule se confirme en `zendure_flip` secondes ; en dessous, l'attente est cinq fois plus longue |
| `zendure_smooth` | `..._lissage` | 0 | 0–0,9 | lissage de la consigne (0 = désactivé). Essaie 0,7 si des appareils qui consomment par à-coups (induction, four) font osciller le compteur ; la réaction aux gros appareils ralentit de quelques secondes |

Ces clés sont relues **immédiatement** (événement `kvs_rev`) et, par sécurité, toutes les 60 s.

> ⚠️ **Ne descends pas `zendure_period` sous 1 seconde.** Mesuré sur matériel
> réel : à 500 ms le serveur HTTP de la Zendure sature et certaines réponses
> passent de ~90 ms à **près de 10 secondes**, ce qui fait clignoter tous les
> capteurs de Home Assistant en « Indisponible ». À 1 s le phénomène disparaît
> totalement — et sans aucune perte de réactivité, puisque la pince du Shelly
> ne produit de toute façon qu'une mesure par seconde. Le script refuse donc
> les valeurs inférieures.

Elles peuvent aussi se modifier à la main :

```
http://IP_SHELLY/rpc/KVS.Set?key="zendure_gain"&value=0.6
```

### Bornes SOC (curseurs synchronisés)

Deux entités **modifiables directement** dans l'onglet Réglages, alignées en permanence
sur ce que la Zendure applique réellement :

| Entité | Bornes | Propriété zenSDK |
|---|---|---|
| `input_number.zendure_solarflow4000mix_soc_min_consigne` | 0–50 % | `minSoc` (‰) |
| `input_number.zendure_solarflow4000mix_soc_max_consigne` | 70–100 % | `socSet` (‰) |

Fonctionnement :

- **Tu déplaces un curseur** → attente de 5 s (le temps de régler les deux) → écriture
  flash unique dans la Zendure, puis relecture immédiate.
- **La Zendure change de valeur** (app mobile, reset…) → les curseurs se réalignent seuls.
- Aucune écriture n'est envoyée si les valeurs sont déjà celles de l'appareil (anti-boucle),
  ni si `SOC max ≤ SOC min`.

Valeurs d'usine : **10 %** et **100 %**. Zendure déconseille de descendre sous 10 %.

### Réglages persistants de la Zendure (écriture flash)

Accessibles par des **scripts HA** dans l'onglet Réglages. Ils écrivent en `smartMode: 0`
(mémoire flash) puis repassent en `smartMode: 1`. **À utiliser ponctuellement**, jamais en boucle.

| Script | Propriété zenSDK | Valeurs |
|---|---|---|
| `zendure_solarflow4000mix_set_soc` | `minSoc`, `socSet` | en ‰ dans l'API (10 % → 100) |
| `zendure_solarflow4000mix_set_plafonds` | `inverseMaxPower`, `chargeMaxLimit` | W |
| `zendure_solarflow4000mix_set_injection_pv` | `gridReverse` | 0 Auto / 1 Autorisée / 2 Interdite |
| `zendure_solarflow4000mix_set_mode_secours` | `gridOffMode` | 0 Standard / 1 Économique / 2 Arrêt |
| `zendure_solarflow4000mix_set_power` | `acMode`,`outputLimit`,`inputLimit` | test manuel, **mode Arrêt uniquement** |

---

## Référence des entités

> 💡 **Les noms affichés portent ton modèle.** La batterie annonce son modèle dans le champ
> `product` ; le projet l'habille et le place devant chaque nom. Sur une 2400 AC+ tu lis
> donc « Zendure SolarFlow 2400 AC+ SOC », sans rien avoir à configurer. Un capteur dédié,
> `sensor.zendure_solarflow4000mix_modele`, expose ce libellé si tu veux t'en servir ailleurs.
>
> ⚠️ Seul le **nom affiché** est dynamique. Les **identifiants techniques** restent figés sur
> `zendure_solarflow4000mix_…` (voir [Préfixe des entités](#préfixe-des-entités)) : c'est ce
> qui garantit que tes historiques, tes statistiques et tes automatisations survivent aux
> mises à jour. Les listes ci-dessous donnent le suffixe de ces identifiants.
>
> Trois capteurs internes (`raw`, `reseau_shelly`, `config_shelly`) et le compteur
> `pack_N_energie_dc` gardent un nom statique : leur plateforme Home Assistant n'accepte pas
> de nom dynamique. Ils ne sont pas destinés à l'affichage.

<details>
<summary>📊 Capteurs principaux (cliquer pour dérouler)</summary>

**État batterie** — `soc`, `tension_batterie`, `autonomie_restante`, `temperature_boitier`,
`energie_disponible`, `energie_requise`, `temps_charge_restant`, `limite_soc`, `etat`

**Photovoltaïque** — `pv`, `pv_1`, `pv_2`, `passthrough_pv`, `pv_vers_batterie`,
`pv_vers_maison`, `energie_pv`, `pv_jour`

**Flux AC** — `sortie_maison`, `entree_reseau`, `sortie_secours`, `reseau`

**Flux batterie** — `charge_batterie`, `decharge_batterie`, `puissance_batterie_nette`,
`puissance`, `charge_dc`, `decharge_dc`

**Énergie** — `energie_chargee`, `energie_dechargee` (intégrations Riemann)

**Rendements** — `rendement_global`, `efficacite_charge`, `efficacite_decharge`
(mesure instantanée, indisponible hors conditions de mesure),
`rendement_charge`, `rendement_decharge` (dernière mesure connue, toujours
affichables), `efficacite_charge_24h`, `efficacite_decharge_24h` (moyennes 7 j)

**Consignes lues** — `limite_sortie`, `limite_charge`, `plafond_onduleur`, `plafond_charge`,
`soc_min`, `soc_max`, `mode_ac`, `injection_pv`, `mode_secours`, `stockage`

**Packs 1 à 4** — `pack_N_soc`, `pack_N_puissance`, `pack_N_tension`, `pack_N_courant`,
`pack_N_temperature`, `pack_N_ecart_cellules` (les packs absents restent indisponibles)

**Agrégats packs** — `ecart_soc_packs`, `ecart_cellules_max`, `temperature_pack_max`

**Diagnostic** — `nombre_de_packs`, `wifi_rssi`, `calibration`, `derniere_calibration`,
`jours_depuis_calibration`, `commutations_jour`, `zero_soutirage_jour`

**Binaires** — `erreur`, `reseau_connecte`, `zero_soutirage`, `script_shelly`

Tous préfixés par `sensor.zendure_solarflow4000mix_` (ou `binary_sensor.`).
</details>

### Échelles de l'API (utile pour créer tes propres capteurs)

| Propriété | Unité brute | Conversion |
|---|---|---|
| `BatVolt`, `packData[].totalVol` | centivolts | `/ 100` → V |
| `packData[].maxVol`, `minVol` | dizaines de mV | `× 10` → mV |
| `packData[].batcur` | dixièmes d'A, **int16 signé** | `(c-65536 si c>32767) / 10` → A |
| `hyperTmp`, `maxTemp` | dixièmes de K | `(v - 2731) / 10` → °C |
| `minSoc`, `socSet` | ‰ | `/ 10` → % |
| `socLimit` | drapeau | `% 16` : 0 normal, 1 SOC max, 2 SOC min |
| `smartMode` | — | 1 = écriture RAM, 0 = écriture flash |

---

## État de santé des batteries

L'API locale zenSDK **n'expose aucun indicateur de santé** : pas de SOH, pas de
capacité réelle, pas de compteur de cycles. Le package
`zendure_solarflow4000mix_sante.yaml` le **reconstruit par la mesure**.

### Comment c'est calculé

| Étape | Entité | Détail |
|---|---|---|
| 1. Puissance DC signée | `sensor.…_pack_N_puissance_dc` | `tension × courant` — `packData[].power` n'est qu'une magnitude, le sens vient du signe de `batcur` (+ charge / − décharge) |
| 2. Énergie échangée | `sensor.…_pack_N_energie_dc` | intégrale trapézoïdale de la puissance DC, en Wh. Compteur **net** : il monte en charge, descend en décharge |
| 3. Capacité réelle | `input_number.…_pack_N_capacite_estimee` | quand le SOC a bougé d'au moins **25 points** depuis le dernier repère : `énergie échangée ÷ ΔSOC × 100` |
| 4. Santé | `sensor.…_pack_N_sante` | `capacité réelle ÷ capacité nominale × 100` |

La **capacité nominale** (`sensor.…_pack_N_capacite_nominale`) est déduite
automatiquement de `packData[].packType` : **8,00 kWh** pour un pack de type 70
sur un `solarFlow4000MixPro`. `sensor.…_capacite_nominale_totale` en donne la
somme — pratique pour renseigner le curseur *Capacité totale* de l'onglet
Réglages.

### Ce qu'il faut savoir

- **C'est une estimation, pas une donnée constructeur.** Un écart de ± 5 % est normal.
- Il faut un **premier cycle d'au moins 25 points de SOC** pour obtenir une
  valeur. Tant qu'il n'y en a pas, `…_pack_N_sante` reste *indisponible* et le
  dashboard affiche une jauge **Mesure en cours**
  (`sensor.…_mesure_sante_progression`).
- Chaque nouvelle mesure ne pèse que **30 %** (lissage 70/30) : la valeur se
  stabilise au bout de quelques cycles.
- Une mesure **implausible** (hors de 40 %–130 % du nominal, typiquement après
  un redémarrage de HA en plein cycle) est **rejetée**, mais le repère est
  quand même replacé pour ne pas rester bloqué.
- La mesure fonctionne aussi bien en charge qu'en décharge, et même sur un
  cycle mixte : c'est le **bilan net** d'énergie rapporté au **bilan net** de SOC.
- Elle est faite **côté DC du pack**, donc elle ne dépend pas du rendement de
  l'onduleur. Seules les pertes internes du pack (~1-2 %) la biaisent
  légèrement vers le bas en charge et vers le haut en décharge.

### Repartir de zéro

Le script `script.zendure_solarflow4000mix_reset_sante` (bouton
**Réinitialiser l'estimation** dans la vue Santé) efface les capacités
mesurées et les repères. La mesure redémarre au prochain cycle.

> 💡 Un pack LFP neuf peut afficher **plus de 100 %** : les constructeurs
> laissent une marge. Ce qui compte, c'est la **dérive dans le temps**, pas la
> valeur absolue.

---

## Pour les experts

### Découverte automatique de la Zendure

Tu n'as **pas besoin de connaître l'IP de ta batterie**. Le script Shelly se
débrouille seul, et c'est lui qui fait autorité : Home Assistant lit l'IP dans
le KVS du Shelly (clé `zendure_ip`) au lieu de l'avoir en dur.

Pourquoi c'est nécessaire sur ce modèle : en Wi-Fi, la SolarFlow 4000 MIX PRO
utilise une **adresse MAC aléatoire**. Une réservation DHCP peut donc rester
sans effet et l'IP bouger toute seule, typiquement après une coupure. Le seul
identifiant réellement stable est le **numéro de série**.

Comment ça marche :

1. Au premier contact réussi, le script mémorise le **SN** de la batterie dans
   la clé KVS `zendure_sn`.
2. Si la Zendure ne répond plus **5 fois de suite**, le script balaie le réseau
   local — celui du Shelly lui-même, rien à configurer.
3. Il explore **en anneaux concentriques autour de la dernière IP connue**
   (`n`, `n+1`, `n−1`, `n+2`…). Un bail DHCP se déplaçant rarement loin, la
   batterie est en général retrouvée en quelques dizaines de secondes plutôt
   qu'en balayant bêtement les 254 adresses.
4. Il ne retient une adresse que si le **SN correspond** : sur un immeuble avec
   plusieurs Zendure, aucun risque de piloter celle du voisin.
5. L'IP trouvée est écrite dans `zendure_ip`. Home Assistant la récupère à son
   prochain rafraîchissement (≤ 60 s) et repart sans aucune intervention.

Le balayage ne coûte rien en fonctionnement normal : il ne démarre que lorsque
la batterie est injoignable, donc quand la régulation est de toute façon à
l'arrêt. Chaque adresse morte coûte ~2,6 s (résolution ARP), une seule requête
à la fois, pour ne pas saturer le Shelly.

En mode **Arrêt**, le script garde un contact espacé (~30 s) avec la batterie :
c'est ce qui permet de détecter un changement d'IP même au repos.

> Si tu préfères figer l'adresse malgré tout, branche la Zendure en **RJ45** :
> la MAC filaire est stable, la réservation DHCP fonctionne alors normalement.
> Bonus : la liaison est plus fiable que le Wi-Fi pour une boucle temps réel.

### Garde-fous : pourquoi la batterie ne peut plus rester figée

Point crucial à comprendre : **la Zendure n'a aucun chien de garde**. Tant que
personne ne lui écrit, elle maintient indéfiniment sa dernière consigne. Si la
boucle de régulation se tait alors qu'elle venait d'ordonner 3000 W de décharge,
la batterie continue de se vider dans le réseau — même en plein soleil.

Or toutes les écritures passent par deux verrous (`zBusy` pour les lectures,
`wBusy` pour les écritures) qui ne sont relâchés que dans le *rappel* d'un appel
HTTP. Si ce rappel n'arrive jamais — socket perdue, pile RPC du Shelly saturée —
le verrou reste armé pour toujours et le script cesse d'écrire **sans s'arrêter
pour autant** : il affiche encore `running: true`, ce qui rend la panne
particulièrement sournoise. Seul un redémarrage du script la débloquait.

Trois protections indépendantes évitent désormais ce scénario :

| Garde | Seuil | Rôle |
|---|---|---|
| Expiration des verrous | 20 s | un verrou plus vieux que le plus long appel (GET à 10 s) est tenu pour perdu et libéré d'office |
| Repli de sécurité | 90 s | sans un seul cycle de régulation abouti, la consigne est ramenée à **0 W** |
| Isolation des exceptions | — | une erreur dans le tick ou le poll est journalisée au lieu de tuer la boucle |

Le repli ne s'applique qu'aux modes régulés (ni **Arrêt**, ni **Manuel**, où une
consigne figée est voulue) et ne fait rien si la consigne est déjà à zéro. La
régulation normale reprend ensuite d'elle-même.

**Pourquoi le filet côté Home Assistant ne suffisait pas.** Une automatisation
remet déjà la consigne à 0 W quand `binary_sensor...._script_shelly` reste à
*off* pendant 30 s. Mais elle ne surveille que l'**arrêt** du script : dans la
panne décrite ci-dessus, le script affichait toujours `running: true`, le
binary_sensor restait à *on*, et ce filet ne se déclenchait jamais. Les deux
protections sont donc complémentaires — l'une couvre le script mort, l'autre le
script vivant mais muet. C'est aussi pour cela que le repli de 90 s vit **dans
le Shelly** : il doit fonctionner même si Home Assistant est éteint.

> Vérifié sur matériel : consigne de 150 W maintenue **3 minutes sans aucune
> écriture**, sans retour à zéro. La batterie ne se protège pas toute seule —
> c'est au pilote de le faire.

Tu verras ces messages dans la console du script si un incident survient :

```
Zendure: verrou de lecture perdu, libéré d'office
Zendure: aucune régulation depuis 90 s - repli de sécurité à 0 W
```

Leur apparition occasionnelle n'est pas inquiétante — c'est le système qui se
rattrape. En revanche, s'ils reviennent toutes les quelques minutes, c'est que
la Zendure répond mal : augmente `zendure_period` (voir la note sur la
saturation de son serveur HTTP).

### Ajouter un pack batterie

Rien à coder : les packs **2 à 4** sont déjà déclarés et apparaissent
automatiquement dès que la batterie les remonte dans `packData`. Les cartes du
dashboard sont conditionnelles, et trois agrégats (`ecart_soc_packs`,
`ecart_cellules_max`, `temperature_pack_max`) s'affichent dès le 2ᵉ pack.

Seule action manuelle : **ajuster `input_number.zendure_solarflow4000mix_capacite`**
(8 kWh par pack de type 70). La détection automatique ne joue qu'à la première
installation, pour ne jamais écraser un réglage voulu : elle ne se redéclenchera
donc pas toute seule quand tu ajouteras un pack. Reporte simplement la valeur de
`sensor.zendure_solarflow4000mix_capacite_nominale_totale`, qui, elle, suit le
nombre de packs en temps réel.

Pour un 5ᵉ pack, duplique un bloc `pack_4_*` en
remplaçant `packData[3]` par `packData[4]`.

### Utiliser un Shelly en triphasé

> ℹ️ Si tes trois pinces sont en **monophasé** et que tu veux simplement lire une
> autre pince que la première, **ne touche pas au code** : règle le canal
> `zendure_em` (voir [Référence des réglages](#référence-des-réglages)).
> La modification ci-dessous ne concerne que le profil **triphasé**, où les
> trois phases sont totalisées par le Shelly.

Dans le script JS, remplace :

```js
function gridPower() {
    let s = Shelly.getComponentStatus("em1", CFG.em);
    return (s && typeof s.act_power === "number") ? s.act_power : null;
}
```

par :

```js
function gridPower() {
    let s = Shelly.getComponentStatus("em", 0);
    return (s && typeof s.total_act_power === "number") ? s.total_act_power : null;
}
```

Pense aussi à adapter le capteur REST de `packages/zendure_solarflow4000mix_dashboard.yaml`
(`EM1.GetStatus` → `EM.GetStatus`, `act_power` → `total_act_power`), sans quoi
l'affichage de Home Assistant ne correspondra plus à ce qui est régulé.

⚠️ Pertinent uniquement si ton compteur d'énergie est en **compensation triphasée**.
Sinon, il vaut mieux réguler sur la phase où la Zendure est raccordée.

### Utiliser un autre compteur qu'un Shelly

Il faut un appareil exécutant du **Shelly Script (mJS)**. Si ton compteur est ailleurs,
deux options :

1. garder un Shelly (même sans pince) comme « cerveau » et lui faire lire ton compteur par HTTP ;
2. déplacer la régulation dans HA — plus simple, mais tu perds l'indépendance vis-à-vis de HA.

### Régler le gain

- Oscillations (la consigne fait le yo-yo) → **baisse le gain** (0,5) et/ou **augmente la période**.
- Réaction trop lente aux gros appareils → **monte le gain** (0,9) et **baisse la période** (1 s).
- Écritures trop fréquentes (usure) → **monte l'hystérésis** (50 W).
- Battements charge/décharge → **monte le délai de bascule** (30–60 s) et/ou le **seuil de bascule** (200–300 W).

### Debug du script

Passe `let DEBUG = false;` à `true` en tête du script : chaque cycle logue
mode, puissance réseau, consigne, consigne actuelle et état de veille dans la console Shelly.

### Sécurité intégrée

`binary_sensor.zendure_solarflow4000mix_script_shelly` interroge
`Script.GetStatus?id=1` toutes les 15 s. Si le script est arrêté pendant 30 s,
une automatisation remet la Zendure à 0 W — sinon elle garderait indéfiniment
sa dernière consigne.

---

## Dépannage

| Symptôme | Cause probable | Solution |
|---|---|---|
| `sensor.zendure_solarflow4000mix_raw` indisponible | API locale non activée / Shelly injoignable | refais l'étape 1, teste avec `curl`. L'IP de la Zendure, elle, se corrige seule (≤ 60 s) |
| Les entités `select`/`number` du Shelly n'existent pas | composants virtuels non découverts | recharge l'intégration Shelly (⋮ → Recharger) |
| `Zendure write err` dans la console Shelly | IP incorrecte, Zendure en veille Wi-Fi | vérifie `zendure_ip` en KVS, la qualité du Wi-Fi (`rssi`) |
| La régulation ne démarre pas | mode sur **Arrêt** | passe en **Autoconsommation** |
| Le mode est vide / invalide après une mise à jour du script | option renommée dans le script | le script détecte la valeur obsolète et remet **Arrêt** au démarrage : resélectionne ton mode |
| La batterie ne charge/décharge pas malgré une consigne | SOC en butée | regarde `sensor..._limite_soc` et les bornes SOC |
| Rien ne se passe après 10 min d'inactivité | **veille profonde** normale | la consigne doit dépasser le *seuil de réveil* |
| Les curseurs SOC reviennent à leur ancienne valeur | la Zendure a refusé l'écriture (SOC max ≤ SOC min, ou API injoignable) | vérifie que max > min, puis les logs HA du script `set_soc` |
| Erreur `default_entity_id` au démarrage de HA | HA trop ancien | supprime toutes les lignes `default_entity_id:` des packages |
| Les graphiques sont vides / « Custom element not found » | `apexcharts-card` absent | installe-le via HACS et vide le cache (Ctrl+F5) |
| Badge « Contrôle » à « — », courbe Réseau plate à 0, zéro soutirage à 0 h | `sensor.zendure_solarflow4000mix_reseau` indisponible | teste `curl http://IP_SHELLY/rpc/EM1.GetStatus?id=0` ; vérifie l'IP du Shelly et le profil **monophasé** |
| La puissance réseau ne correspond pas au compteur (reste à ~0, ou ne suit qu'un appareil) | **mauvais canal de pince** : l'arrivée générale est sur `em1:1` ou `em1:2`, pas sur `em1:0` | règle « Canal pince réseau » dans l'onglet *Réglages* ; compare les trois via `curl http://IP_SHELLY/rpc/EM1.GetStatus?id=0` (puis `1`, `2`) |
| Le signe de la puissance réseau est inversé | pince à l'envers | retourne la pince, ou bascule `reverse` du canal : `http://IP_SHELLY/rpc/EM1.SetConfig?id=0&config={"reverse":true}` |
| Rendement > 100 % ou aberrant | mesure pendant une phase PV | ces capteurs ne sont valides que PV < 20 W ; regarde les moyennes 7 j |
| « Rendement charge/décharge » à *Indisponible* | aucune mesure valide depuis le démarrage de HA | normal tant que la batterie n'a pas chargé/déchargé au moins une fois à plus de 50 W sans PV ; la valeur est ensuite conservée |
| Une entité Shelly porte un nom incohérent (`..._zendure_decharge_max_2`) | l'`entity_id` a été figé lors d'un doublon créé par une ancienne version du script | renomme l'entité dans HA (⚙️ → ID d'entité) ; le renommage côté Shelly ne suffit pas |
| Réglages avancés non synchronisés au démarrage | HA a lu avant que le Shelly réponde | déclenche manuellement l'automatisation « réglages ← Shelly » |
| **La batterie reste figée sur une consigne** (ex. 3000 W en décharge alors que le compteur injecte), et tout rentre dans l'ordre en relançant le script | un rappel HTTP perdu laissait un verrou armé définitivement ; la Zendure, qui n'a aucun chien de garde, conservait la dernière consigne | **corrigé** : verrous à expiration + repli automatique à 0 W au bout de 90 s sans régulation. Mets le script à jour (étape 3) |

**Logs utiles**

```
Console du script Shelly          → http://IP_SHELLY/#/script/1
État de la config KVS             → http://IP_SHELLY/rpc/KVS.GetMany?match=zendure_*
État du script                    → http://IP_SHELLY/rpc/Script.GetStatus?id=1
Rapport brut Zendure              → http://IP_ZENDURE/properties/report
```

---

## Sécurité et avertissements

- ⚠️ **Écritures flash** : toute écriture avec `smartMode: 0` est persistante mais **use la
  mémoire flash**. Les scripts de réglages sont conçus pour un usage ponctuel — ne les mets
  jamais dans une automatisation périodique.
- ⚠️ **Plafonds** : au-delà de **3680 W** de sortie, vérifie que la ligne d'alimentation
  supporte le courant (circuit dédié 20 A). Le respect des normes électriques locales est
  de ta responsabilité.
- ⚠️ **SOC minimum** : Zendure déconseille de descendre sous **10 %**.
- ⚠️ **Injection réseau** : selon ton contrat et ta réglementation, l'injection peut être
  interdite ou nécessiter une déclaration. Utilise `gridReverse = 2` (Interdite) si besoin.
- ⚠️ **Aucune garantie** : ce projet est fourni tel quel, sans affiliation avec Zendure ni
  Shelly. Tu l'utilises à tes risques.

---

## Licence

Ce projet est distribué sous licence **MIT** — voir le fichier [LICENSE](LICENSE).

En résumé : tu peux l'utiliser, le modifier, le redistribuer et même le vendre, y compris
dans un projet propriétaire, à la seule condition de conserver la mention de copyright et
le texte de la licence. En contrepartie, le logiciel est fourni **sans aucune garantie** et
l'auteur ne peut être tenu responsable des dommages — ce qui mérite d'être gardé à l'esprit
quand on pilote une batterie raccordée au réseau électrique.

Ce dépôt n'est affilié ni à **Zendure** ni à **Shelly**. Les marques citées appartiennent à
leurs propriétaires respectifs.

---

## Crédits

- [Zendure/zenSDK](https://github.com/Zendure/zenSDK) — API locale et documentation des propriétés
- [Gielz1986/Zendure-HA-zenSDK](https://github.com/Gielz1986/Zendure-HA-zenSDK) — inspiration
  du dashboard et des capteurs dérivés
- [Zendure/Zendure-HA](https://github.com/Zendure/Zendure-HA) — l'intégration officielle,
  à privilégier dès qu'elle supportera la 4000 MIX PRO
  ([issue #1550](https://github.com/Zendure/Zendure-HA/issues/1550))

Testé sur : **SolarFlow 4000 MIX PRO** (`solarFlow4000MixPro`, version 3), 1 pack 8 kWh type 70,
**Shelly Pro 3EM** en profil monophasé.

Contributions bienvenues — ouvre une *issue* avec ton retour `GET /properties/report`
(pense à masquer ton `sn`) si tu utilises une variante matérielle différente.
