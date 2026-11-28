// ennui. — application (JavaScript vanilla, module ES, aucune dépendance externe).
// Librairies locales (frontend/vendor) chargées par index.html : lucide, noUiSlider, Swiper, gsap.
import { renderAvatar, avatarDe, avatarAleatoire, avatarsPrets, STYLES, FONDS, nomValeur } from "./avatar.js";

const { lucide, noUiSlider, Swiper, gsap } = window;
const MOUVEMENT = !window.matchMedia("(prefers-reduced-motion: reduce)").matches && Boolean(gsap);

/** Icône Lucide en SVG (stroke 1.5), générée depuis les données de lucide.min.js : pas de passe DOM. */
const cacheIcones = {};
function icone(nom, taille = 20, classe = "") {
  if (!(nom in cacheIcones)) {
    const pascal = nom.replace(/(^|-)([a-z0-9])/g, (_, __, c) => c.toUpperCase());
    let noeud = lucide?.icons?.[pascal];
    if (noeud && noeud[0] === "svg") noeud = noeud[2];  // format ["svg", attributs, enfants] selon la version
    cacheIcones[nom] = Array.isArray(noeud) ? noeud.map(([balise, attrs]) =>
      `<${balise} ${Object.entries(attrs || {}).map(([k, v]) => `${k}="${v}"`).join(" ")}/>`).join("") : "";
  }
  return `<svg class="icone ${classe}" width="${taille}" height="${taille}" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${cacheIcones[nom]}</svg>`;
}

// ------------------------------------------------------------------ //
// Constantes                                                           //
// ------------------------------------------------------------------ //
const PREFIXE = "ennui.v4";
const FUSEAU = "Europe/Paris";
const NOMS_PLATEFORMES = { 8: "Netflix", 119: "Prime Video", 337: "Disney+", 381: "Canal+", 234: "Arte", 350: "Apple TV+" };
const GENRES_FR = {
  "Sci-Fi": "Science-Fiction", Thriller: "Thriller", Drama: "Drame", Comedy: "Comédie", Animation: "Animation",
  Documentary: "Documentaire", Horror: "Horreur", Action: "Action", Romance: "Romance", Crime: "Policier",
  Fantasy: "Fantastique", Adventure: "Aventure", Mystery: "Mystère", Children: "Jeunesse", Musical: "Musical",
  War: "Guerre", Western: "Western", "Film-Noir": "Film noir",
};
const TEINTES = {
  "Sci-Fi": 212, Thriller: 0, Drama: 28, Comedy: 44, Animation: 275, Documentary: 160, Horror: 340,
  Action: 14, Romance: 325, Crime: 222, Fantasy: 258, Adventure: 120, Mystery: 245, Children: 190,
  Musical: 300, War: 80, Western: 35,
};
const ICONES_CATEGORIE = {
  culture: "landmark", ecrans: "clapperboard",
  soirees: "disc-3", cinema: "clapperboard", expo: "landmark", scene: "drama", nature: "trees", rencontres: "messages-square",
  livres: "book-open", series: "tv", jeux: "gamepad-2", cuisine: "chef-hat", creatif: "palette", lecture: "book-open",
  cafe: "coffee", sport: "bike",
};
const NOMS_CONSOLES = { pc: "PC", mac: "Mac", switch: "Switch", playstation: "PlayStation", xbox: "Xbox", mobile: "Mobile" };
const TYPES = {
  film: { nom: "Film", icone: "film", vu: "Déjà vu", collectif: "Watch-party" },
  serie: { nom: "Série", icone: "tv", vu: "Déjà vu", collectif: "Watch-party" },
  livre: { nom: "Livre", icone: "book-open", vu: "Déjà lu", collectif: "Club de lecture" },
  jeu: { nom: "Jeu vidéo", icone: "gamepad-2", vu: "Déjà joué", collectif: "Session de jeu" },
  sortie: { nom: "Sortie", icone: "ticket", vu: "", collectif: "Sortie à plusieurs" },
};
const ONGLETS = [
  { id: "pour-vous", nom: "Pour vous", icone: "sparkles" },
  { id: "ecrans", nom: "Chez soi", icone: "sofa" },
  { id: "sorties", nom: "Sorties", icone: "ticket" },
  { id: "profil", nom: "Profil", icone: "user" },
];

// ------------------------------------------------------------------ //
// État, comptes et persistance                                         //
// ------------------------------------------------------------------ //
const PREFS_INITIALES = () => ({ ville: null, rayon: 15, budget: "tous", categories: [], genres: [], plateformes: [], consoles: [], modeJeu: "tous", themes: [] });
// Anciennes envies -> nouvelles (Films & Séries, Lecture, Jeux vidéo, Sorties culturelles, Soirées & Concerts, Balades & Nature)
const MIGRATION_ENVIES = { series: "ecrans", livres: "lecture", cinema: "culture", expo: "culture", scene: "culture" };
const ETAT_INITIAL = () => ({
  uid: null, prenom: "",
  prefs: PREFS_INITIALES(),
  horizon: "semaine",
  dejaVus: [],          // [{ id, titre, type }]
  envies: [],           // « Mes envies » : [{ id, titre, type, affiche, ... }] mis de côté
  avatar: null,         // personnage DiceBear ; null = déduit du prénom
  code: null,           // code public « Prénom#123 » (amis, connexion)
  dispo: "indispo",     // humeur du moment (copie locale du serveur)
  decouverte: 0.3,
  energie: null,        // questionnaire : "cocon" | "mixte" | "dehors"
  onglet: "pour-vous",
  ecrans: "tout",
});
let etat = ETAT_INITIAL();
let CONFIG = null;
let LOGO = "ofk?";  // remplacé au démarrage par le logotype vectoriel (icons/logo-ofk.svg)
let donnees = {};
let controleur = null;
let cleQuota = null;
let feuille = null;     // feuille collaborative ouverte : { oeuvre, plans }
let agenda = null;      // état de la synchronisation de l'agenda
let social = { moi: null, amis: [], suggestions: [] };
// Synchronisation temps réel (/api/sync) : version, plans connus { id -> participants }, plans signalés « Nouveau » { id -> oeuvre_id }
let synchro = { v: null, connus: null, enCours: false };
const nouveaux = new Map();  // code, statut « Dispo », amis (serveur)
let etape = "bienvenue";
let modeAuth = "creer";  // écran d'authentification : "creer" (inscription) | "connexion" // "bienvenue" à chaque ouverture, puis "questionnaire" (sans compte) ou "application"

const stock = {
  lire(cle, defaut) { try { return JSON.parse(localStorage.getItem(`${PREFIXE}.${cle}`)) ?? defaut; } catch (_) { return defaut; } },
  ecrire(cle, valeur) { try { localStorage.setItem(`${PREFIXE}.${cle}`, JSON.stringify(valeur)); } catch (_) { /* indisponible */ } },
  retirer(cle) { try { localStorage.removeItem(`${PREFIXE}.${cle}`); } catch (_) { /* indisponible */ } },
};
const comptes = () => stock.lire("comptes", []);       // [{ id, prenom }] connus sur cet appareil

function sauvegarder() {
  if (!etat.uid) return;
  stock.ecrire(`etat.${etat.uid}`, etat);
  stock.ecrire("actif", etat.uid);
  synchroniserProfil();
}
function restaurer() {
  const uid = stock.lire("actif", null);
  const local = uid ? stock.lire(`etat.${uid}`, null) : null;
  if (local) etat = { ...ETAT_INITIAL(), ...local, prefs: { ...PREFS_INITIALES(), ...(local.prefs || {}) } };
  etat.prefs.categories = [...new Set(etat.prefs.categories.map((c) => MIGRATION_ENVIES[c] || c))];
  if (!["tout", "ecrans", "livre", "jeu"].includes(etat.ecrans)) etat.ecrans = "tout";
  etat.decouverte = versDecouverte(cran());
  if (etat.prefs.modeJeu === "coop") etat.prefs.modeJeu = "multi";  // Co-op fusionné dans Multijoueur
  if (!Array.isArray(etat.envies)) etat.envies = [];
  if (!["liste", "carte"].includes(etat.vueSorties)) etat.vueSorties = "liste";
}

/** Profil côté serveur (SQLite) : prénom, ville et préférences, pour changer d'appareil ou de compte. */
const synchroniserProfil = debounce(() => {
  if (!etat.uid) return;
  const { ville, ...prefs } = etat.prefs;
  api("/api/utilisateurs/moi", { prenom: etat.prenom, ville, prefs: { ...prefs, horizon: etat.horizon, dejaVus: etat.dejaVus, envies: etat.envies } }, undefined, "PUT")
    .catch(() => { /* hors ligne : le navigateur reste la référence */ });
}, 800);

// ------------------------------------------------------------------ //
// Utilitaires                                                          //
// ------------------------------------------------------------------ //
const $ = (sel) => document.querySelector(sel);
const haut = () => { window.scrollTo(0, 0); $("#app").scrollTo(0, 0); };
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
function debounce(fn, ms) { let m; return (...a) => { clearTimeout(m); m = setTimeout(() => fn(...a), ms); }; }

async function api(chemin, corps, signal, methode) {
  const entetes = { "Content-Type": "application/json" };
  if (etat.uid) entetes["X-Utilisateur"] = etat.uid;
  const options = corps === undefined ? { headers: entetes, signal, method: methode || "GET" }
    : { method: methode || "POST", headers: entetes, body: JSON.stringify(corps), signal };
  const r = await fetch(chemin, options);
  if (!r.ok) {
    let detail = `${r.status}`;
    try { const d = await r.json(); detail = typeof d.detail === "string" ? d.detail : detail; } catch (_) { /* rien */ }
    const erreur = new Error(detail);
    erreur.status = r.status;  // 401 = compte inconnu ; 5xx / réseau = serveur momentanément indisponible
    throw erreur;
  }
  return r.json();
}

let minuteurToast;
function toast(message) {
  const t = $("#toast");
  t.textContent = message;
  t.classList.add("visible");
  clearTimeout(minuteurToast);
  minuteurToast = setTimeout(() => t.classList.remove("visible"), 2400);
}

const genresFr = (o, n = 2) => (o.genres_fr || (o.genres || []).map((g) => GENRES_FR[g] || g)).slice(0, n).join(", ");
const estMulti = (o) => (o.modes || []).some((m) => m === "coop" || m === "multi");
const nbPepites = () => Math.round(etat.decouverte * 10);
const km = (x) => `${x < 10 ? x.toFixed(1) : Math.round(x)} km`.replace(".", ",");
const chiffre = (t) => `<span class="chiffre">${esc(t)}</span>`;
const nomVille = () => etat.prefs.ville?.nom || "Partout en France";
const lienSur = (t) => /^https:\/\/[^\s"'<>]+$/.test(t || "");

// ------------------------------------------------------------------ //
// Dates (toujours dans le fuseau Europe/Paris)                         //
// ------------------------------------------------------------------ //
const jourParis = (d) => d.toLocaleDateString("fr-CA", { timeZone: FUSEAU });
const heureParis = (d) => d.toLocaleTimeString("fr-FR", { timeZone: FUSEAU, hour: "2-digit", minute: "2-digit" }).replace(":", "h");
const heureNum = (d) => Number(new Intl.DateTimeFormat("fr-FR", { timeZone: FUSEAU, hour: "numeric", hourCycle: "h23" })
  .formatToParts(d).find((p) => p.type === "hour").value);
const dateCourte = (d) => {
  const t = d.toLocaleDateString("fr-FR", { timeZone: FUSEAU, weekday: "short", day: "numeric", month: "short" });
  return t.charAt(0).toUpperCase() + t.slice(1);
};
const dateDuJour = () => new Date().toLocaleDateString("fr-FR", { timeZone: FUSEAU, weekday: "long", day: "numeric", month: "long" });

/** « Ce soir · 20h30 », « Demain · 14h00 », « Sam. 28 nov. · 20h30 ». */
function libelleInstant(debut, { avecHeure = true } = {}) {
  const maintenant = new Date();
  const auj = jourParis(maintenant);
  const demain = jourParis(new Date(maintenant.getTime() + 864e5));
  const heure = avecHeure ? ` · ${heureParis(debut)}` : "";
  if (jourParis(debut) === auj) return (heureNum(debut) >= 17 && avecHeure ? "Ce soir" : "Aujourd'hui") + heure;
  if (jourParis(debut) === demain) return `Demain${heure}`;
  return `${dateCourte(debut)}${heure}`;
}

function libelleDate(o) {
  if (!o.prochaine) return "";
  const debut = new Date(o.prochaine.debut);
  const fin = new Date(o.prochaine.fin);
  if (debut <= new Date()) {
    return jourParis(fin) === jourParis(new Date()) ? `En cours · jusqu'à ${heureParis(fin)}`
      : `En cours · jusqu'au ${fin.toLocaleDateString("fr-FR", { timeZone: FUSEAU, day: "numeric", month: "long" })}`;
  }
  return libelleInstant(debut, { avecHeure: heureParis(debut) !== "00h00" });
}

/** Valeur pour <input type="datetime-local"> en heure de Paris. */
function valeurLocale(d) {
  const p = Object.fromEntries(new Intl.DateTimeFormat("fr-FR", { timeZone: FUSEAU, year: "numeric", month: "2-digit",
    day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).formatToParts(d).map((x) => [x.type, x.value]));
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`;
}

function ilYa(iso) {
  if (!iso) return "jamais";
  const min = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (min < 1) return "à l'instant";
  if (min < 60) return `il y a ${min} min`;
  const h = Math.round(min / 60);
  return h < 24 ? `il y a ${h} h` : `il y a ${Math.round(h / 24)} j`;
}

const tarif = (o) => o.tarif || "Tarif non précisé";

// ------------------------------------------------------------------ //
// Briques visuelles                                                    //
// ------------------------------------------------------------------ //
function tagDecouverte(o) {
  if (o.origine !== "decouverte") return "";
  return o.etiquette === "hors-piste" ? `<span class="tag tag-hors-piste">Hors piste</span>` : `<span class="tag tag-pepite">Pépite</span>`;
}

function affiche(o) {
  const teinte = TEINTES[o.genres?.[0]] ?? 230;
  const fond = `background: linear-gradient(160deg, hsl(${teinte} 32% 24%) 0%, hsl(${teinte} 20% 12%) 55%, #141417 100%)`;
  const typo = `<div class="visuel-typo" style="${fond}">
      <span class="surtitre">${TYPES[o.type]?.nom || "Film"}</span>
      <div><strong>${esc(o.titre)}</strong><div class="annee">${esc(o.auteur || o.annee || "")}</div></div>
    </div>`;
  const srcset = o.affiche_mini ? ` srcset="${esc(o.affiche_mini)} 210w, ${esc(o.affiche)} 680w" sizes="180px"` : "";
  const img = o.affiche ? `<img src="${esc(o.affiche_mini || o.affiche)}"${srcset} alt="" loading="lazy" decoding="async" onerror="this.remove()">` : "";
  const format = o.type === "jeu" ? "paysage" : "affiche";  // affiches et livres 2/3, jeux 16/10
  return `<div class="visuel ${format}" data-action="ouvrir-plans" data-id="${esc(o.id)}">${typo}${img}<span class="voile"></span>${tagDecouverte(o)}${boutonSauver(o)}</div>`;
}

function visuelSortie(o, format = "paysage") {
  const fond = `background: radial-gradient(120% 90% at 20% 0%, #26262C 0%, #141417 70%)`;
  const img = o.affiche ? `<img src="${esc(o.affiche)}" alt="" loading="lazy" decoding="async" onerror="this.remove()">` : "";
  const credit = o.affiche && o.credit_image ? `<span class="credit">© ${esc(o.credit_image)}</span>` : "";
  return `<div class="visuel ${format}" style="${fond}" data-action="ouvrir-plans" data-id="${esc(o.id)}">
      <div class="visuel-icone">${icone(ICONES_CATEGORIE[o.categorie] || "compass", 40)}</div>${img}<span class="voile"></span>${credit}${tagDecouverte(o)}${o.id ? boutonSauver(o) : ""}
    </div>`;
}

function lignePlateformes(o) {
  if (!o.plateformes?.length) return "";  // rien à afficher plutôt qu'un avertissement
  return `<div class="plateformes">${o.plateformes.filter((p) => p in NOMS_PLATEFORMES).map((p) =>
    `<span class="plateforme ${etat.prefs.plateformes.includes(p) ? "possedee" : ""}">${esc(NOMS_PLATEFORMES[p])}</span>`).join("")}</div>`;
}

/** « Avec Chloé, Théo et 2 autres » (soi-même affiché « toi »). */
function avecQui(plan) {
  const noms = plan.participants.map((n, i) => (plan.je_participe && n === etat.prenom && i === plan.participants.indexOf(etat.prenom) ? "toi" : n));
  if (noms.length <= 2) return `Avec ${noms.join(" et ")}`;
  return `Avec ${noms.slice(0, 2).join(", ")} et ${noms.length - 2} autre${noms.length > 3 ? "s" : ""}`;
}

// ---------------- Billetterie (OpenAgenda : statut, inscription, conditions publiées) ----------------
const BILLETS = { libre: ["Entrée libre", "door-open"], reservation: ["Sur réservation", "ticket"], complet: ["Complet", "circle-slash"] };
const tagBillet = (o) => {
  const b = BILLETS[o.billetterie];
  return b ? `<span class="tag-billet billet-${o.billetterie}">${icone(b[1], 12)}${b[0]}</span>` : "";
};
function lienReservation(o) {
  if (o.billetterie === "complet") return "";
  if (o.reservation_url && lienSur(o.reservation_url)) {
    return `<a class="bouton-ligne bouton-accent" href="${esc(o.reservation_url)}" target="_blank" rel="noopener noreferrer">${icone("external-link", 14)}Réserver</a>`;
  }
  if (o.reservation_tel) {
    return `<a class="bouton-ligne" href="tel:${esc(o.reservation_tel.replace(/[^\d+]/g, ""))}">${icone("phone", 14)}<span class="chiffre">${esc(o.reservation_tel)}</span></a>`;
  }
  return "";
}

// ---------------- Participants et nouveautés (synchronisation) ----------------
/** Pile d'avatars des participants d'un plan (personnages, jamais d'identifiant). */
const pileMembres = (p, taille = 22) => (p.membres || []).length ? `<span class="pile-membres" aria-hidden="true">${p.membres.slice(0, 4)
  .map((m) => avatar({ ...m, dispo: "indispo" }, taille)).join("")}${p.membres.length > 4 ? `<span class="pile-plus chiffre">+${p.membres.length - 4}</span>` : ""}</span>` : "";
const pastilleNouveau = (actif) => actif ? `<span class="pastille-nouveau">Nouveau</span>` : "";
const oeuvreANouveau = (id) => [...nouveaux.values()].some((oid) => oid === id);

/** Ligne collaborative d'une carte : remplace l'ancien compteur. */
function ligneCollab(o, { compacte = false } = {}) {
  const plan = (o.plans || [])[0];
  const id = esc(o.id);
  if (!plan) {
    return `<div class="collab ${compacte ? "compacte" : ""}">
        ${compacte ? "" : `<span class="collab-texte tres-muet">Personne encore. Lance le premier plan.</span>`}
        <button class="bouton-ligne ${o.type === "jeu" && estMulti(o) ? "bouton-accent" : ""}" data-action="ouvrir-plans" data-id="${id}">${icone(o.type === "jeu" ? "gamepad-2" : "plus", 14)}${compacte ? (o.type === "livre" ? "Club de lecture" : o.type === "jeu" ? "Lancer une session" : "Organiser") : "Proposer un créneau"}</button>
      </div>`;
  }
  const quand = libelleInstant(new Date(plan.debut));
  const autres = o.plans.length > 1 ? ` · +${o.plans.length - 1} créneau${o.plans.length > 2 ? "x" : ""}` : "";
  const bouton = plan.je_participe
    ? `<button class="bouton-ligne" aria-pressed="true" data-action="ouvrir-plans" data-id="${id}">${icone("check", 14)}Inscrit</button>`
    : `<button class="bouton-ligne bouton-accent" data-action="rejoindre" data-plan="${plan.id}" data-id="${id}">${icone("users", 14)}Rejoindre</button>`;
  return `<div class="collab ${compacte ? "compacte" : ""}">
      <button class="collab-texte" data-action="ouvrir-plans" data-id="${id}">
        <span class="collab-quand">${esc(quand)}${esc(autres)}${pastilleNouveau(oeuvreANouveau(o.id))}</span>
        <span class="collab-avec">${pileMembres(plan, 18)}<span class="tres-muet">${esc(avecQui(plan))}</span></span>
      </button>
      ${bouton}
    </div>`;
}

function ligneJeu(o) {
  const consoles = (o.consoles || []).map((c) =>
    `<span class="plateforme ${etat.prefs.consoles.includes(c) ? "possedee" : ""}">${esc(NOMS_CONSOLES[c] || c)}</span>`).join("");
  const mode = estMulti(o) ? "Multijoueur" : "Solo";  // co-op et en ligne regroupés
  return `<div class="plateformes"><span class="tag tag-discret tag-mode">${mode}</span>${consoles}</div>`;
}

// ------------------------------------------------------------------ //
// Avatars, humeur du moment et amis                                    //
// ------------------------------------------------------------------ //
// Humeur = statut visible par les amis (serveur : indispo | sortir | distance, expire après 12 h).
const DISPOS = [
  { id: "sortir", nom: "Partant pour bouger", aide: "Les sorties d'abord", icone: "footprints" },
  { id: "distance", nom: "Chill à distance", aide: "Films, séries et jeux d'abord", icone: "sofa" },
  { id: "indispo", nom: "Mode ermite", aide: "Statut discret", icone: "moon" },
];
const nomDispo = (id) => (DISPOS.find((d) => d.id === id) || DISPOS[2]).nom;
const actif = (dispo) => dispo === "sortir" || dispo === "distance";
/** « Bonjour » jusqu'à 18 h, « Bonsoir » ensuite (heure de Paris). */
const salutation = () => { const h = heureNum(new Date()); return h >= 18 || h < 5 ? "Bonsoir" : "Bonjour"; };
const moi = () => ({ prenom: etat.prenom, avatar: etat.avatar, dispo: etat.dispo || "indispo" });

/** Personnage illustré (renderAvatar, DiceBear local) avec anneau lumineux si la personne est active. */
const avatar = (p, taille = 48, classe = "") => `<span class="avatar ${classe} ${actif(p.dispo) ? "anneau" : ""}" aria-hidden="true"
    style="--taille:${taille}px">${renderAvatar(avatarDe(p), taille, p.prenom)}</span>`;

/** Rangée sociale en haut de « Pour vous » : moi (humeur en un tap), puis les amis actifs, puis « Amis ». */
function rangeeAvatars() {
  const actifs = social.amis.filter((a) => actif(a.dispo));
  const m = moi();
  return `<div class="zone-sociale" id="zone-sociale">
      <div class="rangee-avatars defilement" role="list" aria-label="Toi et tes amis">
        <button class="ami-bulle bulle-moi" role="listitem" data-action="humeur" aria-haspopup="true" aria-expanded="false"
          aria-label="Mon humeur : ${esc(nomDispo(m.dispo))}">
          <span class="avatar-cadre">${avatar(m, 52)}<span class="badge-plus">${icone("plus", 11)}</span></span>
          <span class="ami-nom">Moi</span>
        </button>
        ${actifs.map((a) => `<button class="ami-bulle" role="listitem" data-action="voir-ami" aria-label="${esc(a.prenom)} · ${esc(nomDispo(a.dispo))}">
            ${avatar(a, 52)}<span class="ami-nom">${esc(a.prenom)}</span><span class="ami-tag">${esc(nomDispo(a.dispo))}</span></button>`).join("")}
        <button class="ami-bulle" data-action="ouvrir-amis" aria-label="Amis">
          <span class="avatar avatar-ajout" style="--taille:52px">${icone(social.amis.length ? "users" : "user-plus", 18)}</span>
          <span class="ami-nom">${social.amis.length ? "Amis" : "Ajouter"}</span></button>
      </div>
      <div class="popover-humeur" id="popover-humeur" role="menu" hidden>
        <span class="surtitre">Mon humeur du moment</span>
        ${DISPOS.map((d) => `<button role="menuitemradio" aria-checked="${m.dispo === d.id}" data-action="choisir-humeur" data-valeur="${d.id}">
            ${icone(d.icone, 18)}<span><b>${d.nom}</b><small>${d.aide}</small></span>${m.dispo === d.id ? icone("check", 16, "coche") : ""}</button>`).join("")}
      </div>
    </div>`;
}

function ligneAmi(a) {
  const bouton = a.ami
    ? `<button class="bouton-ligne" data-action="retirer-ami" data-code="${esc(a.code)}" aria-label="Retirer ${esc(a.prenom)}">${icone("user-minus", 14)}Retirer</button>`
    : `<button class="bouton-ligne bouton-accent" data-action="ajouter-ami" data-code="${esc(a.code)}">${icone("user-plus", 14)}Ajouter</button>`;
  return `<li class="ligne-ami">${avatar(a, 42)}
      <div class="ligne-ami-texte">
        <span class="ligne-ami-nom"><b>${esc(a.prenom)}</b>${a.demo ? '<span class="tag-demo">Démo</span>' : ""}</span>
        <span class="tres-muet petit">${esc(a.code)}${a.ville ? ` · ${esc(a.ville)}` : ""}</span>
        <span class="petit statut-ami dispo-${esc(a.dispo)}">${esc(nomDispo(a.dispo))}</span>
      </div>${bouton}</li>`;
}

function panneauAmis() {
  const f = feuille;
  const resultats = f.resultats === null ? ""
    : f.resultats.length ? `<ul class="liste-amis">${f.resultats.map(ligneAmi).join("")}</ul>`
    : `<p class="tres-muet petit" style="margin:10px 2px 0">Aucun profil trouvé. Vérifie le code (ex. Camille#101).</p>`;
  return `<div class="feuille-fond" data-action="fermer-feuille"></div>
    <section class="feuille-panneau" role="dialog" aria-modal="true" aria-label="Amis">
      <div class="poignee" data-action="fermer-feuille" aria-hidden="true"></div>
      <button class="bouton-icone feuille-fermer" data-action="fermer-feuille" aria-label="Fermer">${icone("x", 16)}</button>
      <div class="feuille-corps">
        <h2 class="titre-detail">Amis</h2>
        <p class="muet petit" style="margin:6px 0 0">Ajoute tes amis avec leur code ou leur prénom. Ils voient ton humeur du moment, tu vois la leur.</p>
        ${social.moi ? `<div class="mon-code verre">${avatar(moi(), 40)}<span class="mon-code-texte"><span class="tres-muet petit">Mon code</span><b>${esc(social.moi.code)}</b></span>
          <button class="bouton-ligne" data-action="copier-code">${icone("copy", 14)}Copier</button></div>` : ""}
        <label class="champ-recherche">${icone("search", 16, "tres-muet")}
          <input class="champ" id="recherche-ami" maxlength="40" autocomplete="off" placeholder="Prénom ou code, ex. Camille#101" value="${esc(f.q || "")}">
        </label>
        <div id="resultats-amis">${resultats}</div>
        <section class="groupe">
          <span class="surtitre">Mes amis · ${social.amis.length}</span>
          ${social.amis.length ? `<ul class="liste-amis">${social.amis.map(ligneAmi).join("")}</ul>`
            : `<p class="tres-muet petit">Pas encore d'amis ici. Partage ton code ou cherche un prénom.</p>`}
        </section>
        ${social.suggestions.length ? `<section class="groupe">
          <span class="surtitre">Profils de démonstration</span>
          <p class="tres-muet petit" style="margin:-4px 0 10px">Étudiants fictifs, pour essayer les fonctions entre amis.</p>
          <ul class="liste-amis">${social.suggestions.map(ligneAmi).join("")}</ul>
        </section>` : ""}
      </div>
    </section>`;
}

// ---------------- Studio d'avatar (tiroir) : vrais paramètres DiceBear ----------------
const ONGLETS_STUDIO = [["style", "Style"], ["bg", "Fond"], ["hair", "Coiffure"], ["details", "Détails"]];
const styleCourant = () => STYLES.find((x) => x.id === feuille.config.style) || STYLES[0];

function panneauStudio() {
  const f = feuille;
  const index = ONGLETS_STUDIO.findIndex(([k]) => k === f.onglet);
  return `<div class="feuille-fond" data-action="fermer-feuille"></div>
    <section class="feuille-panneau" role="dialog" aria-modal="true" aria-label="Studio d'avatar">
      <div class="poignee" data-action="fermer-feuille" aria-hidden="true"></div>
      <button class="bouton-icone feuille-fermer" data-action="fermer-feuille" aria-label="Fermer">${icone("x", 16)}</button>
      <div class="feuille-corps studio">
        <h2 class="titre-detail">Studio d'avatar</h2>
        <div class="studio-apercu avatar" id="studio-apercu" style="--taille:148px">${renderAvatar(f.config, 148, etat.prenom)}</div>
        <span class="studio-nom" id="studio-nom">${esc(nomStudio(f.config))}</span>
        <button class="bouton-ligne studio-aleatoire" data-action="studio-aleatoire">${icone("shuffle", 14)}Aléatoire</button>
        <div class="segment segment-4 segment-pilule" role="tablist" aria-label="Réglages" style="--index:${index}">
          <span class="segment-indicateur" aria-hidden="true"></span>
          ${ONGLETS_STUDIO.map(([k, n]) => `<button role="tab" data-action="studio-onglet" data-valeur="${k}" aria-pressed="${f.onglet === k}">${n}</button>`).join("")}
        </div>
        <div class="studio-options" id="studio-options">${optionsStudio()}</div>
        <button class="bouton-principal" data-action="studio-enregistrer">${icone("check", 18)}Enregistrer</button>
        <p class="studio-credits">Illustrations DiceBear : Lorelei (Lisa Wischofsky, CC0), Avatar Illustration System (Micah Lanier, CC BY 4.0).</p>
      </div>
    </section>`;
}

const nomStudio = (c) => `${(STYLES.find((x) => x.id === c.style) || STYLES[0]).nom} · ${(FONDS.find((x) => x.id === c.bg) || FONDS[0]).nom}`;

/** Une vignette = le personnage actuel avec une seule valeur changée (aperçu direct). */
const vignette = (cle, valeur, nom, config) => `<button class="studio-option" data-action="studio-choix" data-cle="${cle}" data-valeur="${esc(valeur)}"
    aria-pressed="${feuille.config[cle] === valeur}">${renderAvatar(config, 58, etat.prenom, { zoom: cle !== "style" && cle !== "bg" })}<span>${esc(nom)}</span></button>`;

function optionsStudio() {
  const { config, onglet } = feuille;
  const style = styleCourant();
  if (onglet === "style") return STYLES.map((x) => vignette("style", x.id, x.nom, { style: x.id, seed: config.seed, bg: config.bg })).join("");
  if (onglet === "bg") return FONDS.map((f) => vignette("bg", f.id, f.nom, { ...config, bg: f.id })).join("");
  if (onglet === "hair") return style.hair.map((v) => vignette("hair", v, nomValeur(v), { ...config, hair: v })).join("");
  const groupe = (titre, cle) => `<span class="studio-sous-titre">${titre}</span>`
    + style[cle].map((v) => vignette(cle, v, nomValeur(v), { ...config, [cle]: v })).join("");
  return groupe("Lunettes", "glasses") + groupe("Expression", "mouth") + groupe("Regard", "eyes");
}

function majStudio() {
  $("#studio-apercu").innerHTML = renderAvatar(feuille.config, 148, etat.prenom);
  $("#studio-nom").textContent = nomStudio(feuille.config);
  $("#studio-options").innerHTML = optionsStudio();
}

function ouvrirStudio() {
  feuille = { mode: "avatar", onglet: "style", config: { ...avatarDe(moi()) } };
  rendreFeuille();
}

/** Aperçu du questionnaire : avatar déduit du prénom, tant qu'il n'a pas été personnalisé. */
const apercuInscription = () => `<div class="avatar-inscription" id="avatar-inscription">
    ${avatar({ prenom: etat.prenom, avatar: etat.avatar }, 72)}
    <div class="avatar-inscription-actions">
      <span class="tres-muet petit">Ton avatar</span>
      <div class="puces">
        <button class="bouton-ligne" data-action="ouvrir-studio">${icone("sliders-horizontal", 14)}Personnaliser</button>
        <button class="bouton-ligne" data-action="avatar-aleatoire">${icone("shuffle", 14)}Aléatoire</button>
      </div>
    </div>
  </div>`;

/** Met à jour en place ce qui dépend des amis et de l'avatar (sans recharger l'écran). */
function rafraichirSocial() {
  const r = $("#zone-sociale");
  if (r) r.outerHTML = rangeeAvatars();
  const code = $("#bloc-code");
  if (code) code.outerHTML = blocCode();
  const ins = $("#avatar-inscription");
  if (ins) ins.outerHTML = apercuInscription();
  if (feuille?.mode === "amis") {
    const champ = $("#recherche-ami");
    const focus = document.activeElement === champ;
    const position = champ?.selectionStart;
    $("#feuille .feuille-panneau").outerHTML = panneauAmis().replace(/^[\s\S]*?(<section class="feuille-panneau")/, "$1");
    if (focus) { const c = $("#recherche-ami"); c.focus(); c.setSelectionRange(position, position); }
  }
}

// ------------------------------------------------------------------ //
// Temps réel : smart polling (12 s, onglet visible) + réveil immédiat  //
// ------------------------------------------------------------------ //
const INTERVALLE_SYNC = 12000;
/** Une saisie ou un menu ouvert : on reporte les mises à jour du DOM (jamais de saisie coupée). */
const occupe = () => {
  const actif = document.activeElement;
  return (actif && /^(INPUT|TEXTAREA|SELECT)$/.test(actif.tagName)) || ($("#popover-humeur") && !$("#popover-humeur").hidden);
};

function marquerOngletNouveau() {
  const b = document.querySelector('#onglets [data-onglet="pour-vous"]');
  if (b) b.classList.toggle("a-nouveau", nouveaux.size > 0 && etat.onglet !== "pour-vous");
}

async function synchroniser() {
  if (!etat.uid || synchro.enCours || document.visibilityState !== "visible" || etape !== "application") return;
  synchro.enCours = true;
  try {
    const r = await api(`/api/sync${synchro.v ? `?v=${synchro.v}` : ""}`);
    synchro.v = r.v;
    if (r.inchange) return;
    const avant = synchro.connus;
    const connus = new Map(r.plans.map((p) => [p.id, p.membres.map((m) => m.prenom)]));
    const changes = new Set();  // oeuvres dont les plans ont bougé
    if (avant) {  // premier passage : on mémorise sans rien signaler
      for (const p of r.plans) {
        const anciens = avant.get(p.id);
        if (!anciens) {
          changes.add(p.oeuvre_id);
          if (!p.est_auteur) { nouveaux.set(p.id, p.oeuvre_id); toast(`${p.auteur} propose « ${p.oeuvre_titre} »`); }
        } else if (anciens.length !== p.membres.length || anciens.some((n, i) => n !== p.membres[i]?.prenom)) {
          changes.add(p.oeuvre_id);
          const arrive = p.membres.find((m) => !m.moi && !anciens.includes(m.prenom));
          if (arrive) { nouveaux.set(p.id, p.oeuvre_id); toast(`${arrive.prenom} rejoint « ${p.oeuvre_titre} »`); }
        }
      }
      for (const [id] of avant) if (!connus.has(id)) changes.add((r.plans.find((p) => p.id === id) || {}).oeuvre_id);
    }
    synchro.connus = connus;
    // humeurs et avatars des amis
    const amisAvant = JSON.stringify(social.amis.map((a) => [a.code, a.dispo, a.avatar]));
    social.amis = r.amis;
    if (r.dispo && r.dispo !== etat.dispo) etat.dispo = r.dispo;  // expiration après 12 h côté serveur
    if (JSON.stringify(r.amis.map((a) => [a.code, a.dispo, a.avatar])) !== amisAvant && !occupe()) rafraichirSocial();
    if (changes.size) await appliquerChangementsPlans([...changes].filter(Boolean));
    marquerOngletNouveau();
  } catch (_) { /* hors ligne : on réessaiera */ } finally {
    synchro.enCours = false;
  }
}

/** Met à jour en douceur ce qui est affiché : rangée des sessions, lignes « Avec … » des cartes, fiche ouverte. */
async function appliquerChangementsPlans(oeuvres) {
  if (occupe()) { synchro.v = null; return; }  // on recommencera au prochain passage
  if (etat.onglet === "pour-vous" && $("#bloc-sessions")) {
    try {
      const sessions = await api("/api/plans/a-venir?limite=10");
      donnees.sessions = sessions;
      const bloc = $("#bloc-sessions");
      const position = bloc.querySelector(".swiper")?.swiper?.translate || 0;
      bloc.innerHTML = blocSessions(sessions);
      monterComposants(bloc);
      const sw = bloc.querySelector(".swiper")?.swiper;
      if (sw && position) { sw.setTranslate(Math.max(position, sw.maxTranslate())); sw.updateProgress(); }
    } catch (_) { /* on garde l'affichage */ }
  }
  for (const id of oeuvres) {
    const carte = document.querySelector(`[data-carte="${CSS.escape(id)}"] .collab`);
    const o = trouver(id);
    if (carte && o) {
      try {
        o.plans = await api(`/api/plans?oeuvre_id=${encodeURIComponent(id)}`);
        carte.outerHTML = ligneCollab(o, { compacte: carte.classList.contains("compacte") });
      } catch (_) { /* rien */ }
    }
  }
  if (feuille?.oeuvre && oeuvres.includes(feuille.oeuvre.id) && !feuille.mode) {
    const panneau = $("#feuille .feuille-panneau");
    const defilement = panneau?.scrollTop || 0;
    try { feuille.plans = await api(`/api/plans?oeuvre_id=${encodeURIComponent(feuille.oeuvre.id)}`); } catch (_) { return; }
    if (!occupe()) { rendreFeuille(); const p = $("#feuille .feuille-panneau"); if (p) p.scrollTop = defilement; }
  }
}

document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") synchroniser(); });
window.addEventListener("focus", () => synchroniser());
window.addEventListener("pageshow", () => synchroniser());

async function chargerSocial() {
  if (!etat.uid) return;
  try {
    const [m, liste] = await Promise.all([api("/api/utilisateurs/moi"), api("/api/amis")]);
    const humeurAvant = etat.dispo;
    social = { moi: { code: m.code }, amis: liste.amis, suggestions: liste.suggestions };
    etat.code = m.code;
    etat.mdpActif = Boolean(m.mdp_actif);
    memoriserCompte(etat.uid, etat.prenom, m.code);
    etat.dispo = m.dispo;
    if (m.avatar) etat.avatar = m.avatar;
    stock.ecrire(`etat.${etat.uid}`, etat);
    rafraichirSocial();
    if (humeurAvant !== etat.dispo && etat.onglet === "pour-vous" && !donnees.chargement) rendreContenu();
  } catch (_) { /* hors ligne : on garde l'existant */ }
}

const blocCode = () => `<div class="mon-code verre" id="bloc-code">
    <button class="avatar-profil" data-action="ouvrir-studio" aria-label="Ouvrir le studio d'avatar">${avatar(moi(), 64)}</button>
    <span class="mon-code-texte"><span class="tres-muet petit">Mon code ami</span><b>${esc(social.moi?.code || "…")}</b></span>
    <div class="mon-code-actions">
      <button class="bouton-ligne" data-action="copier-code" ${social.moi ? "" : "disabled"}>${icone("copy", 14)}Copier mon code</button>
      <button class="bouton-ligne" data-action="ouvrir-amis">${icone("users", 14)}Amis · <span class="chiffre">${social.amis.length}</span></button>
      <button class="bouton-ligne" data-action="ouvrir-studio">${icone("palette", 14)}Studio d'avatar</button>
      <button class="bouton-ligne" data-action="ouvrir-mdp">${icone("key-round", 14)}${etat.mdpActif === false ? "Choisir un mot de passe" : "Mot de passe"}</button>
    </div>
  </div>`;

function panneauMdp() {
  const avecActuel = etat.mdpActif !== false;
  return `<div class="feuille-fond" data-action="fermer-feuille"></div>
    <section class="feuille-panneau" role="dialog" aria-modal="true" aria-label="Mot de passe">
      <div class="poignee" data-action="fermer-feuille" aria-hidden="true"></div>
      <button class="bouton-icone feuille-fermer" data-action="fermer-feuille" aria-label="Fermer">${icone("x", 16)}</button>
      <div class="feuille-corps etape-pin">
        <span class="pin-icone">${icone("key-round", 22)}</span>
        <h2 class="titre-detail">${avecActuel ? "Changer de mot de passe" : "Choisir un mot de passe"}</h2>
        <p class="muet petit">Il te permet de te reconnecter à <b>${esc(etat.code || etat.prenom)}</b> sur n'importe quel appareil.</p>
        <form id="form-mdp" class="form-auth">
          ${avecActuel ? champMdp("actuel", "Mot de passe actuel", "current-password") : ""}
          ${champMdp("nouveau", "Nouveau mot de passe (6 caractères minimum)", "new-password")}
          <p class="auth-erreur" id="erreur-mdp" role="alert" hidden></p>
          <button class="bouton-principal" type="submit">${icone("check", 18)}Enregistrer</button>
        </form>
      </div>
    </section>`;
}

const estSauvegarde = (id) => etat.envies.some((e) => e.id === id);
function boutonSauver(o, { texte = false } = {}) {
  const actif = estSauvegarde(o.id);
  const libelle = actif ? "Sauvegardé" : "Sauvegarder";
  return `<button class="${texte ? "bouton-ligne" : "bouton-sauver"}" data-action="sauver" data-id="${esc(o.id)}" aria-pressed="${actif}"
      aria-label="${libelle}" title="${libelle}">${icone(actif ? "bookmark-check" : "bookmark", texte ? 14 : 16)}${texte ? libelle : ""}</button>`;
}

const nomTheme = (id) => (CONFIG.themes.find((t) => t.id === id) || {}).nom || id;

function carteOeuvre(o, i = 0) {
  const livre = o.type === "livre";
  const jeu = o.type === "jeu";
  const annee = o.annee ? ` · ${chiffre(o.annee)}` : "";
  const meta = livre ? `${esc(o.auteur || "")}${annee}` : jeu ? `${esc(o.studio || "")}${annee}`
    : `${o.annee ? chiffre(o.annee) : ""}${o.annee && genresFr(o) ? " · " : ""}${esc(genresFr(o))}`;
  return `<article class="carte-oeuvre apparition" data-carte="${esc(o.id)}" style="animation-delay:${i * 25}ms">
      ${affiche(o)}
      <span class="type-oeuvre">${TYPES[o.type].nom}${livre && !o.francais ? " · VO" : ""}</span>
      <h3 data-action="ouvrir-plans" data-id="${esc(o.id)}">${esc(o.titre)}</h3>
      <div class="meta">${meta}</div>
      ${o.resume && !jeu ? `<p class="extrait">${esc(o.resume)}</p>` : ""}
      ${livre ? `<div class="plateformes">${(o.themes || []).map((t) => `<span class="plateforme">${esc(nomTheme(t))}</span>`).join("")}</div>`
        : jeu ? `${genresFr(o) ? `<div class="meta">${esc(genresFr(o))}</div>` : ""}${ligneJeu(o)}` : lignePlateformes(o)}
      ${ligneCollab(o, { compacte: true })}
      <div class="carte-actions">
        <button class="bouton-ligne" data-action="deja-vu" data-id="${esc(o.id)}">${icone(livre ? "book-open" : jeu ? "gamepad-2" : "eye", 14)}${TYPES[o.type].vu}</button>
      </div>
    </article>`;
}

function carteSortie(o, i = 0) {
  const lieu = [o.lieu && o.lieu !== o.titre ? o.lieu : null, o.ville].filter(Boolean).join(", ");
  const distance = o.distance_km != null ? `<span class="distance">à ${chiffre(km(o.distance_km))}</span>` : "";
  return `<article class="carte-sortie apparition" data-carte="${esc(o.id)}" style="animation-delay:${i * 30}ms">
      ${visuelSortie(o)}
      <div class="carte-sortie-corps">
        <div class="carte-sortie-tete">
          <span class="categorie">${icone(ICONES_CATEGORIE[o.categorie] || "compass", 14)}${esc(o.categorie_libelle || "")}</span>
          ${distance}
        </div>
        <h3 data-action="ouvrir-plans" data-id="${esc(o.id)}">${esc(o.titre)}</h3>
        <div class="ligne-info date">${icone("calendar", 15)}<span>${esc(libelleDate(o))}</span></div>
        <div class="ligne-info">${icone("map-pin", 15)}<span>${esc(lieu)}</span></div>
        ${o.propose_par ? `<div class="ligne-info">${icone("user", 15)}<span>Proposée par ${esc(o.propose_par)}</span></div>` : ""}
        ${o.acces ? `<div class="ligne-info">${icone("train-front", 15)}<span>${esc(o.acces)}</span></div>` : ""}
        <div class="ligne-info">${icone("ticket", 15)}<span class="tarif chiffre">${esc(tarif(o))}</span>${tagBillet(o)}</div>
        <div class="carte-sortie-pied">${ligneCollab(o)}</div>
      </div>
    </article>`;
}

const PALIERS = [
  { valeur: 0, nom: "Sur mesure", aide: "Basé sur tes genres et tes thèmes favoris." },
  { valeur: 0.3, nom: "Équilibré", aide: "Tes goûts, avec quelques pépites glissées." },
  { valeur: 0.6, nom: "Exploration", aide: "Plus de pépites, hors des sentiers battus." },
  { valeur: 1, nom: "Hors piste", aide: "Hors de ta zone de confort : d'autres univers." },
];
// Curseur continu 1 -> 10 : chaque cran dose la part de découvertes (cran 1 = 0, cran 10 = 1).
const cran = () => Math.max(1, Math.min(10, Math.round(etat.decouverte * 9) + 1));
const versDecouverte = (c) => (c - 1) / 9;
const LIBELLES_CRANS = ["Zone de confort", "Zone de confort", "Valeurs sûres", "Valeurs sûres", "Équilibré",
  "Équilibré", "Exploration", "Exploration", "Aventureux", "Hors piste"];
const AIDES_CRANS = ["Basé sur tes genres et tes thèmes favoris.", "Basé sur tes genres et tes thèmes favoris.",
  "Tes goûts, avec une pépite de temps en temps.", "Tes goûts, avec une pépite de temps en temps.",
  "Moitié valeurs sûres, moitié pépites.", "Moitié valeurs sûres, moitié pépites.",
  "Plus de pépites, hors des sentiers battus.", "Plus de pépites, hors des sentiers battus.",
  "Presque tout hors de tes habitudes.", "Hors de ta zone de confort : d'autres univers."];
const indexPalier = () => PALIERS.reduce((meilleur, p, i) =>
  Math.abs(p.valeur - etat.decouverte) < Math.abs(PALIERS[meilleur].valeur - etat.decouverte) ? i : meilleur, 0);
const valeurCurseur = (n) => n === 0 ? "Valeurs sûres uniquement"
  : n === 10 ? "<b>Découverte totale</b> · hors de tes genres" : `<b>${n}</b> découverte${n > 1 ? "s" : ""} sur 10`;

function instrument() {
  const c = cran();
  return `<div class="curseur-bloc verre" style="--cran:${(c - 1) / 9}">
      <div class="curseur-tete">
        <div>
          <span class="surtitre">Confort ↔ Découverte</span>
          <div class="curseur-libelle" id="curseur-libelle">${LIBELLES_CRANS[c - 1]}</div>
        </div>
        <span class="curseur-badge chiffre" id="curseur-badge"><b>${c}</b>/10</span>
      </div>
      <div class="slider-ui slider-continu" id="curseur-ui" aria-label="Dosage confort ou découverte, de 1 à 10"></div>
      <p class="paliers-aide" id="paliers-aide">${AIDES_CRANS[c - 1]}</p>
    </div>`;
}

/** Met à jour libellé, badge et aide pendant le glissement (sans re-rendu). */
function afficherCran(c) {
  const bloc = document.querySelector(".curseur-bloc");
  if (!bloc) return;
  bloc.style.setProperty("--cran", (c - 1) / 9);
  $("#curseur-badge").innerHTML = `<b>${c}</b>/10`;
  const lib = $("#curseur-libelle");
  if (lib.textContent !== LIBELLES_CRANS[c - 1]) {
    lib.textContent = LIBELLES_CRANS[c - 1];
    if (MOUVEMENT) gsap.fromTo(lib, { opacity: 0.2, y: 3 }, { opacity: 1, y: 0, duration: 0.28, ease: "power2.out" });
  }
  $("#paliers-aide").textContent = AIDES_CRANS[c - 1];
}

function localisation() {
  const v = etat.prefs.ville;
  return `<div class="localisation">
      <div class="champ-ville">
        ${icone("map-pin", 16, "tres-muet")}
        <input id="champ-ville" class="champ-nu" type="search" autocomplete="off" spellcheck="false"
               placeholder="Ta ville (toute la France)" value="${esc(v?.nom || "")}" aria-label="Ville">
        ${v ? `<button class="bouton-icone petit-bouton" data-action="effacer-ville" aria-label="Effacer la ville">${icone("x", 14)}</button>` : ""}
      </div>
      <ul class="suggestions" id="suggestions-ville" hidden></ul>
      ${v ? `<div class="rayon">
          <div class="rayon-tete"><span class="surtitre">Périmètre</span><span class="instrument-valeur chiffre" id="valeur-rayon">${etat.prefs.rayon} km</span></div>
          <input type="range" class="curseur-natif" id="rayon" min="5" max="50" step="5" value="${etat.prefs.rayon}"
            style="--pct:${((etat.prefs.rayon - 5) / 45) * 100}%" aria-label="Rayon de recherche en kilomètres" aria-valuetext="${etat.prefs.rayon} km">
          <div class="curseur-reperes chiffre" aria-hidden="true">${[5, 15, 30, 50].map((v) => `<span style="left:${((v - 5) / 45) * 100}%">${v} km</span>`).join("")}</div>
        </div>` : `<p class="tres-muet petit" style="margin:8px 2px 0">Sans ville, on te montre les sorties partout en France.</p>`}
    </div>`;
}

const selecteurHorizon = () => `<div class="puces defilement" role="group" aria-label="Quand ?">
    ${CONFIG.horizons.map((h) => `<button class="puce puce-s" data-action="horizon" data-valeur="${h.id}" aria-pressed="${etat.horizon === h.id}">
      ${h.id === "maintenant" ? icone("clock", 14) : ""}${esc(h.nom)}</button>`).join("")}
  </div>`;

const selecteurDuree = () => `<div class="puces defilement" role="group" aria-label="Temps disponible">
    ${CONFIG.durees.map((d) => `<button class="puce puce-s" data-action="duree" data-valeur="${d.id}" aria-pressed="${(etat.prefs.duree || "tout") === d.id}">
      ${d.id === "tout" ? icone("clock", 14) + "Tout le temps" : esc(d.nom)}</button>`).join("")}
  </div>`;

const selecteurBudget = () => `<div class="puces defilement" role="group" aria-label="Budget">
    ${CONFIG.budgets.map((b) => `<button class="puce puce-s" data-action="budget" data-valeur="${b.id}" aria-pressed="${etat.prefs.budget === b.id}">
      ${b.id === "tous" ? "" : icone("ticket", 14)}${esc(b.nom)}</button>`).join("")}
  </div>`;

function statutAgenda() {
  if (!agenda) return "";
  const texte = agenda.en_cours ? "Synchronisation de l'agenda…"
    : agenda.statut === "erreur" ? `Agenda hors ligne · synchronisé ${ilYa(agenda.derniere_sync)}`
      : `Agenda synchronisé ${ilYa(agenda.derniere_sync)}`;
  return `<div class="statut-agenda" id="statut-agenda">
      <span>${esc(texte)}</span>
      <button class="lien-discret" data-action="synchroniser" ${agenda.en_cours ? "disabled" : ""}>
        ${icone("rotate-ccw", 14, agenda.en_cours ? "tourne" : "")}Mettre à jour</button>
    </div>`;
}

function entete(surtitre, titre, { avantTitre = "" } = {}) {
  const tirage = ["pour-vous", "ecrans", "sorties"].includes(etat.onglet);
  return `<header class="apparition">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:10px">
        <span class="marque">${LOGO}</span>
        ${tirage ? `<button class="bouton-tirage" data-action="choisir-pour-moi">${icone("shuffle", 15)}Choisir à ma place</button>`
          : `<span class="surtitre">${esc(surtitre)}</span>`}
      </div>
      ${avantTitre}
      ${tirage ? `<span class="surtitre surtitre-entete">${esc(surtitre)}</span>` : ""}
      <h1 class="titre-1">${esc(titre)}</h1>
    </header>`;
}

const squelettesAffiches = (n) => `<div class="grille-affiches">${'<div><div class="visuel affiche squelette"></div></div>'.repeat(n)}</div>`;
const squelettesSorties = (n) => '<div class="squelette" style="height:300px;margin-bottom:14px;border-radius:18px"></div>'.repeat(n);

function videSorties() {
  const c = donnees.couverture;
  const suggestion = c && etat.prefs.ville && c.ville !== etat.prefs.ville.nom
    ? `<button class="bouton-ligne" style="margin-top:14px" data-action="aller-ville" data-ville="${esc(JSON.stringify(c))}">
        ${icone("compass", 14)}Voir ${esc(c.ville)} · à ${km(c.distance_km)}</button>` : "";
  return `<div class="vide verre etat-vide">${icone("compass", 28, "tres-muet")}
      <p><b>Aucune sortie avec ces filtres.</b><br>Élargis le périmètre ou le moment, ou repars de zéro.</p>
      <div class="etat-vide-actions"><button class="bouton-ligne bouton-accent" style="margin-top:14px" data-action="reinitialiser-filtres">${icone("rotate-ccw", 14)}Réinitialiser les filtres</button>${suggestion}</div></div>`;
}

function videEcrans() {
  return `<div class="vide verre etat-vide">${icone("sparkles", 28, "tres-muet")}
      <p><b>Rien ne correspond à ces filtres.</b><br>Élargis le budget, le temps disponible, les thèmes ou les machines.</p>
      <button class="bouton-ligne bouton-accent" style="margin-top:14px" data-action="reinitialiser-filtres">${icone("rotate-ccw", 14)}Réinitialiser les filtres</button></div>`;
}

// ------------------------------------------------------------------ //
// Écrans                                                               //
// ------------------------------------------------------------------ //
const puces = (groupe, options) => `<div class="puces">${options.map((o) => `<button class="puce" data-action="pref" data-groupe="${groupe}"
    data-valeur="${esc(JSON.stringify(o.id))}" aria-pressed="${etat.prefs[groupe].includes(o.id)}">${esc(o.nom)}</button>`).join("")}</div>`;

function groupePuces(titre, groupe, options) {
  return `<section class="groupe"><span class="surtitre">${esc(titre)}</span>${puces(groupe, options)}</section>`;
}

const sectionVille = () => `<section class="groupe"><span class="surtitre">Où es-tu ?</span>${localisation()}</section>`;

/** Genres (films, séries, sorties) puis ambiances (sorties seulement), tous deux dans prefs.genres. */
const sectionGenres = () => groupePuces("Tes genres favoris", "genres", CONFIG.genres)
  + `<section class="groupe">
    <span class="surtitre">Quelle ambiance ?</span>
    ${puces("genres", CONFIG.ambiances)}
    <p class="tres-muet petit" style="margin:10px 2px 0">Pour tes sorties.</p>
  </section>`;

/**
 * Profil durable (accueil et Profil) : ville, genres et thèmes, abonnements et consoles.
 * Les envies du moment se choisissent par les onglets du bas, plus dans le questionnaire.
 */
function preferences({ ville = true, ambiances = true } = {}) {
  return (ville ? sectionVille() : "")
    + groupePuces("Tes genres favoris", "genres", CONFIG.genres)
    + groupePuces("Tes thèmes de lecture", "themes", CONFIG.themes)
    + (ambiances ? `<section class="groupe"><span class="surtitre">Quelle ambiance pour sortir ?</span>${puces("genres", CONFIG.ambiances)}</section>` : "")
    + groupePuces("Tes abonnements", "plateformes", CONFIG.plateformes)
    + groupePuces("Tes consoles et appareils", "consoles", CONFIG.consoles);
}

/** Question à choix unique du questionnaire (énergie, moment, curiosité). */
function groupeChoix(titre, cle, options) {
  return `<section class="groupe">
      <span class="surtitre">${esc(titre)}</span>
      <div class="puces">${options.map((o) => `<button class="puce" data-action="choix" data-cle="${cle}"
          data-valeur="${esc(JSON.stringify(o.id))}" aria-pressed="${etat[cle] === o.id}">${o.icone ? icone(o.icone, 14) : ""}${esc(o.nom)}</button>`).join("")}</div>
    </section>`;
}

function ecranBienvenue() {
  return `<div class="bienvenue apparition">
      <span class="marque">${LOGO}</span>
      <div class="bienvenue-centre">
        <h1 class="titre-1 bienvenue-titre">${etat.uid && etat.prenom ? `${salutation()} ${esc(etat.prenom)},<br>on fait quoi ?` : "Salut !<br>On fait quoi aujourd'hui ?"}</h1>
        <p class="muet bienvenue-texte">Pas besoin de savoir : laisse-toi guider selon ton énergie, tes goûts et ce qu'il se passe près de chez toi.</p>
      </div>
      <div class="bienvenue-actions">
        <button class="bouton-principal" data-action="c-est-parti">C'est parti ! ${icone("arrow-right", 18)}</button>
        ${etat.uid ? "" : `<button class="lien-discret lien-reprise" data-action="auth" data-mode="connexion">${icone("log-in", 15)}J'ai déjà un compte</button>`}
      </div>
    </div>`;
}

/** Champ mot de passe masqué, avec bouton discret Afficher / Masquer. */
const champMdp = (nom, libelle, autocomplete) => `<label class="champ-mdp">
    <span class="petit muet">${libelle}</span>
    <span class="champ-mdp-ligne">
      <input class="champ" type="password" name="${nom}" id="mdp-${nom}" minlength="${nom === "actuel" || autocomplete === "current-password" ? 1 : 6}" maxlength="128"
        autocomplete="${autocomplete}" required>
      <button type="button" class="bouton-afficher" data-action="basculer-mdp" data-cible="mdp-${nom}" aria-pressed="false">Afficher</button>
    </span>
  </label>`;

function ecranAccueil() {
  const connus = comptes();
  const creer = modeAuth === "creer";
  return `<div class="apparition">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <span class="marque">${LOGO}</span>
        <button class="lien-discret" data-action="retour-bienvenue">${icone("arrow-left", 16)}Retour</button>
      </div>
      <h1 class="titre-1" style="font-size:34px;margin-top:34px">${creer ? "Dis-nous tout." : "Content de te revoir."}</h1>
      <div class="segment segment-pilule segment-auth" role="tablist" aria-label="Compte" style="--index:${creer ? 0 : 1}">
        <span class="segment-indicateur" aria-hidden="true"></span>
        <button role="tab" data-action="auth" data-mode="creer" aria-pressed="${creer}">Créer un compte</button>
        <button role="tab" data-action="auth" data-mode="connexion" aria-pressed="${!creer}">Se connecter</button>
      </div>
      ${creer ? `
      <p class="muet" style="margin:16px 0 0">Ton profil, une fois pour toutes : tes goûts, ta ville et ce que tu possèdes. L'envie du moment se choisit ensuite dans les onglets.</p>
      <section class="groupe">
        <span class="surtitre">Ton prénom ou pseudo</span>
        <input class="champ" id="champ-prenom" maxlength="30" autocomplete="nickname" placeholder="Ex. Chloé" value="${esc(etat.prenom)}">
        ${apercuInscription()}
      </section>
      <section class="groupe">
        <span class="surtitre">Ton mot de passe</span>
        <form id="form-inscription-mdp" class="form-auth">
          ${champMdp("inscription", "6 caractères minimum", "new-password")}
        </form>
      </section>
      ${sectionVille()}
      ${preferences({ ville: false, ambiances: false })}
    </div>
    <div class="barre-action">
      <button class="bouton-principal" data-action="commencer" ${etat.prenom.trim() ? "" : "disabled"}>Créer mon compte ${icone("arrow-right", 18)}</button>
    </div>` : `
      <form id="form-connexion" class="form-auth" style="margin-top:22px">
        <label class="champ-mdp"><span class="petit muet">Prénom ou code (ex. Sadia#402)</span>
          <input class="champ" name="identifiant" id="champ-identifiant" maxlength="40" autocomplete="username" autocapitalize="words" required></label>
        ${champMdp("connexion", "Mot de passe", "current-password")}
        <p class="auth-erreur" id="erreur-connexion" role="alert" hidden></p>
        <button class="bouton-principal" type="submit">${icone("log-in", 18)}Se connecter</button>
      </form>
      ${connus.length ? `<section class="groupe">
          <span class="surtitre">Déjà connecté sur cet appareil</span>
          <div class="puces">${connus.map((c) => `<button class="puce" data-action="changer-compte" data-uid="${esc(c.id)}">
            ${icone("user", 14)}${esc(c.prenom)}${c.code ? ` <span class="tres-muet">#${esc(c.code.split("#")[1] || "")}</span>` : ""}</button>`).join("")}</div>
        </section>` : ""}
    </div>`}`;
}

const rangee = (cartes, classe = "") => `<div class="swiper rangee ${classe}"><div class="swiper-wrapper">
    ${cartes.map((c) => `<div class="swiper-slide">${c}</div>`).join("")}</div></div>`;

function carteSession(p) {
  const vignette = p.affiche
    ? `<img src="${esc(p.affiche)}" alt="" loading="lazy" decoding="async" onerror="this.remove()">`
    : `<span class="vignette-icone">${icone(TYPES[p.oeuvre_type]?.icone || "users", 22)}</span>`;
  return `<article class="carte-session verre" data-carte="${esc(p.oeuvre_id)}">
      <button class="vignette" data-action="ouvrir-plans" data-id="${esc(p.oeuvre_id)}" data-titre="${esc(p.oeuvre_titre)}" data-type="${esc(p.oeuvre_type)}">${vignette}</button>
      <div class="carte-session-corps">
        <span class="surtitre">${esc(TYPES[p.oeuvre_type]?.collectif || "Sortie à plusieurs")}${pastilleNouveau(nouveaux.has(p.id))}</span>
        <h3>${esc(p.oeuvre_titre)}</h3>
        <div class="petit"><span class="chiffre">${esc(libelleInstant(new Date(p.debut)))}</span></div>
        <div class="collab-avec">${pileMembres(p)}<span class="tres-muet petit">${esc(avecQui(p))}</span></div>
        ${p.je_participe
          ? `<button class="bouton-ligne" aria-pressed="true" data-action="ouvrir-plans" data-id="${esc(p.oeuvre_id)}" data-titre="${esc(p.oeuvre_titre)}" data-type="${esc(p.oeuvre_type)}">${icone("check", 14)}Inscrit</button>`
          : `<button class="bouton-ligne bouton-accent" data-action="rejoindre" data-plan="${p.id}" data-id="${esc(p.oeuvre_id)}">${icone("users", 14)}Rejoindre</button>`}
      </div>
    </article>`;
}

/** L'humeur oriente l'accueil : « Partant pour bouger » met les sorties en premier. */
function blocsPourVous(titre, ecrans, sorties, rayon) {
  const d = donnees;
  const blocEcrans = `${titre(etat.dispo === "distance" ? "Ce soir au chaud" : "Pépites du moment", "ecrans")}
      ${ecrans.length ? rangee(ecrans.map(carteOeuvre), "rangee-affiches")
        : d.chargement ? squelettesRangee() : videEcrans()}`;
  const blocSorties = `${titre(`Sorties proches · ${esc(nomVille())}${esc(rayon)}`, "sorties")}
      ${selecteurHorizon()}
      <div style="margin-top:14px">${sorties.length ? rangee(sorties.map(carteSortie), "rangee-sorties")
        : d.chargement ? squelettesRangee("sorties") : videSorties()}</div>`;
  const note = actif(etat.dispo) ? `<p class="humeur-note">${icone(DISPOS.find((x) => x.id === etat.dispo).icone, 14)}
      ${esc(nomDispo(etat.dispo))} · ${etat.dispo === "sortir" ? "les sorties d'abord" : "films, séries et jeux d'abord"}</p>` : "";
  return note + (etat.dispo === "sortir" ? blocSorties + blocEcrans : blocEcrans + blocSorties);
}

const blocSessions = (sessions) => sessions.length ? rangee(sessions.map(carteSession), "rangee-sessions")
  : `<div class="vide verre">Aucune session prévue pour l'instant. Lance la première depuis une carte : « Organiser », « Lancer une session » ou « Club de lecture ».</div>`;

function ecranPourVous() {
  const d = donnees;
  const ecrans = d.ecrans || [];
  const sorties = d.sorties || [];
  const sessions = d.sessions || [];
  const rayon = etat.prefs.ville ? ` · ${etat.prefs.rayon} km` : "";
  const titre = (t, onglet) => `<div class="titre-section"><h2 class="titre-2">${t}</h2>
      ${onglet ? `<button class="lien-discret" data-action="onglet" data-onglet="${onglet}">Tout voir ${icone("chevron-right", 16)}</button>` : ""}</div>`;
  return `${entete(dateDuJour(), `${salutation()} ${etat.prenom}, on fait quoi ?`, { avantTitre: rangeeAvatars() })}
    ${instrument()}
    <div style="margin-top:12px">${selecteurBudget()}</div>

    <div id="contenu" class="${d.chargement ? "chargement" : ""}">
      ${blocsPourVous(titre, ecrans, sorties, rayon)}
      ${titre("Watch-parties & sessions en cours")}
      <div id="bloc-sessions">${blocSessions(sessions)}</div>
    </div>`;
}

const squelettesRangee = (type = "affiches") => `<div class="rangee-squelette">${(type === "sorties"
  ? '<div class="squelette" style="width:280px;height:330px;border-radius:18px"></div>'
  : '<div><div class="visuel affiche squelette" style="width:148px"></div></div>').repeat(3)}</div>`;

function filtresChezSoi() {
  if (etat.ecrans === "livre") {
    return `<div class="filtres"><span class="surtitre">Thèmes</span>${puces("themes", CONFIG.themes)}</div>`;
  }
  if (etat.ecrans === "jeu") {
    return `<div class="filtres">
        <span class="surtitre">Ma machine</span>
        <div class="puces">${CONFIG.consoles.map((c) => `<button class="puce" data-action="pref" data-groupe="consoles"
          data-valeur="${esc(JSON.stringify(c.id))}" aria-pressed="${etat.prefs.consoles.includes(c.id)}">${icone(c.id === "mobile" ? "smartphone" : c.id === "pc" || c.id === "mac" ? "monitor" : "gamepad-2", 14)}${esc(c.nom)}</button>`).join("")}</div>
        <span class="surtitre" style="margin-top:14px">Mode</span>
        <div class="puces">${CONFIG.modes_jeu.map((m) => `<button class="puce puce-s" data-action="mode-jeu" data-valeur="${m.id}"
          aria-pressed="${etat.prefs.modeJeu === m.id}">${m.id === "tous" ? "" : icone(m.id === "solo" ? "user" : "users", 14)}${esc(m.nom)}</button>`).join("")}</div>
      </div>`;
  }
  return "";
}

const SEGMENTS_CHEZ_SOI = [["tout", "Tout"], ["ecrans", "Films & Séries"], ["livre", "Lecture"], ["jeu", "Jeux vidéo"]];
const dureeVisible = () => (etat.onglet === "ecrans" && etat.ecrans === "ecrans") || etat.onglet === "sorties";

/** Partie de « Ce soir au chaud » qui change avec le sous-onglet : filtres + résultats. */
function zoneChezSoi() {
  const d = donnees;
  const liste = d.grille || [];
  return `<div id="zone-chez-soi">
      ${filtresChezSoi()}
      <div style="margin-top:12px">${selecteurBudget()}</div>
      ${dureeVisible() ? `<div style="margin-top:8px">${selecteurDuree()}</div>` : ""}
      <div id="contenu" class="${d.chargement ? "chargement" : ""}" style="margin-top:22px">
        ${liste.length ? `<div class="grille-affiches">${liste.map(carteOeuvre).join("")}</div>`
          : d.chargement ? squelettesAffiches(4) : videEcrans()}
      </div>
    </div>`;
}

function ecranEcrans() {
  const actif = SEGMENTS_CHEZ_SOI.findIndex(([v]) => v === etat.ecrans);
  const nom = SEGMENTS_CHEZ_SOI[actif][1];
  return `${entete(nom === "Tout" ? "Chez soi" : nom, "Ce soir, au chaud")}
    <div class="segment segment-4 segment-pilule" role="tablist" aria-label="Univers chez soi" style="--index:${actif}">
      <span class="segment-indicateur" aria-hidden="true"></span>
      ${SEGMENTS_CHEZ_SOI.map(([v, n]) => `<button role="tab" data-action="segment" data-valeur="${v}" aria-pressed="${etat.ecrans === v}">${n}</button>`).join("")}
    </div>
    ${instrument()}
    ${zoneChezSoi()}`;
}

/** Remplace la zone de Chez soi : hauteur verrouillée, fondu + translateY(6px) en 220 ms. */
function rendreZone() {
  const zone = $("#zone-chez-soi");
  if (!zone) return rendre();
  const tmp = document.createElement("div");
  tmp.innerHTML = zoneChezSoi();
  const nouvelle = tmp.firstElementChild;
  nouvelle.style.minHeight = `${zone.offsetHeight}px`;
  zone.replaceWith(nouvelle);
  monterComposants(nouvelle);
  const fin = () => { nouvelle.style.minHeight = ""; };
  if (MOUVEMENT && nouvelle.animate) {
    nouvelle.animate([{ opacity: 0, transform: "translateY(6px)" }, { opacity: 1, transform: "none" }],
      { duration: 220, easing: "cubic-bezier(0.22, 1, 0.36, 1)" }).onfinish = fin;
  } else fin();
}

function ecranSorties() {
  const d = donnees;
  const liste = d.grille || [];
  return `${entete("Sorties", "Sortir près de chez toi")}
    ${statutAgenda()}
    <button class="bouton-ligne" style="margin-top:12px" data-action="ouvrir-publication">${icone("calendar-plus", 14)}Proposer une sortie</button>
    <div style="margin-top:16px">${localisation()}</div>
    <div style="margin-top:14px">${selecteurHorizon()}</div>
    <div style="margin-top:12px">${selecteurBudget()}</div>
    <div style="margin-top:8px">${selecteurDuree()}</div>
    <div class="puces defilement" style="margin-top:8px">${CONFIG.categories.map((c) => `<button class="puce" data-action="pref"
        data-groupe="categories" data-valeur="${esc(JSON.stringify(c.id))}" aria-pressed="${etat.prefs.categories.includes(c.id)}">
        ${icone(ICONES_CATEGORIE[c.id], 15)}${esc(c.nom)}</button>`).join("")}</div>
    ${instrument()}
    <div class="bascule-vue" role="tablist" aria-label="Affichage des sorties" style="--index:${etat.vueSorties === "carte" ? 1 : 0}">
      <span class="paliers-pilule" aria-hidden="true"></span>
      <button role="tab" data-action="vue-sorties" data-valeur="liste" aria-selected="${etat.vueSorties !== "carte"}">${icone("list", 15)}Liste</button>
      <button role="tab" data-action="vue-sorties" data-valeur="carte" aria-selected="${etat.vueSorties === "carte"}">${icone("map", 15)}Carte</button>
    </div>
    <div id="contenu" class="${d.chargement ? "chargement" : ""}" style="margin-top:16px">
      ${etat.vueSorties === "carte"
        ? `<div id="carte-sorties" class="carte-leaflet verre" aria-label="Carte des sorties"></div>
           <p class="tres-muet petit" style="margin:10px 2px 0">${liste.length} sortie${liste.length > 1 ? "s" : ""} sur la carte · touche un repère pour ouvrir la fiche.</p>`
        : liste.length ? liste.map(carteSortie).join("") : d.chargement ? squelettesSorties(2) : videSorties()}
    </div>`;
}

function ecranProfil() {
  const vus = etat.dejaVus;
  const mesPlans = donnees.mesPlans;
  const autres = comptes().filter((c) => c.id !== etat.uid);
  return `${entete("Profil", etat.prenom)}
    ${blocCode()}
    <div class="compte">
      <span class="muet">Connecté sur cet appareil</span>
      <div class="puces" style="margin-top:10px">
        ${autres.map((c) => `<button class="puce" data-action="changer-compte" data-uid="${esc(c.id)}">${icone("user", 14)}${esc(c.prenom)}</button>`).join("")}
        <button class="puce" data-action="changer-de-compte">${icone("repeat", 14)}Changer de compte</button>
        <button class="puce" data-action="nouveau-compte">${icone("plus", 14)}Nouveau compte</button>
        <button class="puce" data-action="se-deconnecter">${icone("log-out", 14)}Se déconnecter</button>
      </div>
    </div>
    <section class="groupe">
      <span class="surtitre">Mes envies · ${etat.envies.length}</span>
      ${etat.envies.length ? rangee(etat.envies.map((e) => `<article class="carte-envie" data-carte="${esc(e.id)}">
          <button class="envie-visuel ${e.type === "sortie" || e.type === "jeu" ? "paysage" : ""}" data-action="ouvrir-plans" data-id="${esc(e.id)}"
            data-titre="${esc(e.titre)}" data-type="${esc(e.type)}" aria-label="${esc(e.titre)}">
            ${e.affiche ? `<img src="${esc(e.affiche)}" alt="" loading="lazy" onerror="this.remove()">` : icone(TYPES[e.type]?.icone || "bookmark", 22)}
          </button>
          <span class="type-oeuvre">${esc(TYPES[e.type]?.nom || "")}</span>
          <h3>${esc(e.titre)}</h3>
        </article>`), "rangee-envies")
        : `<div class="liste-vus"><div class="vide">Touche le marque-page d'une carte pour mettre de côté un film, une série, un livre, un jeu ou une sortie.</div></div>`}
    </section>
    <section class="groupe">
      <span class="surtitre">Mes plans</span>
      ${mesPlans === undefined ? `<div class="squelette" style="height:64px"></div>`
        : mesPlans.length ? `<div class="liste-vus"><ul>${mesPlans.map((p) => `<li>
            ${icone(TYPES[p.oeuvre_type]?.icone || "film", 16, "tres-muet")}
            <button class="titre plan-ligne" data-action="ouvrir-plans" data-id="${esc(p.oeuvre_id)}" data-titre="${esc(p.oeuvre_titre)}" data-type="${esc(p.oeuvre_type)}">
              <span>${esc(p.oeuvre_titre)}</span>
              <span class="tres-muet petit">${esc(libelleInstant(new Date(p.debut)))} · ${esc(avecQui(p))}${p.est_auteur ? " · organisé par toi" : ""}</span>
            </button>
            ${icone("chevron-right", 16, "tres-muet")}
          </li>`).join("")}</ul></div>`
        : `<div class="liste-vus"><div class="vide">Aucun plan pour l'instant. Touche « Proposer un créneau » ou « Rejoindre » sur une carte.</div></div>`}
    </section>
    ${preferences()}
    <section class="groupe">
      <span class="surtitre">Déjà vus, lus et joués · ${vus.length}</span>
      <div class="liste-vus">${vus.length ? `<ul>${vus.map((o) => `<li>
          ${icone(TYPES[o.type]?.icone || "film", 16, "tres-muet")}
          <span class="titre">${esc(o.titre)}</span>
          <button class="bouton-icone" data-action="retirer-vu" data-id="${esc(o.id)}" aria-label="Retirer ${esc(o.titre)}">${icone("x", 14)}</button>
        </li>`).join("")}</ul>` : `<div class="vide">Touche « Déjà vu » ou « Déjà lu » sur une carte : on s'en servira pour affiner tes recommandations.</div>`}</div>
      <input class="champ" id="recherche-vu" type="search" placeholder="Ajouter un film, une série, un livre ou un jeu…" autocomplete="off" style="margin-top:12px">
      <ul class="suggestions" id="suggestions-vu" hidden></ul>
    </section>
    <section class="groupe">${statutAgenda()}</section>
    <section class="groupe">
      <button class="bouton-ligne" data-action="oublier-compte">${icone("x", 14)}Oublier ce compte sur cet appareil</button>
    </section>
    <p class="sources">
      Sources : sorties <a href="https://openagenda.com" target="_blank" rel="noopener">OpenAgenda</a> (via Opendatasoft, synchronisé toutes les 6 h) ;
      communes <a href="https://adresse.data.gouv.fr" target="_blank" rel="noopener">API Adresse</a> ;
      séries <a href="https://www.tvmaze.com" target="_blank" rel="noopener">TVmaze</a> (CC BY-SA) ;
      livres GoodReads et <a href="https://openlibrary.org" target="_blank" rel="noopener">OpenLibrary</a> ;
      affiches de films, jeux vidéo et jaquettes <a href="https://www.wikidata.org" target="_blank" rel="noopener">Wikidata</a> et <a href="https://www.wikipedia.org" target="_blank" rel="noopener">Wikipédia</a> ;
      affiches et plateformes <a href="https://www.themoviedb.org" target="_blank" rel="noopener">TMDB</a> (abonnements en France uniquement) ;
      films MovieLens (GroupLens).
    </p>`;
}

const ECRANS = { "pour-vous": ecranPourVous, ecrans: ecranEcrans, sorties: ecranSorties, profil: ecranProfil };

// ------------------------------------------------------------------ //
// Feuille collaborative (créneaux, participants, messages)             //
// ------------------------------------------------------------------ //
function creneauParDefaut(o) {
  if (o.type === "sortie" && o.prochaine && new Date(o.prochaine.debut) > new Date()) return new Date(o.prochaine.debut);
  if (o.type === "livre") return new Date(`${jourParis(new Date(Date.now() + 7 * 864e5))}T18:30:00`);
  const d = new Date();
  const ce_soir = new Date(`${jourParis(d)}T21:00:00`);
  // 21h heure de Paris ≈ 21h locale pour un public en France ; sinon demain
  return ce_soir > d ? ce_soir : new Date(ce_soir.getTime() + 864e5);
}

function formulairePublication() {
  const v = etat.prefs.ville;
  const demain = new Date(`${jourParis(new Date(Date.now() + 864e5))}T20:00:00`);
  return `<div class="feuille-fond" data-action="fermer-feuille"></div>
    <section class="feuille-panneau" role="dialog" aria-modal="true" aria-label="Proposer une sortie">
      <div class="feuille-tete">
        <div><span class="surtitre">Publier pour les étudiants</span><h2 class="titre-2" style="margin-top:4px">Proposer une sortie</h2></div>
        <button class="bouton-icone" data-action="fermer-feuille" aria-label="Fermer">${icone("x", 16)}</button>
      </div>
      <form class="feuille-corps proposer" id="form-sortie">
        <label class="petit muet">Titre
          <input class="champ" name="titre" required minlength="3" maxlength="100" placeholder="Soirée jeux, concert, expo…"></label>
        <label class="petit muet">Catégorie
          <select class="champ" name="categorie">${CONFIG.categories.map((c) => `<option value="${c.id}">${esc(c.nom)}</option>`).join("")}</select></label>
        <label class="petit muet">Lieu
          <input class="champ" name="lieu" required minlength="2" maxlength="120" placeholder="Nom du bar, de la salle, adresse…"></label>
        <div class="petit muet">Ville
          <div class="localisation" style="margin-top:6px">
            <div class="champ-ville">${icone("map-pin", 16, "tres-muet")}
              <input id="champ-ville-pub" class="champ-nu" type="search" autocomplete="off" required placeholder="Ville" value="${esc(v?.nom || "")}">
            </div>
            <ul class="suggestions" id="suggestions-ville-pub" hidden></ul>
          </div>
        </div>
        <div class="deux-colonnes">
          <label class="petit muet">Quand
            <input class="champ" type="datetime-local" name="debut" required value="${esc(valeurLocale(demain))}" min="${esc(valeurLocale(new Date()))}"></label>
          <label class="petit muet">Durée
            <select class="champ" name="duree_h">${[1, 2, 3, 4, 6].map((h) => `<option value="${h}" ${h === 3 ? "selected" : ""}>${h} h</option>`).join("")}</select></label>
        </div>
        <label class="petit muet">Prix en euros (0 = gratuit)
          <input class="champ" type="number" name="prix" min="0" max="500" step="0.5" placeholder="Laisser vide si non précisé"></label>
        <label class="petit muet">Description (facultatif)
          <input class="champ" name="description" maxlength="500" placeholder="Ambiance, programme, comment venir…"></label>
        <button class="bouton-principal" type="submit">${icone("calendar-plus", 18)}Publier la sortie</button>
      </form>
    </section>`;
}

/** En-tête de la fiche : visuel, informations, résumé, action « Déjà vu / lu / joué ». */
function detailOeuvre(o) {
  const sortie = o.type === "sortie";
  const img = o.affiche ? `<img src="${esc(o.affiche)}" alt="" decoding="async" onerror="this.remove()">` : "";
  const note = o.note ? `${String(o.note).replace(".", ",")} / ${o.type === "livre" ? 5 : 10}` : "";
  const infos = sortie
    ? [[libelleDate(o)], [o.distance_km != null ? `à ${km(o.distance_km)}` : "", true], [tarif(o), true]]
    : o.type === "livre" ? [[o.auteur], [o.annee, true], [note, true]]
      : o.type === "jeu" ? [[o.studio], [o.annee, true], [o.editeur && o.editeur !== o.studio ? `Édité par ${o.editeur}` : ""]]
        : [[o.annee, true], [genresFr(o, 3)], [note, true]];
  const lignes = infos.filter(([t]) => t).map(([t, nombre]) => nombre ? chiffre(t) : `<span>${esc(t)}</span>`).join("");
  const badges = o.type === "jeu" ? ligneJeu(o)
    : o.type === "livre" ? `<div class="plateformes">${(o.themes || []).map((t) => `<span class="plateforme">${esc(nomTheme(t))}</span>`).join("")}</div>`
      : sortie ? "" : lignePlateformes(o);
  const adresse = sortie ? [o.lieu, o.adresse, o.ville].filter(Boolean).filter((x, i, a) => a.indexOf(x) === i).join(", ") : "";
  return `<div class="detail ${sortie || o.type === "jeu" ? "detail-paysage" : ""}">
      <div class="detail-visuel">${img}<span class="voile"></span>${tagDecouverte(o)}</div>
      <div class="detail-texte">
        ${o.selectionne ? `<span class="tag tag-selection">${icone("sparkles", 12)}Sélectionné pour vous</span>` : ""}
        <span class="surtitre">${esc(sortie ? o.categorie_libelle || "Sortie" : TYPES[o.type]?.nom || "")}</span>
        <h2 class="titre-detail">${esc(o.titre)}</h2>
        ${lignes ? `<div class="detail-infos">${lignes}</div>` : ""}
        ${badges}
        ${adresse ? `<div class="ligne-info">${icone("map-pin", 15)}<span>${esc(adresse)}</span></div>` : ""}
        ${sortie && o.acces ? `<div class="ligne-info">${icone("train-front", 15)}<span>${esc(o.acces)}</span></div>` : ""}
        ${sortie && o.billetterie ? `<div class="ligne-info">${tagBillet(o)}</div>` : ""}
        <div class="detail-actions">${boutonSauver(o, { texte: true })}${sortie ? lienReservation(o) : ""}
        ${!sortie && TYPES[o.type] ? `<button class="bouton-ligne" data-action="deja-vu" data-id="${esc(o.id)}">${icone(o.type === "livre" ? "book-open" : o.type === "jeu" ? "gamepad-2" : "eye", 14)}${TYPES[o.type].vu}</button>` : ""}</div>
      </div>
    </div>
    ${o.resume ? `<section class="detail-synopsis"><span class="surtitre">${sortie ? "Description" : "Synopsis"}</span><p>${esc(o.resume)}</p></section>` : ""}
    ${o.url && lienSur(o.url) ? `<a class="lien-discret" href="${esc(o.url)}" target="_blank" rel="noopener noreferrer">${icone("external-link", 14)}${sortie ? "Voir l'événement" : "Voir la source"}</a>` : ""}`;
}

function rendreFeuille() {
  const racine = $("#feuille");
  if (!feuille) { racine.hidden = true; racine.innerHTML = ""; return; }
  if (feuille.mode === "mdp") {
    const ouverture = racine.hidden;
    racine.hidden = false;
    racine.innerHTML = panneauMdp();
    if (ouverture) animerOuvertureFeuille(racine);
    return;
  }
  if (feuille.mode === "avatar") {
    const ouverture = racine.hidden;
    racine.hidden = false;
    racine.innerHTML = panneauStudio();
    if (ouverture) animerOuvertureFeuille(racine);
    return;
  }
  if (feuille.mode === "amis") {
    const ouverture = racine.hidden;
    racine.hidden = false;
    racine.innerHTML = panneauAmis();
    if (ouverture) animerOuvertureFeuille(racine);
    return;
  }
  if (feuille.mode === "publier") {
    const ouverture = racine.hidden;
    racine.hidden = false;
    racine.innerHTML = formulairePublication();
    monterComposants(racine);
    if (ouverture) animerOuvertureFeuille(racine);
    return;
  }
  const { oeuvre: o, plans } = feuille;
  const estSortie = o.type === "sortie";
  const plansHtml = plans === null ? `<div class="squelette" style="height:90px"></div>`
    : plans.length ? plans.map((p) => `<div class="plan">
        <div class="plan-tete">
          <div>
            <div class="plan-quand">${esc(libelleInstant(new Date(p.debut)))}${pastilleNouveau(nouveaux.has(p.id))}</div>
            <div class="collab-avec">${pileMembres(p)}<span class="tres-muet petit">${esc(avecQui(p))} · proposé par ${esc(p.auteur)}</span></div>
          </div>
          <button class="bouton-ligne ${p.je_participe ? "" : "bouton-accent"}" data-action="${p.je_participe ? "quitter" : "rejoindre"}" data-plan="${p.id}" data-id="${esc(o.id)}"
            ${p.je_participe ? 'aria-pressed="true"' : ""}>${icone(p.je_participe ? "check" : "users", 14)}${p.je_participe ? "Inscrit" : "Rejoindre"}</button>
        </div>
        ${p.rendez_vous ? `<div class="ligne-info">${icone(estSortie ? "map-pin" : "tv", 15)}${lienSur(p.rendez_vous)
          ? `<a href="${esc(p.rendez_vous)}" target="_blank" rel="noopener noreferrer">${esc(p.rendez_vous)}</a>` : `<span>${esc(p.rendez_vous)}</span>`}</div>` : ""}
        ${p.message ? `<p class="plan-message">« ${esc(p.message)} » <span class="tres-muet">— ${esc(p.auteur)}</span></p>` : ""}
        ${(p.messages || []).length ? `<ul class="fil">${p.messages.map((m) => `<li><b>${esc(m.prenom)}</b> ${esc(m.texte)}</li>`).join("")}</ul>` : ""}
        ${p.je_participe ? `<form class="ecrire" data-plan="${p.id}">
            <input class="champ" name="texte" maxlength="280" placeholder="Un mot pour le groupe…" autocomplete="off">
            <button class="bouton-icone" aria-label="Envoyer">${icone("arrow-right", 16)}</button>
          </form>` : ""}
      </div>`).join("")
      : `<p class="tres-muet">Aucun créneau pour l'instant. Propose le premier.</p>`;
  const ouverture = racine.hidden;
  racine.hidden = false;
  racine.innerHTML = `<div class="feuille-fond" data-action="fermer-feuille"></div>
    <section class="feuille-panneau" role="dialog" aria-modal="true" aria-label="${esc(o.titre)}">
      <div class="poignee" data-action="fermer-feuille" aria-hidden="true"></div>
      <button class="bouton-icone feuille-fermer" data-action="fermer-feuille" aria-label="Fermer">${icone("x", 16)}</button>
      <div class="feuille-corps">
        ${detailOeuvre(o)}
        <div class="titre-section" style="margin:8px 0 0"><h3 class="titre-2">${esc(TYPES[o.type]?.collectif || "Sortie à plusieurs")}</h3></div>
        ${plansHtml}
        <form class="proposer" id="form-plan">
          <span class="surtitre">Proposer un créneau</span>
          <label class="petit muet">Quand
            <input class="champ" type="datetime-local" name="debut" required value="${esc(valeurLocale(creneauParDefaut(o)))}" min="${esc(valeurLocale(new Date()))}">
          </label>
          <label class="petit muet">${estSortie ? "Point de rendez-vous" : o.type === "livre" ? "Lieu ou lien visio" : o.type === "jeu" ? "Lien Discord ou lieu" : "Lien de la watch-party"}
            <input class="champ" name="rendez_vous" maxlength="200"
              placeholder="${estSortie ? "Devant la gare, le campus, l'entrée…" : o.type === "livre" ? "Café, bibliothèque, lien visio…" : o.type === "jeu" ? "Serveur Discord, chez qui, salle du campus…" : "Lien Discord, Teleparty… (https://)"}">
          </label>
          <label class="petit muet">Un mot (facultatif)
            <input class="champ" name="message" maxlength="280" placeholder="${estSortie ? "On y va ensemble ?" : o.type === "livre" ? "On lit les 100 premières pages pour la prochaine fois ?" : o.type === "jeu" ? "On lance une partie à 21h ? Il reste deux places." : "On lance l'épisode à 21h ?"}">
          </label>
          <button class="bouton-principal" type="submit">${icone("plus", 18)}Proposer ce créneau</button>
        </form>
      </div>
    </section>`;
  if (ouverture) animerOuvertureFeuille(racine);
}

function animerOuvertureFeuille(racine) {
  if (!MOUVEMENT) return;
  gsap.fromTo(racine.querySelector(".feuille-fond"), { opacity: 0 }, { opacity: 1, duration: 0.3, ease: "power1.out" });
  gsap.fromTo(racine.querySelector(".feuille-panneau"), { yPercent: 100 }, { yPercent: 0, duration: 0.55, ease: "expo.out" });
}

async function fermerFeuille() {
  const racine = $("#feuille");
  if (MOUVEMENT && !racine.hidden) {
    await Promise.all([
      gsap.to(racine.querySelector(".feuille-fond"), { opacity: 0, duration: 0.22 }),
      gsap.to(racine.querySelector(".feuille-panneau"), { yPercent: 100, duration: 0.3, ease: "power2.in" }),
    ]);
  }
  feuille = null;
  rendreFeuille();
}

async function ouvrirFeuille(oeuvre) {
  feuille = { oeuvre, plans: null };
  rendreFeuille();
  try {
    feuille.plans = await api(`/api/plans?oeuvre_id=${encodeURIComponent(oeuvre.id)}`);
  } catch (_) { feuille.plans = []; toast("Impossible de charger les créneaux."); }
  if (feuille) rendreFeuille();
}

async function rafraichirApresPlan() {
  if (feuille) {
    feuille.plans = await api(`/api/plans?oeuvre_id=${encodeURIComponent(feuille.oeuvre.id)}`).catch(() => feuille.plans);
    rendreFeuille();
  }
  if (etat.onglet === "profil") chargerMesPlans(); else charger({ partiel: true });
}

// ------------------------------------------------------------------ //
// Rendu et chargement                                                  //
// ------------------------------------------------------------------ //
function rendre() {
  const ecran = $("#ecran");
  const nav = $("#onglets");
  // La bienvenue s'affiche à chaque ouverture, même avec un compte (la sélection se charge pendant ce temps).
  if (etape === "bienvenue" || !etat.uid) {
    nav.hidden = true;
    ecran.className = `ecran sans-onglets${etape === "bienvenue" ? " ecran-bienvenue" : ""}`;
    ecran.innerHTML = etape === "bienvenue" ? ecranBienvenue() : ecranAccueil();
    return;
  }
  nav.hidden = false;
  ecran.className = "ecran";
  nav.innerHTML = ONGLETS.map((o) => `<button class="onglet" data-action="onglet" data-onglet="${o.id}"
      ${etat.onglet === o.id ? 'aria-current="page"' : ""}>${icone(o.icone, 22)}<span>${o.nom}</span></button>`).join("");
  marquerOngletNouveau();
  ecran.innerHTML = ECRANS[etat.onglet]();
  monterComposants(ecran);
}

function rendreContenu() {
  const zone = $("#contenu");
  if (!zone) return rendre();
  const tmp = document.createElement("div");
  tmp.innerHTML = ECRANS[etat.onglet]();
  const nouvelle = tmp.querySelector("#contenu");
  if (!nouvelle) return;
  // pas de saut de mise en page : la nouvelle grille garde la hauteur de l'ancienne le temps du fondu
  const hauteur = zone.offsetHeight;
  if (MOUVEMENT) nouvelle.style.minHeight = `${hauteur}px`;
  zone.replaceWith(nouvelle);
  monterComposants(nouvelle);
  const fin = () => { nouvelle.style.minHeight = ""; };
  if (MOUVEMENT && nouvelle.animate) {
    nouvelle.animate([{ opacity: 0.25, transform: "translateY(6px)" }, { opacity: 1, transform: "none" }],
      { duration: 220, easing: "cubic-bezier(0.22, 1, 0.36, 1)" }).onfinish = fin;
  } else fin();
}

/** Après chaque rendu : curseurs noUiSlider, carrousels Swiper, apparition des cartes en cascade (GSAP). */
function monterComposants(racine) {
  const curseur = racine.querySelector?.("#curseur-ui");
  if (curseur && !curseur.noUiSlider && noUiSlider) {
    noUiSlider.create(curseur, {
      start: cran(), step: 1, connect: [true, false], range: { min: 1, max: 10 },
      pips: { mode: "values", values: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10], density: 100, format: { to: (v) => String(Math.round(v)) } },
    });
    curseur.noUiSlider.on("slide", ([v]) => {
      const c = Math.round(Number(v));
      if (c === cran()) return;
      etat.decouverte = versDecouverte(c);
      afficherCran(c);
      if (navigator.vibrate) navigator.vibrate(4);
      chargerApresCran();
    });
    curseur.noUiSlider.on("change", sauvegarder);
  }
  if (Swiper) {
    racine.querySelectorAll?.(".swiper.rangee:not(.swiper-initialized)").forEach((el) => new Swiper(el, {
      slidesPerView: "auto", spaceBetween: 12, freeMode: { enabled: true, momentum: true, sticky: false },
      grabCursor: true, slidesOffsetBefore: 0, slidesOffsetAfter: 0, watchSlidesProgress: true,
    }));
  }
  const carte = racine.querySelector?.("#carte-sorties");
  if (carte) monterCarte(carte);
  if (MOUVEMENT) {
    const cartes = [...(racine.querySelectorAll?.("[data-carte]") || [])].slice(0, 16);
    if (cartes.length) gsap.from(cartes, { opacity: 0, y: 18, scale: 0.985, duration: 0.55, stagger: 0.035, ease: ADOUCI, clearProps: "opacity,transform" });
  }
}

/**
 * Carte Leaflet : périmètre, repères minimalistes, clic = fiche de la sortie.
 * Tuiles OpenStreetMap assombries en CSS (.tuiles-sombres) : CartoDB Dark Matter exige désormais
 * une clé d'API (filigrane « API KEY REQUIRED » constaté), OpenStreetMap non.
 */
let carteLeaflet = null;
function monterCarte(el) {
  const L = window.L;
  if (!L) { el.innerHTML = `<div class="vide">Carte indisponible.</div>`; return; }
  if (carteLeaflet) { carteLeaflet.remove(); carteLeaflet = null; }
  const v = etat.prefs.ville;
  const sorties = (donnees.grille || []).filter((o) => o.lat != null && o.lon != null);
  carteLeaflet = L.map(el, { zoomControl: false, attributionControl: true, scrollWheelZoom: false })
    .setView(v ? [v.lat, v.lon] : [46.6, 2.4], v ? 11 : 5);
  L.control.zoom({ position: "bottomright" }).addTo(carteLeaflet);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19, className: "tuiles-sombres",
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">contributeurs OpenStreetMap</a>',
  }).addTo(carteLeaflet);
  if (v) {
    const cercle = L.circle([v.lat, v.lon], { radius: etat.prefs.rayon * 1000, color: "#A5B4FC", weight: 1, opacity: 0.6,
      fillColor: "#818CF8", fillOpacity: 0.06, dashArray: "4 6" }).addTo(carteLeaflet);
    L.circleMarker([v.lat, v.lon], { radius: 4, color: "#fff", weight: 2, fillColor: "#0B0F19", fillOpacity: 1 }).addTo(carteLeaflet);
    carteLeaflet.fitBounds(cercle.getBounds(), { padding: [12, 12] });
  } else if (sorties.length) {
    carteLeaflet.fitBounds(L.latLngBounds(sorties.map((o) => [o.lat, o.lon])), { padding: [24, 24] });
  }
  sorties.forEach((o) => {
    const repere = L.marker([o.lat, o.lon], {
      icon: L.divIcon({ className: "repere", html: `<span class="repere-point ${o.origine === "decouverte" ? "repere-pepite" : ""}"></span>`, iconSize: [22, 22] }),
      title: o.titre, keyboard: true,
    }).addTo(carteLeaflet);
    repere.bindTooltip(`${esc(o.titre)}<br><span class="tres-muet">${esc(libelleDate(o))}</span>`, { direction: "top", offset: [0, -10], className: "bulle" });
    repere.on("click", () => ouvrirFeuille(o));
  });
  setTimeout(() => carteLeaflet?.invalidateSize(), 60);
}

/**
 * « Choisir à ma place » : tirage parmi le top 3 des recommandations de l'écran courant (mêmes filtres :
 * onglet, curseur, budget, temps disponible), pondéré 50 / 30 / 20 %, puis ouverture de la fiche.
 */
/** Tout le pool affiché pour l'onglet et les filtres actifs (15 à 20 résultats et plus), sans doublon. */
function candidatsTirage() {
  const d = donnees;
  const pool = etat.onglet === "pour-vous" ? [...(d.ecrans || []), ...(d.sorties || [])] : [...(d.grille || [])];
  const vus = new Set();
  return pool.filter((o) => o && !vus.has(o.id) && vus.add(o.id));
}
let dernierTirage = null;  // jamais deux fois de suite le même élément

async function choisirPourMoi() {
  const pool = candidatsTirage();
  if (!pool.length) return toast("Rien à départager avec ces filtres.");
  const possibles = pool.length > 1 ? pool.filter((o) => o.id !== dernierTirage) : pool;
  const gagnant = possibles[Math.floor(Math.random() * possibles.length)];
  dernierTirage = gagnant.id;
  if (MOUVEMENT && pool.length > 1) {
    // micro-effet (~500 ms) : les visuels du pool défilent dans une vignette qui ralentit puis se fige sur l'élu
    const racine = $("#feuille");
    racine.hidden = false;
    racine.innerHTML = `<div class="feuille-fond"></div>
      <section class="tirage tirage-flash" role="status" aria-live="polite">
        <span class="surtitre">On choisit pour toi · <span class="chiffre">${pool.length}</span> possibilités</span>
        <div class="tirage-vignette" id="tirage-vignette"></div>
        <span class="tirage-titre" id="tirage-titre"></span>
      </section>`;
    gsap.fromTo(racine.querySelector(".feuille-fond"), { opacity: 0 }, { opacity: 1, duration: 0.18 });
    const vignette = $("#tirage-vignette");
    const titre = $("#tirage-titre");
    const montrer = (o) => {
      vignette.innerHTML = o.affiche ? `<img src="${esc(o.affiche)}" alt="" onerror="this.remove()">`
        : icone(ICONES_CATEGORIE[o.categorie] || TYPES[o.type]?.icone || "sparkles", 28);
      titre.textContent = o.titre;
    };
    const melange = [...pool].sort(() => Math.random() - 0.5).filter((o) => o.id !== gagnant.id).slice(0, 7);
    let delai = 34;  // 34 + 40 + 48 + … ≈ 450 ms au total
    for (const o of melange) {
      montrer(o);
      await new Promise((res) => setTimeout(res, delai));
      delai *= 1.2;
    }
    montrer(gagnant);
    vignette.classList.add("elu");
    await new Promise((res) => setTimeout(res, 160));
    racine.hidden = true;
  }
  ouvrirFeuille({ ...gagnant, selectionne: true });
}

/** Glissement + fondu entre écrans : direction selon l'ordre des onglets (ou des sous-onglets). */
const ADOUCI = "expo.out";  // ≈ cubic-bezier(0.22, 1, 0.36, 1)
function transitionEcran(direction = 0) {
  if (!MOUVEMENT) return;
  gsap.fromTo("#ecran", { opacity: 0, x: direction * 36 }, { opacity: 1, x: 0, duration: 0.5, ease: ADOUCI, clearProps: "transform" });
}

function corps(type, k, ecrans = ["film", "serie", "livre", "jeu"]) {
  const v = etat.prefs.ville;
  return {
    type, k, ecrans,
    genres: etat.prefs.genres,
    deja_vus: etat.dejaVus.map((o) => o.id),
    decouverte: etat.decouverte,
    plateformes: etat.prefs.plateformes,
    lat: v?.lat ?? null,
    lon: v?.lon ?? null,
    rayon_km: etat.prefs.rayon,
    horizon: etat.horizon,
    budget: etat.prefs.budget,
    themes: etat.prefs.themes,
    duree: dureeVisible() ? etat.prefs.duree || "tout" : "tout",  // durée : Films & Séries et Sorties seulement
    categories: etat.prefs.categories,
    consoles: etat.prefs.consoles,
    mode_jeu: etat.prefs.modeJeu,
  };
}

async function couvertureSiVide(sorties, signal) {
  const v = etat.prefs.ville;
  if (sorties.length || !v) return null;
  try { return await api(`/api/couverture?lat=${v.lat}&lon=${v.lon}`, undefined, signal); } catch (_) { return null; }
}

async function charger({ partiel = false, zone = false } = {}) {
  if (!etat.uid) return;
  if (etat.onglet === "profil") { rendre(); chargerMesPlans(); return; }
  controleur?.abort();
  controleur = new AbortController();
  const signal = controleur.signal;
  cleQuota = `${etat.onglet}:${etat.ecrans}:${nbPepites()}`;
  donnees = { ...donnees, chargement: true };
  if (zone) $("#zone-chez-soi")?.classList.add("chargement");
  else partiel ? $("#contenu")?.classList.add("chargement") : rendre();
  try {
    if (etat.onglet === "pour-vous") {
      // composition déduite du profil durable : livres si des thèmes de lecture, jeux si des consoles
      const ecransChoisis = ["film", "serie", ...(etat.prefs.themes.length ? ["livre"] : []),
        ...(etat.prefs.consoles.length ? ["jeu"] : [])];
      const [ecrans, sorties, sessions] = await Promise.all([
        api("/api/recommandations", corps("tout", 10, ecransChoisis), signal),
        api("/api/recommandations", corps("sortie", 8), signal),
        api("/api/plans/a-venir?limite=10", undefined, signal).catch(() => []),
      ]);
      donnees = { ecrans, sorties, sessions, couverture: await couvertureSiVide(sorties, signal) };
    } else if (etat.onglet === "ecrans") {
      const types = { tout: ["film", "serie", "livre", "jeu"], ecrans: ["film", "serie"], livre: ["livre"], jeu: ["jeu"] }[etat.ecrans];
      donnees = { grille: await api("/api/recommandations",
        types.length === 1 ? corps(types[0], 20) : corps("tout", 20, types), signal) };
    } else if (etat.onglet === "sorties") {
      const grille = await api("/api/recommandations", corps("sortie", etat.vueSorties === "carte" ? 40 : 20), signal);
      donnees = { grille, couverture: await couvertureSiVide(grille, signal) };
    }
  } catch (e) {
    if (e.name === "AbortError") return;
    donnees = { erreur: true };
    toast("Le serveur ne répond pas.");
  }
  if (zone && etat.onglet === "ecrans") rendreZone();
  else partiel ? rendreContenu() : rendre();
}

async function chargerMesPlans() {
  try { donnees = { ...donnees, mesPlans: await api("/api/mes-plans") }; } catch (_) { donnees = { ...donnees, mesPlans: [] }; }
  if (etat.onglet === "profil" && !feuille) rendre();
}

const chargerSiQuotaChange = debounce(() => {
  if (`${etat.onglet}:${etat.ecrans}:${nbPepites()}` !== cleQuota) charger({ partiel: true });
}, 60);
const chargerApresRayon = debounce(() => charger({ partiel: true }), 150);
/** Curseur natif du périmètre : valeur en direct (JetBrains Mono), remplissage, rechargement si l'appli est ouverte. */
function majRayon(champ) {
  etat.prefs.rayon = Number(champ.value);
  champ.style.setProperty("--pct", `${((etat.prefs.rayon - 5) / 45) * 100}%`);
  champ.setAttribute("aria-valuetext", `${etat.prefs.rayon} km`);
  const v = $("#valeur-rayon");
  if (v) v.textContent = `${etat.prefs.rayon} km`;
  if (etat.uid && etape === "application" && etat.onglet !== "profil") chargerApresRayon();
}
const chargerApresCran = debounce(() => charger({ partiel: true }), 120);

function trouver(id) {
  for (const liste of Object.values(donnees)) {
    if (Array.isArray(liste)) {
      const o = liste.find((x) => x.id === id);
      if (o) return o;
    }
  }
  return null;
}

function apresPreference() {
  sauvegarder();
  if (etat.uid && etat.onglet !== "profil") charger();
  else rendre();
}

async function rafraichirAgenda() {
  try { agenda = await api("/api/agenda"); } catch (_) { return; }
  const zone = $("#statut-agenda");
  if (zone) zone.outerHTML = statutAgenda();
}

// ------------------------------------------------------------------ //
// Comptes                                                              //
// ------------------------------------------------------------------ //
function memoriserCompte(id, prenom, code) {
  const ancien = comptes().find((c) => c.id === id);
  const liste = comptes().filter((c) => c.id !== id);
  stock.ecrire("comptes", [{ id, prenom, code: code || ancien?.code || null }, ...liste].slice(0, 8));
}

/** Horizon d'un ancien profil (ex. « court ») absent des choix proposés : « Dans la semaine ». */
function normaliserHorizon() {
  if (!CONFIG.horizons.some((h) => h.id === etat.horizon)) etat.horizon = "semaine";
}

async function changerCompte(uid) {
  const local = stock.lire(`etat.${uid}`, null);
  let u = null;
  try {
    etat.uid = uid;  // pour l'en-tête X-Utilisateur
    u = await api("/api/utilisateurs/moi");
  } catch (e) {
    if (!local && e.status === 401) {
      stock.ecrire("comptes", comptes().filter((c) => c.id !== uid));
      etat = ETAT_INITIAL();
      toast("Ce compte n'existe plus sur le serveur.");
      return rendre();
    }
  }
  const prefsServeur = u?.prefs || {};
  etat = {
    ...ETAT_INITIAL(),
    ...(local || {}),
    uid,
    prenom: u?.prenom || local?.prenom || "",
    prefs: { ...PREFS_INITIALES(), ...(local?.prefs || {}), ...(local ? {} : prefsServeur), ville: u?.ville ?? local?.prefs?.ville ?? null },
    dejaVus: local?.dejaVus || prefsServeur.dejaVus || [],
    envies: local?.envies || prefsServeur.envies || [],
    avatar: u?.avatar || local?.avatar || null,
    dispo: u?.dispo || "indispo",
    code: u?.code || local?.code || null,
    horizon: local?.horizon || prefsServeur.horizon || "semaine",
  };
  delete etat.prefs.dejaVus;
  delete etat.prefs.envies;
  delete etat.prefs.horizon;
  normaliserHorizon();
  memoriserCompte(uid, etat.prenom, etat.code);
  stock.ecrire("actif", uid);
  sauvegarder();
  donnees = {};
  haut();
  toast(`Bonjour ${etat.prenom}`);
  social = { moi: null, amis: [], suggestions: [] };
  charger();
  chargerSocial();
}

// ------------------------------------------------------------------ //
// Actions                                                              //
// ------------------------------------------------------------------ //
/** Choix unique dans un groupe de puces : met à jour aria-pressed sans re-rendre l'écran. */
function choisirDansGroupe(b) {
  b.parentElement.querySelectorAll(`[data-action="${b.dataset.action}"]`).forEach((x) => x.setAttribute("aria-pressed", x === b));
}

const actions = {
  pref(b) {
    const { groupe } = b.dataset;
    const valeur = JSON.parse(b.dataset.valeur);
    const liste = etat.prefs[groupe];
    etat.prefs[groupe] = liste.includes(valeur) ? liste.filter((v) => v !== valeur) : [...liste, valeur];
    sauvegarder();
    b.setAttribute("aria-pressed", etat.prefs[groupe].includes(valeur));
    if (etat.uid && etape !== "bienvenue" && etat.onglet !== "profil") charger({ partiel: true });
  },
  "vue-sorties"(b) {
    if (etat.vueSorties === b.dataset.valeur) return;
    etat.vueSorties = b.dataset.valeur;
    const bascule = b.closest(".bascule-vue");
    bascule.style.setProperty("--index", etat.vueSorties === "carte" ? 1 : 0);
    bascule.querySelectorAll("button").forEach((x) => x.setAttribute("aria-selected", x.dataset.valeur === etat.vueSorties));
    sauvegarder();
    charger({ partiel: true });
  },
  palier(b) {
    const i = Number(b.dataset.index);
    const groupe = b.closest(".paliers");
    if (indexPalier() === i) return;
    etat.decouverte = PALIERS[i].valeur;
    groupe.style.setProperty("--index", i);
    groupe.querySelectorAll("button").forEach((x, j) => x.setAttribute("aria-checked", j === i));
    const aide = $("#paliers-aide");
    if (MOUVEMENT) gsap.fromTo(aide, { opacity: 0, y: 4 }, { opacity: 1, y: 0, duration: 0.3 });
    aide.textContent = PALIERS[i].aide;
    sauvegarder();
    charger({ partiel: true });
  },
  "mode-jeu"(b) {
    if (etat.prefs.modeJeu === b.dataset.valeur) return;
    etat.prefs.modeJeu = b.dataset.valeur;
    choisirDansGroupe(b);
    sauvegarder();
    charger({ partiel: true });
  },
  duree(b) {
    if ((etat.prefs.duree || "tout") === b.dataset.valeur) return;
    etat.prefs.duree = b.dataset.valeur;
    choisirDansGroupe(b);
    sauvegarder();
    charger({ partiel: true });
  },
  "choisir-pour-moi"() { choisirPourMoi(); },
  budget(b) {
    if (etat.prefs.budget === b.dataset.valeur) return;
    etat.prefs.budget = b.dataset.valeur;
    choisirDansGroupe(b);
    sauvegarder();
    charger({ partiel: true });
  },
  horizon(b) {
    if (etat.horizon === b.dataset.valeur) return;
    etat.horizon = b.dataset.valeur;
    choisirDansGroupe(b);
    sauvegarder();
    charger({ partiel: true });
  },
  "choisir-ville"(b) {
    etat.prefs.ville = resultatsVille[Number(b.dataset.index)];
    apresPreference();
  },
  "aller-ville"(b) {
    const c = JSON.parse(b.dataset.ville);
    etat.prefs.ville = { nom: c.ville, contexte: null, lat: c.lat, lon: c.lon };
    apresPreference();
    toast(`Sorties autour de ${c.ville}`);
  },
  "effacer-ville"() {
    etat.prefs.ville = null;
    apresPreference();
  },
  async commencer(b) {
    const prenom = etat.prenom.trim();
    if (!prenom) return;
    const mdp = $("#mdp-inscription")?.value || "";
    if (mdp.length < 6) {
      $("#mdp-inscription")?.focus();
      return toast("Choisis un mot de passe de 6 caractères minimum.");
    }
    b.disabled = true;
    try {
      const { ville, ...prefs } = etat.prefs;
      const u = await api("/api/utilisateurs", { prenom, ville, prefs: { ...prefs, horizon: etat.horizon },
        avatar: avatarDe({ prenom, avatar: etat.avatar }), mot_de_passe: mdp });  // jamais stocké côté client
      etat.uid = u.id;
      etat.prenom = u.prenom;
      etat.code = u.code;
      etat.mdpActif = true;
      etat.onglet = "pour-vous";
      etape = "application";
      memoriserCompte(u.id, u.prenom, u.code);
      sauvegarder();
      haut();
      social = { moi: null, amis: [], suggestions: [] };
      charger();
      chargerSocial();
    } catch (e) {
      b.disabled = false;
      toast(`Connexion impossible : ${e.message}`);
    }
  },
  "changer-compte"(b) {
    if (feuille) { feuille = null; rendreFeuille(); }
    etape = "application";
    changerCompte(b.dataset.uid);
  },
  "c-est-parti"() {
    etape = etat.uid ? "application" : "questionnaire";  // compte connu : directement à la sélection
    modeAuth = "creer";
    haut();
    rendre();
    synchroniser();
  },
  "retour-bienvenue"() {
    etape = "bienvenue";
    haut();
    rendre();
  },
  /** Choix unique du questionnaire : énergie, horizon ou curiosité (avant création du compte). */
  choix(b) {
    const { cle } = b.dataset;
    etat[cle] = JSON.parse(b.dataset.valeur);
    b.parentElement.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", x === b));
  },
  "nouveau-compte"() {
    etape = "questionnaire";
    modeAuth = "creer";
    social = { moi: null, amis: [], suggestions: [] };
    etat = ETAT_INITIAL();
    stock.retirer("actif");
    donnees = {};
    haut();
    rendre();
  },
  "oublier-compte"() {
    stock.ecrire("comptes", comptes().filter((c) => c.id !== etat.uid));
    stock.retirer(`etat.${etat.uid}`);
    actions["nouveau-compte"]();
  },
  onglet(b) {
    if (etat.onglet === b.dataset.onglet && b.closest("#onglets")) return haut();
    const ordre = ONGLETS.map((o) => o.id);
    const direction = Math.sign(ordre.indexOf(b.dataset.onglet) - ordre.indexOf(etat.onglet));
    etat.onglet = b.dataset.onglet;
    sauvegarder();
    donnees = {};
    haut();
    charger();
    transitionEcran(direction);
  },
  segment(b) {
    if (etat.ecrans === b.dataset.valeur) return;
    etat.ecrans = b.dataset.valeur;
    const groupe = b.closest(".segment-pilule");
    groupe.style.setProperty("--index", SEGMENTS_CHEZ_SOI.findIndex(([v]) => v === etat.ecrans));
    groupe.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", x === b));
    const zone = $("#zone-chez-soi");
    if (zone) { zone.style.minHeight = `${zone.offsetHeight}px`; zone.classList.add("chargement"); }
    $("#ecran").querySelector(".surtitre-entete, header .surtitre")?.replaceChildren(
      document.createTextNode(SEGMENTS_CHEZ_SOI.find(([v]) => v === etat.ecrans)[1].replace("Tout", "Chez soi")));
    sauvegarder();
    donnees = {};
    charger({ zone: true });
  },
  "deja-vu"(b) {
    const id = b.dataset.id;
    const o = trouver(id);
    if (!o || etat.dejaVus.some((v) => v.id === id)) return;
    etat.dejaVus.push({ id, titre: o.titre, type: o.type });
    sauvegarder();
    b.closest("[data-carte]")?.classList.add("sortante");
    toast(`« ${o.titre} » ajouté à tes ${{ livre: "déjà lus", jeu: "déjà joués" }[o.type] || "déjà vus"} · sélection ajustée`);
    setTimeout(() => charger({ partiel: true }), 260);
  },
  async "ouvrir-plans"(b) {
    for (const [pid, oid] of nouveaux) if (oid === b.dataset.id) nouveaux.delete(pid);
    marquerOngletNouveau();
    let o = trouver(b.dataset.id);
    if (!o) {  // élément hors de la liste affichée (Mes envies, Mes plans) : fiche complète depuis l'API
      try { o = await api(`/api/oeuvre?id=${encodeURIComponent(b.dataset.id)}`); } catch (_) {
        o = etat.envies.find((e) => e.id === b.dataset.id) || { id: b.dataset.id, titre: b.dataset.titre, type: b.dataset.type };
      }
    }
    ouvrirFeuille(o);
  },
  sauver(b) {
    const id = b.dataset.id;
    const o = trouver(id) || feuille?.oeuvre || etat.envies.find((e) => e.id === id);
    if (!o) return;
    const actif = !estSauvegarde(id);
    etat.envies = actif
      ? [{ id, titre: o.titre, type: o.type, affiche: o.affiche || null, annee: o.annee || null, auteur: o.auteur || null,
           studio: o.studio || null, categorie: o.categorie || null, ville: o.ville || null, genres: (o.genres || []).slice(0, 2) },
         ...etat.envies].slice(0, 60)
      : etat.envies.filter((e) => e.id !== id);
    sauvegarder();
    document.querySelectorAll(`[data-action="sauver"][data-id="${CSS.escape(id)}"]`).forEach((el) => {
      el.outerHTML = boutonSauver(o, { texte: el.classList.contains("bouton-ligne") });
    });
    toast(actif ? "Ajouté à Mes envies" : "Retiré de Mes envies");
    if (etat.onglet === "profil" && !feuille) rendre();
  },
  auth(b) {
    modeAuth = b.dataset.mode;
    etape = "questionnaire";
    haut();
    rendre();
    if (modeAuth === "connexion") setTimeout(() => $("#champ-identifiant")?.focus(), 50);
  },
  "basculer-mdp"(b) {
    const champ = document.getElementById(b.dataset.cible);
    const visible = champ.type === "password";
    champ.type = visible ? "text" : "password";
    b.textContent = visible ? "Masquer" : "Afficher";
    b.setAttribute("aria-pressed", String(visible));
  },
  "ouvrir-mdp"() { feuille = { mode: "mdp" }; rendreFeuille(); },
  "changer-de-compte"() {
    stock.retirer("actif");  // le compte reste dans « Déjà connecté sur cet appareil »
    etat = ETAT_INITIAL(); donnees = {}; social = { moi: null, amis: [], suggestions: [] };
    modeAuth = "connexion"; etape = "questionnaire";
    haut(); rendre();
  },
  "se-deconnecter"() {
    stock.ecrire("comptes", comptes().filter((c) => c.id !== etat.uid));
    stock.retirer(`etat.${etat.uid}`);
    stock.retirer("actif");
    etat = ETAT_INITIAL(); donnees = {}; social = { moi: null, amis: [], suggestions: [] };
    modeAuth = "connexion"; etape = "questionnaire";
    haut(); rendre();
    toast("Déconnecté");
  },
  "ouvrir-amis"() {
    feuille = { mode: "amis", q: "", resultats: null };
    rendreFeuille();
    chargerSocial();
  },
  async "ajouter-ami"(b) {
    try {
      const a = await api("/api/amis", { code: b.dataset.code });
      toast(`${a.prenom} fait partie de tes amis`);
      if (feuille?.resultats) feuille.resultats = feuille.resultats.map((r) => r.code === a.code ? { ...r, ami: true } : r);
      await chargerSocial();
    } catch (err) { toast(err.message); }
  },
  async "retirer-ami"(b) {
    try {
      await api("/api/amis/retirer", { code: b.dataset.code });
      if (feuille?.resultats) feuille.resultats = feuille.resultats.map((r) => r.code === b.dataset.code ? { ...r, ami: false } : r);
      await chargerSocial();
    } catch (err) { toast(err.message); }
  },
  async "copier-code"() {
    const code = social.moi?.code;
    if (!code) return;
    try { await navigator.clipboard.writeText(code); toast(`Code copié : ${code}`); }
    catch (_) { toast(`Ton code : ${code}`); }  // presse-papiers indisponible (HTTP sur téléphone)
  },
  humeur(b) {
    const pop = $("#popover-humeur");
    if (!pop) return;
    pop.hidden = !pop.hidden;
    b.setAttribute("aria-expanded", String(!pop.hidden));
    if (!pop.hidden && MOUVEMENT) gsap.fromTo(pop, { opacity: 0, y: -6, scale: 0.98 }, { opacity: 1, y: 0, scale: 1, duration: 0.28, ease: "expo.out" });
  },
  async "choisir-humeur"(b) {
    const statut = b.dataset.valeur;
    const precedent = etat.dispo;
    etat.dispo = statut;
    sauvegarder();
    rafraichirSocial();
    if (etat.onglet === "pour-vous") rendreContenu();
    try {
      await api("/api/utilisateurs/moi/dispo", { statut }, undefined, "PUT");
      toast(statut === "indispo" ? "Mode ermite : statut discret" : `Tes amis te voient « ${nomDispo(statut)} »`);
    } catch (err) {
      etat.dispo = precedent; sauvegarder(); rafraichirSocial();
      if (etat.onglet === "pour-vous") rendreContenu();
      toast(err.message);
    }
  },
  "voir-ami"(b) {
    document.querySelectorAll(".ami-bulle.montre-tag").forEach((x) => { if (x !== b) x.classList.remove("montre-tag"); });
    b.classList.toggle("montre-tag");
  },
  "ouvrir-studio"() { ouvrirStudio(); },
  "avatar-aleatoire"() {
    etat.avatar = avatarAleatoire(avatarDe({ prenom: etat.prenom, avatar: etat.avatar }));
    rafraichirSocial();
  },
  "studio-onglet"(b) {
    feuille.onglet = b.dataset.valeur;
    const groupe = b.closest(".segment-pilule");
    groupe.style.setProperty("--index", ONGLETS_STUDIO.findIndex(([k]) => k === feuille.onglet));
    groupe.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", x === b));
    $("#studio-options").innerHTML = optionsStudio();
  },
  "studio-choix"(b) {
    const { cle, valeur } = b.dataset;
    const c = feuille.config;
    // changer de style remet à zéro les choix propres à l'ancien style (les valeurs DiceBear diffèrent)
    feuille.config = cle === "style" ? { style: valeur, seed: c.seed, bg: c.bg } : { ...c, [cle]: valeur };
    const defilement = $("#studio-options").scrollTop;
    majStudio();
    $("#studio-options").scrollTop = defilement;
  },
  "studio-aleatoire"() {
    feuille.config = avatarAleatoire(feuille.config);
    majStudio();
    if (MOUVEMENT) gsap.fromTo("#studio-apercu", { scale: 0.94 }, { scale: 1, duration: 0.5, ease: "back.out(2)" });
  },
  async "studio-enregistrer"() {
    const config = feuille.config;
    etat.avatar = config;
    if (etat.uid) {
      sauvegarder();
      try { await api("/api/utilisateurs/moi/avatar", config, undefined, "PUT"); toast("Avatar enregistré"); }
      catch (err) { toast(`Enregistré sur cet appareil (${err.message})`); }
    }
    await fermerFeuille();
    rafraichirSocial();
  },
  "reinitialiser-filtres"() {
    Object.assign(etat.prefs, { budget: "tous", duree: "tout", modeJeu: "tous", categories: [] });
    etat.horizon = "mois";
    sauvegarder();
    charger();
  },
  "fermer-feuille"() { fermerFeuille(); },
  "ouvrir-publication"() {
    feuille = { mode: "publier", ville: etat.prefs.ville };
    rendreFeuille();
  },
  "choisir-ville-pub"(b) {
    feuille.ville = resultatsVille[Number(b.dataset.index)];
    $("#champ-ville-pub").value = feuille.ville.nom;
    $("#suggestions-ville-pub").hidden = true;
  },
  async rejoindre(b) {
    try {
      await api(`/api/plans/${b.dataset.plan}/participation`, { actif: true });
      toast("C'est noté, tu fais partie du plan.");
      rafraichirApresPlan();
    } catch (e) { toast(e.message); }
  },
  async quitter(b) {
    try {
      await api(`/api/plans/${b.dataset.plan}/participation`, { actif: false });
      toast("Tu as quitté ce créneau.");
      rafraichirApresPlan();
    } catch (e) { toast(e.message); }
  },
  async synchroniser() {
    try { agenda = await api("/api/agenda/synchroniser", {}); } catch (_) { return toast("Synchronisation impossible."); }
    rafraichirAgenda();
    const suivre = setInterval(async () => {
      await rafraichirAgenda();
      if (agenda && !agenda.en_cours) {
        clearInterval(suivre);
        toast(agenda.statut === "ok" ? "Agenda à jour" : "Agenda injoignable, sorties existantes conservées");
        if (etat.onglet !== "profil") charger({ partiel: true });
      }
    }, 3000);
  },
  "retirer-vu"(b) {
    etat.dejaVus = etat.dejaVus.filter((o) => o.id !== b.dataset.id);
    sauvegarder();
    rendre();
  },
  "ajouter-vu"(b) {
    const o = resultatsRecherche[Number(b.dataset.index)];
    if (o && !etat.dejaVus.some((v) => v.id === o.id)) {
      etat.dejaVus.push({ id: o.id, titre: o.titre, type: o.type });
      sauvegarder();
    }
    rendre();
    if (o) toast(`« ${o.titre} » ajouté à tes déjà vus`);
  },
};

// ------------------------------------------------------------------ //
// Autocomplétions                                                      //
// ------------------------------------------------------------------ //
let resultatsVille = [];
const rechercherVille = debounce(async (q, suffixe = "") => {
  const liste = $(`#suggestions-ville${suffixe}`);
  const action = suffixe ? "choisir-ville-pub" : "choisir-ville";
  if (!liste) return;
  if (q.length < 2) { liste.hidden = true; return; }
  try { resultatsVille = (await api(`/api/communes?q=${encodeURIComponent(q)}`)).communes; } catch (_) { resultatsVille = []; }
  liste.innerHTML = resultatsVille.length
    ? resultatsVille.map((c, i) => `<li><button type="button" data-action="${action}" data-index="${i}">
        ${icone("map-pin", 16, "tres-muet")}<span style="flex:1">${esc(c.nom)}</span>
        <span class="tres-muet petit">${esc(c.code_postal || "")}</span></button></li>`).join("")
    : `<li class="vide">Aucune commune trouvée</li>`;
  liste.hidden = false;
}, 250);

const rechercherAmi = debounce(async (q) => {
  if (feuille?.mode !== "amis") return;
  feuille.q = q;
  if (q.length < 2) { feuille.resultats = null; $("#resultats-amis").innerHTML = ""; return; }
  try { feuille.resultats = await api(`/api/amis/recherche?q=${encodeURIComponent(q)}`); } catch (_) { feuille.resultats = []; }
  if (feuille?.mode !== "amis") return;
  const tmp = document.createElement("div");
  tmp.innerHTML = panneauAmis();
  $("#resultats-amis").innerHTML = tmp.querySelector("#resultats-amis").innerHTML;
}, 220);

const rafraichirApercuInscription = debounce(() => {
  const el = $("#avatar-inscription .avatar");
  if (el) el.outerHTML = avatar({ prenom: etat.prenom, avatar: etat.avatar }, 72);
}, 120);

let resultatsRecherche = [];
const rechercherVu = debounce(async (q) => {
  const liste = $("#suggestions-vu");
  if (!liste) return;
  if (q.length < 2) { liste.hidden = true; return; }
  try { resultatsRecherche = await api(`/api/oeuvres?q=${encodeURIComponent(q)}&limite=6`); } catch (_) { resultatsRecherche = []; }
  liste.innerHTML = resultatsRecherche.length
    ? resultatsRecherche.map((o, i) => `<li><button data-action="ajouter-vu" data-index="${i}">
        ${icone(TYPES[o.type]?.icone || "film", 16, "tres-muet")}<span style="flex:1">${esc(o.titre)}</span>
        <span class="tres-muet petit">${o.annee ?? ""}</span></button></li>`).join("")
    : `<li class="vide">Aucun titre trouvé</li>`;
  liste.hidden = false;
}, 200);

// ------------------------------------------------------------------ //
// Événements (délégation)                                              //
// ------------------------------------------------------------------ //
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-action]");
  if (b && !b.disabled && actions[b.dataset.action]) { e.preventDefault(); actions[b.dataset.action](b); }
  if (!e.target.closest("#champ-ville, #suggestions-ville")) { const l = $("#suggestions-ville"); if (l) l.hidden = true; }
  if (!e.target.closest("#champ-ville-pub, #suggestions-ville-pub")) { const l = $("#suggestions-ville-pub"); if (l) l.hidden = true; }
  if (!e.target.closest(".bulle-moi, #popover-humeur") || e.target.closest('[data-action="choisir-humeur"]')) {
    const p = $("#popover-humeur"); if (p && !p.hidden) { p.hidden = true; $(".bulle-moi")?.setAttribute("aria-expanded", "false"); }
  }
});

document.addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  if (f.id === "form-connexion") {
    const d = Object.fromEntries(new FormData(f));
    const erreur = $("#erreur-connexion");
    const bouton = f.querySelector("button[type=submit]");
    bouton.disabled = true;
    try {
      const u = await api("/api/connexion", { identifiant: d.identifiant.trim(), mot_de_passe: d.connexion });
      memoriserCompte(u.id, u.prenom, u.code);
      etape = "application";
      await changerCompte(u.id);
    } catch (err) {
      bouton.disabled = false;
      erreur.hidden = false;
      erreur.textContent = err.status ? err.message : "Serveur injoignable, réessaie dans un instant.";
    }
    return;
  }
  if (f.id === "form-mdp") {
    const d = Object.fromEntries(new FormData(f));
    const erreur = $("#erreur-mdp");
    if ((d.nouveau || "").length < 6) { erreur.hidden = false; erreur.textContent = "6 caractères minimum."; return; }
    try {
      await api("/api/utilisateurs/moi/mot-de-passe", { actuel: d.actuel || null, nouveau: d.nouveau }, undefined, "PUT");
      etat.mdpActif = true; sauvegarder();
      await fermerFeuille(); rafraichirSocial(); toast("Mot de passe enregistré");
    } catch (err) { erreur.hidden = false; erreur.textContent = err.message; }
    return;
  }
  if (f.id === "form-sortie" && feuille) {
    const d = Object.fromEntries(new FormData(f));
    if (!feuille.ville || feuille.ville.nom !== $("#champ-ville-pub").value) return toast("Choisis la ville dans la liste.");
    const bouton = f.querySelector("button[type=submit]");
    bouton.disabled = true;
    try {
      await api("/api/sorties", { ...d, ville: feuille.ville, duree_h: Number(d.duree_h), prix: d.prix === "" ? null : Number(d.prix) });
      feuille = null;
      rendreFeuille();
      toast("Sortie publiée. Les étudiants autour peuvent la rejoindre.");
      charger();
    } catch (err) { bouton.disabled = false; toast(err.message); }
  } else if (f.id === "form-plan" && feuille) {
    const donneesForm = Object.fromEntries(new FormData(f));
    try {
      await api("/api/plans", { oeuvre_id: feuille.oeuvre.id, ...donneesForm });
      toast("Créneau proposé. Les autres peuvent te rejoindre.");
      rafraichirApresPlan();
    } catch (err) { toast(err.message); }
  } else if (f.classList.contains("ecrire")) {
    const texte = f.texte.value.trim();
    if (!texte) return;
    try {
      await api(`/api/plans/${f.dataset.plan}/messages`, { texte });
      rafraichirApresPlan();
    } catch (err) { toast(err.message); }
  }
});

document.addEventListener("change", (e) => { if (e.target.id === "rayon") sauvegarder(); });

document.addEventListener("keydown", (e) => { if (e.key === "Escape" && feuille) fermerFeuille(); });

document.addEventListener("input", (e) => {
  const id = e.target.id;
  if (id === "champ-prenom") {
    etat.prenom = e.target.value;
    const b = document.querySelector('[data-action="commencer"]');
    if (b) b.disabled = !etat.prenom.trim();
    if (!etat.avatar) rafraichirApercuInscription();
  } else if (id === "champ-ville") {
    rechercherVille(e.target.value.trim());
  } else if (id === "champ-ville-pub") {
    rechercherVille(e.target.value.trim(), "-pub");
  } else if (id === "rayon") {
    majRayon(e.target);
  } else if (id === "recherche-ami") {
    rechercherAmi(e.target.value.trim());
  } else if (id === "recherche-vu") {
    rechercherVu(e.target.value.trim());
  }
});
// curseurs noUiSlider : voir monterComposants()
document.documentElement.classList.toggle("anime", MOUVEMENT);

// ------------------------------------------------------------------ //
// Démarrage                                                            //
// ------------------------------------------------------------------ //
/** Écran de démarrage (index.html) : animé en CSS (ressort), il s'ouvre vers l'application après 1,4 s. */
const debutSplash = performance.now();
function fermerSplash() {
  const splash = document.getElementById("splash");
  if (!splash) return;
  const reste = Math.max(0, (MOUVEMENT ? 1400 : 300) - (performance.now() - debutSplash));
  setTimeout(() => {
    splash.classList.add("splash-sortie");
    setTimeout(() => splash.remove(), 650);
  }, reste);
}

// PWA : service worker minimal (coquille hors ligne) ; ignoré si non pris en charge
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js").catch(() => {}));
}

(async function demarrer() {
  restaurer();
  try {
    [CONFIG, agenda, LOGO] = await Promise.all([api("/api/config"), api("/api/agenda"),
      fetch("/icons/logo-ofk.svg").then((r) => r.text()).catch(() => "ofk?"), avatarsPrets]);
  } catch (_) {
    $("#ecran").innerHTML = `<div class="vide" style="margin-top:40vh">Serveur injoignable. Lance <code>uvicorn backend.main:app</code>.</div>`;
    return;
  }
  if (!ONGLETS.some((o) => o.id === etat.onglet)) etat.onglet = "pour-vous";
  normaliserHorizon();
  if (etat.uid) {
    // le compte existe-t-il encore côté serveur (base réinitialisée) ?
    // Seul un 401 (compte absent de la base) fait oublier l'identifiant : un serveur qui redémarre (mise à jour,
    // réveil de Render ou de Neon) ne doit jamais faire recréer un profil vierge.
    try { await api("/api/utilisateurs/moi"); } catch (e) {
      if (e.status === 401) {  // compte absent de la base : retour à la connexion
        etat = { ...etat, uid: null };
        modeAuth = "connexion";
        setTimeout(() => toast("Session expirée : reconnecte-toi avec ton prénom et ton mot de passe."), 1600);
      }
    }
  }
  if (etat.uid) { charger(); chargerSocial(); } else rendre();
  fermerSplash();
  setInterval(rafraichirAgenda, 60000);  // « il y a X min » reste juste
  setInterval(synchroniser, INTERVALLE_SYNC);  // amis, humeurs, plans : seulement si l'appli est visible
  setTimeout(synchroniser, 1500);
})();
