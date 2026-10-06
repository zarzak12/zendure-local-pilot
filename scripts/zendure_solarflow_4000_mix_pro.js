// Zendure zenSDK — régulation locale Shelly -> batterie, réglages depuis HA
// Shelly Pro 3EM en profil monophasé (+ soutirage / − injection)
// Compatible avec tous les appareils Zendure exposant l'API HTTP locale zenSDK :
// SolarFlow 4000 MIX PRO / MIX AC+, 3000 MIX AC+, 2400 AC / AC+ / Pro,
// 1600 AC+, 800 / 800 Plus / 800 Pro. Ils partagent le même contrat d'API
// (/properties/report et /properties/write, mêmes noms de propriétés).
// Les plafonds de puissance ne sont pas codés en dur : ils sont lus dans le
// rapport de la batterie (inverseMaxPower / chargeMaxLimit).
//
// NON compatible avec le Hyper 2000, qui n'expose aucun serveur HTTP local
// (pilotage cloud/MQTT uniquement, confirmé par Zendure : zenSDK issues 18 et 61).
// Shelly Pro 3EM en profil monophasé (+ soutirage / − injection)
//
// La pince qui mesure le point de livraison n'est pas forcément la première :
// selon le câblage, c'est em1:0, em1:1 ou em1:2. Le canal est donc un réglage
// (zendure_em), et non une valeur figée dans le code — sinon chaque mise à jour
// du script écraserait le choix de l'utilisateur.
//
// Paramètres avancés stockés dans le KVS du Shelly (modifiables depuis HA ou par URL) :
//   zendure_ip, zendure_sn, zendure_em (0-2), zendure_tick (ms), zendure_period (ms),
//   zendure_gain, zendure_dead (W), zendure_hyst (W), zendure_wake (W), zendure_flip (s)
// Exemple : http://IP_SHELLY/rpc/KVS.Set?key="zendure_gain"&value=0.6
//
// L'IP de la Zendure n'a pas besoin d'être exacte : elle sert de point de départ.
// Si la batterie devient injoignable (bail DHCP déplacé), le script la recherche
// seul sur le réseau local et met zendure_ip à jour — voir startScan/scanNext.
//
// Latence : la pince ne produit une mesure que ~1 fois par seconde, c'est le
// plancher. Le tick (rapide, simple lecture mémoire, sans réseau) guette
// l'arrivée d'une mesure pour écrire aussitôt, au lieu d'attendre le prochain
// battement d'une horloge désynchronisée. Le poll rafraîchit l'état de la
// Zendure en tâche de fond pour le sortir du chemin critique.
//
// zendure_period ne doit PAS descendre sous 1000 ms : mesuré, le serveur HTTP
// de la Zendure sature et certaines réponses passent alors de ~90 ms à près de
// 10 s, ce qui fait décrocher les capteurs de Home Assistant. À 1000 ms la
// queue de latence disparaît complètement, sans perte de réactivité (la pince
// ne fournit de toute façon qu'une mesure par seconde).

// L'IP de la Zendure est volontairement vide : le script la découvre seul sur
// le réseau du Shelly et l'enregistre dans le KVS. Rien à saisir nulle part.
// La renseigner ici fait juste gagner les ~30 s de recherche au tout 1er
// démarrage. Idem pour zendure_sn, appris au premier contact.
let DEFAULTS = { zendure_ip: "", zendure_sn: "", zendure_em: 0, zendure_tick: 250, zendure_period: 1000,
    zendure_gain: 0.9, zendure_dead: 30, zendure_hyst: 25, zendure_wake: 80, zendure_flip: 8 };
let CFG = { ip: DEFAULTS.zendure_ip, sn: DEFAULTS.zendure_sn, em: DEFAULTS.zendure_em,
    tick: DEFAULTS.zendure_tick, period: DEFAULTS.zendure_period,
    gain: DEFAULTS.zendure_gain, dead: DEFAULTS.zendure_dead, hyst: DEFAULTS.zendure_hyst,
    wake: DEFAULTS.zendure_wake, flip: DEFAULTS.zendure_flip };
let DEBUG = false;   // true pour tracer chaque cycle dans la console
let lastMode = null, tickTmr = null, pollTmr = null;
let zeroSince = null, standby = false;
let flipSince = null, flipDir = 0;   // pause d'observation avant inversion charge <-> décharge

// ---- Instantané de l'état Zendure ----
// Z.gen suit writeGen : un instantané antérieur à la dernière écriture décrit un
// état révolu. Z.tick date l'instantané en nombre de ticks, ce qui permet de
// vérifier qu'il est contemporain de la mesure de la pince — la consigne
// acNow + (g - buf) * gain n'a de sens que si acNow et g décrivent le même instant.
let Z = null, ticks = 0, idleTicks = 0;

// ---- Recherche automatique de la batterie sur le réseau ----
// zFail compte les lectures ratées d'affilée ; au-delà de SCAN_AFTER on part
// en exploration. Le SN est l'unique identifiant stable de la Zendure (sa MAC
// est aléatoire), il est appris tout seul au premier contact réussi.
let zFail = 0, scanning = false, scanStep = 0, scanBase = 0, scanPrefix = "", idlePoll = 0;
let SCAN_AFTER = 5;
let zBusy = false, wBusy = false, writeGen = 0;

// ---- Garde-fous ----
// Toutes les écritures passent par zBusy/wBusy. Ces verrous ne sont relâchés
// que dans le rappel d'un appel HTTP : si un rappel n'arrive jamais (socket
// perdue, pile RPC du Shelly saturée), le verrou reste armé pour toujours et le
// script cesse d'écrire *sans s'arrêter* — il affiche encore running: true.
// Or la Zendure conserve indéfiniment sa dernière consigne : un blocage survenu
// en pleine décharge la laisse vider la batterie dans le réseau. D'où deux
// filets indépendants :
//   LOCK_MAX : au-delà, un verrou est tenu pour perdu et libéré d'office
//   FAILSAFE : sans cycle de régulation abouti, on force un retour à 0 W
let zBusyAt = 0, wBusyAt = 0, lastOk = 0;
let LOCK_MAX = 20, FAILSAFE = 90;

function zLock() { zBusy = true; zBusyAt = uptime(); }
function wLock() { wBusy = true; wBusyAt = uptime(); }
let lastG = null, wantReg = false, wantG = 0, wantMode = "arret";

// ---- Limites matérielles, déclarées par la batterie ----
// Chaque modèle a ses propres plafonds (2400 W sur un SolarFlow 2400 AC,
// 3000 W sur un 4000 MIX PRO, 800 W sur un SolarFlow 800...). Plutôt que de
// les coder en dur par modèle, on lit ce que la batterie annonce :
//   inverseMaxPower -> plafond de décharge      chargeMaxLimit -> plafond de charge
// Ces deux valeurs sont aussi réglables par l'utilisateur ; les respecter
// revient donc à ne jamais demander une puissance que la batterie refusera.
// hwD/hwC à 0 = pas encore connu : on n'impose alors aucune limite.
let hwD = 0, hwC = 0, appD = 0, appC = 0;

function plausible(v) {
    return typeof v === "number" && v > 0 && v <= 10000;
}

// Aligne les curseurs du Shelly sur les plafonds réels de la batterie.
// Number.SetConfig écrit en flash : on ne le fait que si la limite a bougé,
// jamais à chaque cycle.
function syncLimits() {
    if (appD === hwD && appC === hwC) return;
    appD = hwD; appC = hwC;
    let d = hwD > 0 ? hwD : 4000, c = hwC > 0 ? hwC : 4000;
    VC[1].config.max = d;
    VC[2].config.max = c;
    VC[3].config.min = -c;
    VC[3].config.max = d;
    print("Zendure: plafonds matériels - décharge", d, "W, charge", c, "W");
    for (let i = 1; i <= 3; i++) {
        Shelly.call(rpc(VC[i].type, "SetConfig"), { id: VC[i].config.id, config: VC[i].config });
    }
}

function readLimits(p) {
    let d = plausible(p.inverseMaxPower) ? p.inverseMaxPower : hwD;
    let c = plausible(p.chargeMaxLimit) ? p.chargeMaxLimit : hwC;
    if (d === hwD && c === hwC) return;
    hwD = d; hwC = c;
    syncLimits();
}

// ---- Composants virtuels (réglages courants, visibles dans HA) ----
// key : clé du composant, précalculée (mJS ne concatène pas nombre + chaîne).
// Elle est réajustée au démarrage si le Shelly attribue un autre id.
// Index : 0 mode, 1 décharge max, 2 charge max, 3 consigne, 4 buffer décharge,
//         5 délai veille, 6 en veille, 7 buffer charge.
let VC = [
    { type: "enum", key: "enum:200", config: { id: 200, name: "Zendure mode", persisted: true, default_value: "arret",
            options: ["arret", "autoconso", "charge_seule", "decharge_seule", "manuel"],
            meta: { ui: { view: "dropdown", titles: { arret: "Arrêt", autoconso: "Autoconsommation",
                        charge_seule: "Charge seule", decharge_seule: "Décharge seule", manuel: "Manuel" } } } } },
    { type: "number", key: "number:200", config: { id: 200, name: "Zendure décharge max", persisted: true, min: 0, max: 4000,
            default_value: 4000, meta: { ui: { view: "slider", unit: "W", step: 50 } } } },
    { type: "number", key: "number:201", config: { id: 201, name: "Zendure charge max", persisted: true, min: 0, max: 4000,
            default_value: 4000, meta: { ui: { view: "slider", unit: "W", step: 50 } } } },
    { type: "number", key: "number:202", config: { id: 202, name: "Zendure consigne manuelle", persisted: true, min: -4000, max: 4000,
            default_value: 0, meta: { ui: { view: "field", unit: "W", step: 10 } } } },
    { type: "number", key: "number:203", config: { id: 203, name: "Zendure buffer", persisted: true, min: -200, max: 200,
            default_value: 20, meta: { ui: { view: "field", unit: "W", step: 5 } } } },
    { type: "number", key: "number:204", config: { id: 204, name: "Zendure délai veille", persisted: true, min: 0, max: 60,
            default_value: 10, meta: { ui: { view: "field", unit: "min", step: 1 } } } },
    { type: "boolean", key: "boolean:200", config: { id: 200, name: "Zendure en veille", persisted: false, default_value: false,
            meta: { ui: { view: "label", titles: ["Active", "Veille"] } } } },
    // Ajouté en fin de liste : les clés des composants existants ne bougent pas
    { type: "number", key: "number:205", config: { id: 205, name: "Zendure buffer charge", persisted: true, min: -200, max: 200,
            default_value: 20, meta: { ui: { view: "field", unit: "W", step: 5 } } } }
];

// ---- Configuration KVS ----
function num(v, def, lo, hi) {
    let n = Number(v);
    if (v === null || v === undefined || isNaN(n)) return def;
    return Math.max(lo, Math.min(hi, n));
}

function validIp(v) {
    if (typeof v !== "string") return false;
    let parts = v.split(".");
    if (parts.length !== 4) return false;
    for (let i = 0; i < 4; i++) {
        let n = Number(parts[i]);
        if (parts[i] === "" || isNaN(n) || n < 0 || n > 255) return false;
    }
    return true;
}

function kvsToMap(res) {
    let m = {};
    if (!res || !res.items) return m;
    let it = res.items;
    if (Array.isArray(it)) { for (let i = 0; i < it.length; i++) m[it[i].key] = it[i].value; }
    else { for (let k in it) m[k] = it[k].value; }
    return m;
}

function applyCfg(m) {
    let oldTick = CFG.tick, oldPeriod = CFG.period, oldEm = CFG.em;
    CFG.ip     = validIp(m.zendure_ip) ? m.zendure_ip : CFG.ip;
    CFG.sn     = (typeof m.zendure_sn === "string") ? m.zendure_sn : CFG.sn;
    // Canal de la pince réseau : 0, 1 ou 2 en profil monophasé.
    CFG.em     = Math.round(num(m.zendure_em, CFG.em, 0, 2));
    CFG.tick   = Math.round(num(m.zendure_tick, CFG.tick, 100, 2000));
    // Plancher à 1000 ms : en dessous, le serveur HTTP de la Zendure sature
    // (réponses jusqu'à ~10 s au lieu de 90 ms). Mesuré, pas supposé.
    CFG.period = Math.round(num(m.zendure_period, CFG.period, 1000, 10000));
    CFG.gain   = num(m.zendure_gain, CFG.gain, 0.1, 1);
    CFG.dead   = num(m.zendure_dead, CFG.dead, 0, 200);
    CFG.hyst   = num(m.zendure_hyst, CFG.hyst, 0, 200);
    CFG.wake   = num(m.zendure_wake, CFG.wake, 0, 500);
    CFG.flip   = Math.round(num(m.zendure_flip, CFG.flip, 0, 300));
    if (tickTmr !== null && (CFG.tick !== oldTick || CFG.period !== oldPeriod)) startTimers();
    // lastG sert à repérer l'arrivée d'une mesure fraîche ; après un changement
    // de canal il décrit une autre pince, et une valeur identique par hasard
    // ferait passer la nouvelle mesure pour une répétition.
    if (CFG.em !== oldEm) lastG = null;
    checkEm();
    print("Zendure cfg:", JSON.stringify(CFG));
}

// Un canal inexistant (mauvais numéro, ou Shelly en profil triphasé) ne produit
// aucune mesure : la régulation resterait muette sans rien signaler.
function checkEm() {
    if (gridPower() !== null) return;
    print("Zendure: ATTENTION, aucune mesure sur em1:" + JSON.stringify(CFG.em) +
          " - verifie le canal de la pince (zendure_em) et le profil monophase du Shelly");
}

function seed(keys, i, done) {
    if (i >= keys.length) { done(); return; }
    Shelly.call("KVS.Set", { key: keys[i], value: DEFAULTS[keys[i]] }, function () { seed(keys, i + 1, done); });
}

function loadCfg(done) {
    Shelly.call("KVS.GetMany", { match: "zendure_*" }, function (res, e) {
        let m = (e === 0) ? kvsToMap(res) : {};
        let missing = [];
        for (let k in DEFAULTS) if (m[k] === undefined) missing.push(k);
        seed(missing, 0, function () {
            for (let j = 0; j < missing.length; j++) m[missing[j]] = DEFAULTS[missing[j]];
            applyCfg(m);
            if (done) done();
        });
    });
}

// ---- Démarrage ----
function startTimers() {
    if (tickTmr !== null) Timer.clear(tickTmr);
    if (pollTmr !== null) Timer.clear(pollTmr);
    tickTmr = Timer.set(CFG.tick, true, tick);
    pollTmr = Timer.set(CFG.period, true, poll);
}

// Nom de la classe RPC d'un composant virtuel (Enum.SetConfig, Number.Set, ...)
function rpc(type, method) {
    let cls = type === "enum" ? "Enum" : type === "number" ? "Number" : type === "boolean" ? "Boolean" : "Text";
    return cls + "." + method;
}

// Si la valeur persistée d'un enum ne fait plus partie des options (renommage
// d'un mode), on la ramène à la valeur par défaut.
function fixEnum(v, done) {
    if (v.type !== "enum") { done(); return; }
    let cur = val(v.key, null);
    let ok = false;
    for (let j = 0; j < v.config.options.length; j++) if (v.config.options[j] === cur) ok = true;
    if (ok) { done(); return; }
    print("Zendure: mode obsolète ->", v.config.default_value);
    Shelly.call("Enum.Set", { id: v.config.id, value: v.config.default_value }, function () { done(); });
}

function setup(i) {
    if (i >= VC.length) { cleanup(ready); return; }
    let v = VC[i];
    // SetConfig d'abord : Virtual.Add ignore l'id demandé et créerait un doublon
    // à chaque démarrage, jusqu'au plafond de composants virtuels du Shelly.
    Shelly.call(rpc(v.type, "SetConfig"), { id: v.config.id, config: v.config }, function (r, e) {
        if (e === 0) { fixEnum(v, function () { setup(i + 1); }); return; }
        Shelly.call("Virtual.Add", { type: v.type, config: v.config }, function (r2, e2) {
            if (e2 !== 0) print("Zendure: création impossible pour", v.config.name, "err", e2);
            else if (r2 && typeof r2.id === "number" && r2.id !== v.config.id) {
                // JSON.stringify : seule façon en mJS d'obtenir la chaîne d'un nombre
                v.key = v.type + ":" + JSON.stringify(r2.id);
                v.config.id = r2.id;
                print("Zendure:", v.config.name, "créé sous", v.key);
            }
            setup(i + 1);
        });
    });
}

// ---- Nettoyage des doublons ----
// Les versions précédentes appelaient Virtual.Add en premier : chaque
// redémarrage ajoutait une copie des réglages jusqu'à saturer l'appareil.
function known(key) {
    for (let i = 0; i < VC.length; i++) if (VC[i].key === key) return true;
    return false;
}

function delDup(list, i, done) {
    if (i >= list.length) { done(); return; }
    print("Zendure: suppression du doublon", list[i]);
    Shelly.call("Virtual.Delete", { key: list[i] }, function () { delDup(list, i + 1, done); });
}

// Pagination : on collecte tout avant de supprimer, sinon les offsets glissent.
function scan(offset, acc, done) {
    Shelly.call("Shelly.GetComponents", { dynamic_only: true, offset: offset }, function (r, e) {
        if (e !== 0 || !r || !r.components) { done(acc); return; }
        let n = r.components.length;
        for (let i = 0; i < n; i++) {
            let c = r.components[i];
            let nm = (c.config && typeof c.config.name === "string") ? c.config.name : "";
            if (nm.slice(0, 7) === "Zendure" && !known(c.key)) acc.push(c.key);
        }
        if (n > 0 && offset + n < r.total) scan(offset + n, acc, done);
        else done(acc);
    });
}

function cleanup(done) {
    scan(0, [], function (dup) { delDup(dup, 0, done); });
}

function ready() {
    loadCfg(function () {
        setStandby(false, true);
        // Sans cette amorce, un redémarrage du script sur un Shelly en service
        // depuis des heures verrait uptime() - lastOk dépasser FAILSAFE dès le
        // premier poll et déclencherait un repli à 0 W injustifié.
        lastOk = uptime();
        startTimers();
        // Aucune IP connue (1re installation) : on cherche la batterie tout de
        // suite plutôt que d'attendre 5 échecs sur une adresse vide.
        if (!validIp(CFG.ip)) startScan();
        else fetchZ();   // instantané initial, pour que la première mesure soit exploitable
        // Rechargement de la config dès qu'une clé KVS change (+ filet toutes les 60 s)
        Shelly.addStatusHandler(function (ev) {
            if (ev.component === "sys" && ev.delta && typeof ev.delta.kvs_rev === "number") loadCfg(null);
        });
        Timer.set(60000, true, function () { loadCfg(null); });
        print("Zendure: prêt");
    });
}

// ---- Utilitaires ----
function val(key, def) {
    let s = Shelly.getComponentStatus(key);
    return (s && s.value !== undefined && s.value !== null) ? s.value : def;
}

// Un statut système momentanément indisponible ne doit pas lever d'exception :
// elle remonterait jusqu'au timer et interromprait la boucle de régulation.
let lastUp = 0;
function uptime() {
    let s = Shelly.getComponentStatus("sys");
    if (s && typeof s.uptime === "number") lastUp = s.uptime;
    return lastUp;
}

function gridPower() {
    let s = Shelly.getComponentStatus("em1", CFG.em);
    return (s && typeof s.act_power === "number") ? s.act_power : null;
}

function setStandby(v, force) {
    if (standby === v && !force) return;
    standby = v;
    Shelly.call("Boolean.Set", { id: VC[6].config.id, value: v });
    print(v ? "Zendure: veille profonde" : "Zendure: active");
}

function writeProps(sn, props, mode) {
    wLock();
    writeGen++;   // périme l'instantané courant et toute lecture déjà en vol
    Shelly.call("HTTP.POST", {
        url: "http://" + CFG.ip + "/properties/write",
        content_type: "application/json",
        body: JSON.stringify({ sn: sn, properties: props }),
        timeout: 3
    }, function (r, e) {
        wBusy = false;
        if (e === 0) { lastMode = mode; setStandby(props.smartMode === 0, false); }
        else print("Zendure write err", e);
        fetchZ();   // resynchronise l'instantané sur la consigne qu'on vient d'envoyer
    });
}

// acMode n'est renvoyé que si le sens change réellement : le réécrire à chaque
// ajustement sollicite le relais de l'onduleur pour rien.
function write(sn, p, mode, acCur) {
    let props;
    if (p > 0) {
        props = { smartMode: 1, outputLimit: p, inputLimit: 0 };
        if (acCur !== 2) props.acMode = 2;
    } else if (p < 0) {
        props = { smartMode: 1, inputLimit: -p, outputLimit: 0 };
        if (acCur !== 1) props.acMode = 1;
    } else {
        props = { smartMode: 1, outputLimit: 0, inputLimit: 0 };
    }
    writeProps(sn, props, mode);
}

// ---- Boucle ----
// Deux horloges. Le tick est rapide mais gratuit (gridPower() lit la mémoire du
// Shelly, sans réseau) : il sert uniquement à repérer l'instant où la pince
// publie une nouvelle mesure, pour écrire dans la foulée. Le poll entretient en
// tâche de fond l'instantané de la Zendure, qui sort ainsi du chemin critique.
function tick() {
    // Une exception qui remonte jusqu'au timer interrompt la boucle : le script
    // resterait "running" sans plus rien écrire, et la Zendure garderait sa
    // consigne. On isole donc le corps du tick.
    try { tickBody(); } catch (e) { print("Zendure: erreur dans le tick -", e); }
}

function tickBody() {
    ticks++;
    // gridPower() d'abord : la grande majorité des ticks n'a rien à faire, et
    // sortir tôt évite la lecture du composant virtuel de mode à chaque passage.
    let g = gridPower();
    if (g === null) return;
    let nouvelle = (lastG === null || g !== lastG);
    if (nouvelle) lastG = g;
    idleTicks++;
    // On régule à l'arrivée d'une mesure, et au minimum toutes les CFG.period ms
    // pour que la veille et les changements de mode restent évalués au repos.
    if (!nouvelle && idleTicks * CFG.tick < CFG.period) return;
    idleTicks = 0;
    let mode = val(VC[0].key, "arret");
    if (mode === "arret" && lastMode === "arret") return;
    regulate(g, mode);
}

// Un instantané n'est exploitable que s'il est postérieur à la dernière écriture
// et quasi contemporain de la mesure : acNow et g doivent décrire le même
// instant, sinon la consigne calculée est fausse et la convergence ralentit.
function zFresh() {
    if (Z === null || Z.gen !== writeGen) return false;
    return (ticks - Z.tick) * CFG.tick <= 600;
}

function regulate(g, mode) {
    if (wBusy) return;
    if (zFresh()) { decide(g, mode, Z); return; }
    // Instantané absent ou périmé : repli sur une lecture en ligne, on paie les
    // ~90 ms du GET dans ce cycle plutôt que de calculer sur un état dépassé.
    wantG = g; wantMode = mode; wantReg = true;
    fetchZ();
}

function fetchZ() {
    if (zBusy) return;
    if (scanning) { wantReg = false; return; }
    if (!validIp(CFG.ip)) { wantReg = false; onZFail(); return; }
    zLock();
    let gen = writeGen;
    Shelly.call("HTTP.GET", { url: "http://" + CFG.ip + "/properties/report", timeout: 3 }, function (r, e) {
        zBusy = false;
        if (e !== 0 || !r || r.code !== 200) { wantReg = false; onZFail(); return; }
        let d, p;
        try { d = JSON.parse(r.body); p = d.properties; } catch (err) { d = null; }
        if (!d || !p) { wantReg = false; onZFail(); print("Zendure: réponse illisible"); return; }
        zFail = 0;
        // Premier contact : on mémorise le SN, seule clé stable pour la retrouver
        if (CFG.sn === "" && d.sn) { CFG.sn = d.sn; Shelly.call("KVS.Set", { key: "zendure_sn", value: d.sn }); }
        Z = { sn: d.sn, cur: p.outputLimit - p.inputLimit,
              acNow: p.outputHomePower - p.gridInputPower, acMode: p.acMode,
              lim: p.socLimit % 16, gen: gen, tick: ticks };
        readLimits(p);
        if (wantReg) {
            wantReg = false;
            // Une écriture partie pendant la lecture rendrait cet instantané
            // caduc : mieux vaut laisser le prochain tick relancer le cycle.
            if (gen === writeGen) decide(wantG, wantMode, Z);
        }
    });
}

// Un verrou encore armé après LOCK_MAX secondes ne peut plus correspondre à un
// appel en cours (le plus long est un GET à 10 s) : son rappel a été perdu. On
// le libère, quitte à tolérer brièvement deux appels concurrents — très
// préférable à un arrêt définitif des écritures.
function unstick() {
    let now = uptime();
    if (zBusy && now - zBusyAt > LOCK_MAX) {
        zBusy = false;
        print("Zendure: verrou de lecture perdu, libéré d'office");
    }
    if (wBusy && now - wBusyAt > LOCK_MAX) {
        wBusy = false;
        print("Zendure: verrou d'écriture perdu, libéré d'office");
    }
}

// Dernier rempart. La Zendure n'a aucun chien de garde : tant que personne ne
// lui écrit, elle maintient sa consigne, fût-elle de 3000 W en décharge alors
// que le compteur injecte. Si plus aucun cycle de régulation n'aboutit, on la
// ramène à 0 W ; la régulation normale repartira d'elle-même ensuite.
function failsafe() {
    if (FAILSAFE <= 0 || wBusy || scanning) return;
    if (Z === null || !Z.sn) return;
    let mode = val(VC[0].key, "arret");
    if (mode === "arret" || mode === "manuel") return;
    if (uptime() - lastOk < FAILSAFE) return;
    lastOk = uptime();                       // on ne réessaie qu'au prochain cycle
    if (Z.cur === 0) return;                 // déjà neutre : rien de dangereux à corriger
    print("Zendure: aucune régulation depuis", FAILSAFE, "s - repli de sécurité à 0 W");
    writeProps(Z.sn, { smartMode: 1, outputLimit: 0, inputLimit: 0 }, mode);
}

function poll() {
    try { pollBody(); } catch (e) { print("Zendure: erreur dans le poll -", e); }
}

function pollBody() {
    unstick();
    failsafe();
    if (scanning) { scanNext(); return; }
    let mode = val(VC[0].key, "arret");
    // En arrêt il n'y a rien à réguler, mais on garde un contact espacé : c'est
    // ce qui permet de repérer un changement d'IP même batterie au repos.
    if (mode === "arret" && lastMode === "arret" && Z !== null) {
        idlePoll++;
        if (idlePoll * CFG.period < 30000) return;
    }
    idlePoll = 0;
    fetchZ();
}

// ---- Découverte automatique ----
// Déclenchée seulement quand la Zendure ne répond plus : la régulation est de
// toute façon à l'arrêt, le balayage ne prend donc rien à personne.
function onZFail() {
    zFail++;
    if (zFail < SCAN_AFTER) return;
    if (!validIp(CFG.ip)) { startScan(); return; }
    if (zBusy || scanning) return;
    // Avant de balayer le réseau, on redonne sa chance à l'adresse connue avec
    // un délai généreux. La Zendure peut être simplement lente (son serveur
    // HTTP sature si on l'interroge trop souvent) plutôt qu'avoir déménagé :
    // sans cette confirmation, une lenteur passagère déclencherait un balayage
    // inutile qui interromprait la régulation.
    zLock();
    Shelly.call("HTTP.GET", { url: "http://" + CFG.ip + "/properties/report", timeout: 10 }, function (r, e) {
        zBusy = false;
        if (e === 0 && r && r.code === 200) {
            zFail = 0;
            print("Zendure: lente mais toujours sur", CFG.ip, "- pas de recherche");
            return;
        }
        startScan();
    });
}

function startScan() {
    if (scanning) return;
    // On repart du réseau du Shelly lui-même : aucune saisie n'est nécessaire.
    let st = Shelly.getComponentStatus("wifi");
    let self = (st && st.sta_ip) ? st.sta_ip : null;
    if (!self) { st = Shelly.getComponentStatus("eth"); self = (st && st.ip) ? st.ip : null; }
    if (!validIp(self)) { print("Zendure: réseau du Shelly inconnu, recherche impossible"); return; }
    let p = self.split(".");
    scanPrefix = p[0] + "." + p[1] + "." + p[2] + ".";
    // Point de départ : la dernière IP connue si elle est sur le même réseau,
    // sinon celle du Shelly. Un bail DHCP se déplace rarement loin.
    let q = validIp(CFG.ip) ? CFG.ip.split(".") : p;
    scanBase = (q[0] + "." + q[1] + "." + q[2] + ".") === scanPrefix ? Number(q[3]) : Number(p[3]);
    scanStep = 0; scanning = true;
    print("Zendure injoignable : recherche sur", scanPrefix + "0/24");
}

function scanNext() {
    if (zBusy) return;
    // Anneaux concentriques autour de scanBase : n, n+1, n-1, n+2, n-2 ...
    let host = -1;
    while (scanStep < 512) {
        let s = scanStep;
        scanStep++;
        let off = (s % 2 === 0) ? s / 2 : -(s + 1) / 2;
        let h = scanBase + off;
        if (h >= 1 && h <= 254) { host = h; break; }
    }
    if (host < 0) {
        scanning = false; scanStep = 0; zFail = 0;
        print("Zendure: recherche infructueuse, nouvelle tentative plus tard");
        return;
    }
    let ip = scanPrefix + JSON.stringify(host);
    zLock();
    Shelly.call("HTTP.GET", { url: "http://" + ip + "/properties/report", timeout: 2 }, function (r, e) {
        zBusy = false;
        if (!scanning || e !== 0 || !r || r.code !== 200) return;
        let d = null;
        try { d = JSON.parse(r.body); } catch (err) { d = null; }
        if (!d || !d.sn || !d.properties) return;
        // Un SN connu doit correspondre : sur un parc à plusieurs batteries on
        // ne veut surtout pas s'accrocher à celle du voisin de palier.
        if (CFG.sn !== "" && d.sn !== CFG.sn) return;
        scanning = false; scanStep = 0; zFail = 0;
        CFG.ip = ip;
        Shelly.call("KVS.Set", { key: "zendure_ip", value: ip });
        if (CFG.sn === "") { CFG.sn = d.sn; Shelly.call("KVS.Set", { key: "zendure_sn", value: d.sn }); }
        print("Zendure retrouvée sur", ip, "- SN", d.sn);
    });
}

function decide(g, mode, z) {
    if (wBusy) return;
    // Battement de cœur surveillé par failsafe(). Les sorties anticipées qui
    // suivent (hystérésis, veille, bascule) sont des décisions légitimes : le
    // cycle a abouti, même sans écriture.
    lastOk = uptime();
    let regulated = (mode === "autoconso" || mode === "charge_seule" || mode === "decharge_seule");
    let cur = z.cur;
    let dMax = val(VC[1].key, 4000), cMax = val(VC[2].key, 4000);
    // Le plafond annoncé par la batterie prime : demander plus serait refusé,
    // et ferait croire à la régulation qu'elle dispose d'une marge inexistante.
    if (hwD > 0) dMax = Math.min(dMax, hwD);
    if (hwC > 0) cMax = Math.min(cMax, hwC);
    let t;

    if (mode === "arret") t = 0;
    else if (mode === "manuel") t = val(VC[3].key, 0);
    else {
        let acNow = z.acNow;
        // Le buffer appliqué dépend du sens du besoin brut : on veut pouvoir
        // viser un léger soutirage en décharge et une légère injection en charge.
        let buf = (acNow + g >= 0) ? val(VC[4].key, 20) : val(VC[7].key, 20);
        t = acNow + (g - buf) * CFG.gain;
        if (mode === "charge_seule") t = Math.min(t, 0);
        if (mode === "decharge_seule") t = Math.max(t, 0);
        // SOC en butée : décharger à SOC min (2) ou charger à SOC max (1) ne sert à rien
        if ((t > 0 && z.lim === 2) || (t < 0 && z.lim === 1)) t = 0;
    }

    t = Math.round(Math.max(-cMax, Math.min(dMax, t)));
    if (mode !== "manuel" && Math.abs(t) < CFG.dead) t = 0;

    // ---- Temporisation d'inversion charge <-> décharge ----
    // Avant d'inverser le sens, on repasse à 0 W et on observe le réseau
    // pendant CFG.flip secondes. La consigne étant recalculée à vide, on
    // applique ensuite le besoin réel — plus de battement charge/décharge.
    if (regulated && CFG.flip > 0) {
        let curDir = cur > 0 ? 1 : (cur < 0 ? -1 : 0);
        let newDir = t > 0 ? 1 : (t < 0 ? -1 : 0);
        if (flipSince !== null) {
            // fenêtre d'observation bornée : on maintient 0 W jusqu'au bout
            if (uptime() - flipSince >= CFG.flip) { flipSince = null; flipDir = 0; }
            else { flipDir = newDir; t = 0; }
        } else if (newDir !== 0 && curDir !== 0 && newDir !== curDir) {
            flipDir = newDir; flipSince = uptime(); t = 0;
            print("Zendure: inversion demandée, observation", CFG.flip, "s à 0 W");
        }
    } else { flipSince = null; flipDir = 0; }

    if (DEBUG) print("mode", mode, "| réseau", g, "W | consigne", t, "W | actuelle", cur,
        "W | veille", standby, "| bascule", flipSince === null ? "-" : flipDir);

    // ---- Veille profonde (modes régulés uniquement) ----
    if (regulated) {
        if (standby) {
            if (Math.abs(t) < CFG.wake) { lastMode = mode; return; }
            zeroSince = null;
        } else if (t === 0 && cur === 0 && flipSince === null) {
            let delay = val(VC[5].key, 10) * 60;
            let now = uptime();
            if (zeroSince === null) zeroSince = now;
            if (delay > 0 && now - zeroSince >= delay) {
                zeroSince = null;
                writeProps(z.sn, { smartMode: 0, outputLimit: 0, inputLimit: 0 }, mode);
                return;
            }
        } else zeroSince = null;
    } else zeroSince = null;

    if (mode !== "arret" && Math.abs(t - cur) <= CFG.hyst) { lastMode = mode; return; }
    write(z.sn, t, mode, z.acMode);
}

setup(0);