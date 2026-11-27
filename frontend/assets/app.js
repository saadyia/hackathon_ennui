// ennui. — application (JavaScript vanilla, module ES, aucune dépendance externe).
import { icone } from "./icones.js";

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
  cinema: "clapperboard", expo: "landmark", scene: "music", nature: "trees", rencontres: "messages-square",
  series: "tv", jeux: "gamepad-2", cuisine: "chef-hat", creatif: "palette", lecture: "book-open", cafe: "coffee", sport: "bike",
};
// Questionnaire : l'énergie choisit l'onglet d'arrivée, la curiosité règle le curseur Découverte.
const ENERGIES = [
  { id: "cocon", nom: "Mode cocon", icone: "popcorn", onglet: "ecrans" },
  { id: "mixte", nom: "Un peu des deux", icone: "sparkles", onglet: "pour-vous" },
  { id: "dehors", nom: "Envie de sortir", icone: "compass", onglet: "sorties" },
];
const CURIOSITES = [
  { id: 0.1, nom: "Des valeurs sûres" },
  { id: 0.3, nom: "Un peu des deux" },
  { id: 0.7, nom: "Surprends-moi" },
];
const ONGLETS = [
  { id: "pour-vous", nom: "Pour vous", icone: "sparkles" },
  { id: "ecrans", nom: "Films & Séries", icone: "clapperboard" },
  { id: "sorties", nom: "Sorties", icone: "ticket" },
  { id: "profil", nom: "Profil", icone: "user" },
];

// ------------------------------------------------------------------ //
// État, comptes et persistance                                         //
// ------------------------------------------------------------------ //
const PREFS_INITIALES = () => ({ ville: null, rayon: 15, budget: "tous", categories: [], genres: [], plateformes: [] });
const ETAT_INITIAL = () => ({
  uid: null, prenom: "",
  prefs: PREFS_INITIALES(),
  horizon: "semaine",
  dejaVus: [],          // [{ id, titre, type }]
  decouverte: 0.3,
  energie: null,        // questionnaire : "cocon" | "mixte" | "dehors"
  onglet: "pour-vous",
  ecrans: "tout",
});
let etat = ETAT_INITIAL();
let CONFIG = null;
let donnees = {};
let controleur = null;
let cleQuota = null;
let feuille = null;     // feuille collaborative ouverte : { oeuvre, plans }
let agenda = null;      // état de la synchronisation de l'agenda
let etape = "bienvenue"; // "bienvenue" à chaque ouverture, puis "questionnaire" (sans compte) ou "application"

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
}

/** Profil côté serveur (SQLite) : prénom, ville et préférences, pour changer d'appareil ou de compte. */
const synchroniserProfil = debounce(() => {
  if (!etat.uid) return;
  const { ville, ...prefs } = etat.prefs;
  api("/api/utilisateurs/moi", { prenom: etat.prenom, ville, prefs: { ...prefs, horizon: etat.horizon, dejaVus: etat.dejaVus } }, undefined, "PUT")
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
    throw new Error(detail);
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

const genresFr = (o, n = 2) => (o.genres || []).slice(0, n).map((g) => GENRES_FR[g] || g).join(", ");
const nbPepites = () => Math.round(etat.decouverte * 10);
const km = (x) => `${x < 10 ? x.toFixed(1) : Math.round(x)} km`.replace(".", ",");
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

const tarif = (o) => o.tarif || "Tarif non communiqué";

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
      <span class="surtitre">${o.type === "serie" ? "Série" : "Film"}</span>
      <div><strong>${esc(o.titre)}</strong><div class="annee">${o.annee ?? ""}</div></div>
    </div>`;
  const srcset = o.affiche_mini ? ` srcset="${esc(o.affiche_mini)} 210w, ${esc(o.affiche)} 680w" sizes="180px"` : "";
  const img = o.affiche ? `<img src="${esc(o.affiche_mini || o.affiche)}"${srcset} alt="" loading="lazy" decoding="async" onerror="this.remove()">` : "";
  return `<div class="visuel affiche">${typo}${img}${tagDecouverte(o)}</div>`;
}

function visuelSortie(o, format = "paysage") {
  const fond = `background: radial-gradient(120% 90% at 20% 0%, #26262C 0%, #141417 70%)`;
  const img = o.affiche ? `<img src="${esc(o.affiche)}" alt="" loading="lazy" decoding="async" onerror="this.remove()">` : "";
  const credit = o.affiche && o.credit_image ? `<span class="credit">© ${esc(o.credit_image)}</span>` : "";
  return `<div class="visuel ${format}" style="${fond}">
      <div class="visuel-icone">${icone(ICONES_CATEGORIE[o.categorie] || "compass", 40)}</div>${img}${credit}${tagDecouverte(o)}
    </div>`;
}

function lignePlateformes(o) {
  if (!o.plateformes_verifiees) return `<div class="plateformes"><span class="non-verifie">Disponibilité non vérifiée</span></div>`;
  if (!o.plateformes?.length) return `<div class="plateformes"><span class="non-verifie">Hors abonnements suivis</span></div>`;
  return `<div class="plateformes">${o.plateformes.filter((p) => p in NOMS_PLATEFORMES).map((p) =>
    `<span class="plateforme ${etat.prefs.plateformes.includes(p) ? "possedee" : ""}">${esc(NOMS_PLATEFORMES[p])}</span>`).join("")}</div>`;
}

/** « Avec Chloé, Théo et 2 autres » (soi-même affiché « toi »). */
function avecQui(plan) {
  const noms = plan.participants.map((n, i) => (plan.je_participe && n === etat.prenom && i === plan.participants.indexOf(etat.prenom) ? "toi" : n));
  if (noms.length <= 2) return `Avec ${noms.join(" et ")}`;
  return `Avec ${noms.slice(0, 2).join(", ")} et ${noms.length - 2} autre${noms.length > 3 ? "s" : ""}`;
}

/** Ligne collaborative d'une carte : remplace l'ancien compteur. */
function ligneCollab(o, { compacte = false } = {}) {
  const plan = (o.plans || [])[0];
  const id = esc(o.id);
  if (!plan) {
    return `<div class="collab ${compacte ? "compacte" : ""}">
        ${compacte ? "" : `<span class="collab-texte tres-muet">Personne encore. Lance le premier plan.</span>`}
        <button class="bouton-ligne" data-action="ouvrir-plans" data-id="${id}">${icone("plus", 14)}${compacte ? "Organiser" : "Proposer un créneau"}</button>
      </div>`;
  }
  const quand = libelleInstant(new Date(plan.debut));
  const autres = o.plans.length > 1 ? ` · +${o.plans.length - 1} créneau${o.plans.length > 2 ? "x" : ""}` : "";
  const bouton = plan.je_participe
    ? `<button class="bouton-ligne" aria-pressed="true" data-action="ouvrir-plans" data-id="${id}">${icone("check", 14)}Inscrit</button>`
    : `<button class="bouton-ligne bouton-accent" data-action="rejoindre" data-plan="${plan.id}" data-id="${id}">${icone("users", 14)}Rejoindre</button>`;
  return `<div class="collab ${compacte ? "compacte" : ""}">
      <button class="collab-texte" data-action="ouvrir-plans" data-id="${id}">
        <span class="collab-quand">${esc(quand)}${esc(autres)}</span>
        <span class="tres-muet">${esc(avecQui(plan))}</span>
      </button>
      ${bouton}
    </div>`;
}

function carteOeuvre(o, i = 0) {
  const meta = [o.annee, genresFr(o)].filter(Boolean).join(" · ");
  return `<article class="carte-oeuvre apparition" data-carte="${esc(o.id)}" style="animation-delay:${i * 25}ms">
      ${affiche(o)}
      <span class="type-oeuvre">${o.type === "serie" ? "Série" : "Film"}</span>
      <h3>${esc(o.titre)}</h3>
      <div class="meta">${esc(meta)}</div>
      ${lignePlateformes(o)}
      ${ligneCollab(o, { compacte: true })}
      <div class="carte-actions">
        <button class="bouton-ligne" data-action="deja-vu" data-id="${esc(o.id)}">${icone("eye", 14)}Déjà vu</button>
      </div>
    </article>`;
}

function carteSortie(o, i = 0) {
  const lieu = [o.lieu && o.lieu !== o.titre ? o.lieu : null, o.ville].filter(Boolean).join(", ");
  const distance = o.distance_km != null ? `<span class="distance">à ${km(o.distance_km)}</span>` : "";
  return `<article class="carte-sortie apparition" data-carte="${esc(o.id)}" style="animation-delay:${i * 30}ms">
      ${visuelSortie(o)}
      <div class="carte-sortie-corps">
        <div class="carte-sortie-tete">
          <span class="categorie">${icone(ICONES_CATEGORIE[o.categorie] || "compass", 14)}${esc(o.categorie_libelle || "")}</span>
          ${distance}
        </div>
        <h3>${esc(o.titre)}</h3>
        <div class="ligne-info date">${icone("calendar", 15)}<span>${esc(libelleDate(o))}</span></div>
        <div class="ligne-info">${icone("map-pin", 15)}<span>${esc(lieu)}</span></div>
        ${o.acces ? `<div class="ligne-info">${icone("train-front", 15)}<span>${esc(o.acces)}</span></div>` : ""}
        <div class="ligne-info">${icone("ticket", 15)}<span class="tarif">${esc(tarif(o))}</span></div>
        <div class="carte-sortie-pied">${ligneCollab(o)}</div>
      </div>
    </article>`;
}

const valeurCurseur = (n) => n === 0 ? "Valeurs sûres uniquement"
  : n === 10 ? "<b>Découverte totale</b> · hors de tes genres" : `<b>${n}</b> découverte${n > 1 ? "s" : ""} sur 10`;

function instrument() {
  const n = nbPepites();
  const pct = etat.decouverte * 100;
  return `<div class="instrument">
      <div class="instrument-tete">
        <span class="surtitre">Réglage</span>
        <span class="instrument-valeur" id="valeur-curseur">${valeurCurseur(n)}</span>
      </div>
      <div class="piste">
        <div class="piste-ligne"></div>
        <div class="piste-remplie" id="piste-remplie" style="width:calc((100% - 18px) * ${pct / 100})"></div>
        <div class="piste-graduations">${"<i></i>".repeat(11)}</div>
        <input class="curseur" id="curseur" type="range" min="0" max="100" step="1" value="${Math.round(pct)}"
               aria-label="Zone de confort ou découverte" aria-valuetext="${n} découvertes sur 10">
      </div>
      <div class="instrument-pied"><span>Zone de confort</span><span>Découverte</span></div>
    </div>`;
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
          <div class="rayon-tete"><span class="surtitre">Rayon</span><span class="instrument-valeur" id="valeur-rayon">${etat.prefs.rayon} km</span></div>
          <input class="reglette" id="rayon" type="range" min="5" max="50" step="5" value="${etat.prefs.rayon}" aria-label="Rayon de recherche en kilomètres">
          <div class="instrument-pied"><span>5 km</span><span>50 km</span></div>
        </div>` : `<p class="tres-muet petit" style="margin:8px 2px 0">Sans ville, on te montre les sorties partout en France.</p>`}
    </div>`;
}

const selecteurHorizon = () => `<div class="puces defilement" role="group" aria-label="Quand ?">
    ${CONFIG.horizons.map((h) => `<button class="puce puce-s" data-action="horizon" data-valeur="${h.id}" aria-pressed="${etat.horizon === h.id}">
      ${h.id === "maintenant" ? icone("clock", 14) : ""}${esc(h.nom)}</button>`).join("")}
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

function entete(surtitre, titre) {
  return `<header class="apparition">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <span class="marque">On fait koi<span> ?</span></span>
        <span class="surtitre">${esc(surtitre)}</span>
      </div>
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
  const budget = etat.prefs.budget !== "tous" ? " Le filtre budget écarte aussi les sorties sans tarif publié." : "";
  return `<div class="vide">Aucune sortie à venir avec ces filtres. Élargis le rayon, l'horizon ou le budget.${budget}<br>${suggestion}</div>`;
}

function videEcrans() {
  if (etat.prefs.budget !== "tous" && !CONFIG.plateformes_verifiees) {
    return `<div class="vide">Impossible de garantir « ${esc(CONFIG.budgets.find((b) => b.id === etat.prefs.budget).nom)} » :
      les disponibilités sur tes abonnements ne sont pas encore vérifiées. Repasse sur « Tous les prix ».</div>`;
  }
  return `<div class="vide">Rien ne correspond. Ajoute un abonnement dans le profil ou élargis le budget.</div>`;
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

function preferences({ ville = true } = {}) {
  const noteTmdb = CONFIG.plateformes_verifiees ? "" :
    `<p class="tres-muet petit" style="margin:10px 2px 0">Disponibilités en cours de vérification : le filtre s'appliquera dès que les plateformes seront confirmées.</p>`;
  return (ville ? sectionVille() : "")
    + groupePuces("Envie de…", "categories", CONFIG.categories)
    + sectionGenres()
    + groupePuces("Tes abonnements", "plateformes", CONFIG.plateformes) + noteTmdb;
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
      <span class="marque">On fait koi<span> ?</span></span>
      <div class="bienvenue-centre">
        <h1 class="titre-1 bienvenue-titre">Salut !<br>On fait koi aujourd'hui ?</h1>
        <p class="muet bienvenue-texte">Pas besoin de savoir : laisse-toi guider selon ton énergie, tes goûts et ce qu'il se passe près de chez toi.</p>
      </div>
      <button class="bouton-principal" data-action="c-est-parti">C'est parti ! ${icone("arrow-right", 18)}</button>
    </div>`;
}

function ecranAccueil() {
  const connus = comptes();
  return `<div class="apparition">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <span class="marque">On fait koi<span> ?</span></span>
        <button class="lien-discret" data-action="retour-bienvenue">${icone("arrow-left", 16)}Retour</button>
      </div>
      <h1 class="titre-1" style="font-size:34px;margin-top:40px">Dis-nous tout.</h1>
      <p class="muet" style="margin:14px 0 0">Quelques questions sur tes goûts et tes envies du moment. Rien n'est obligatoire, à part ton prénom.</p>
      ${connus.length ? `<div class="reprendre">
          <span class="tres-muet petit">Déjà venu sur cet appareil ?</span>
          <div class="puces" style="margin-top:8px">${connus.map((c) => `<button class="puce" data-action="changer-compte" data-uid="${esc(c.id)}">
            ${icone("user", 14)}${esc(c.prenom)}</button>`).join("")}</div>
        </div>` : ""}
      <section class="groupe">
        <span class="surtitre">Ton prénom</span>
        <input class="champ" id="champ-prenom" maxlength="30" autocomplete="given-name" placeholder="Ex. Chloé" value="${esc(etat.prenom)}">
      </section>
      ${sectionVille()}
      ${groupeChoix("Ton énergie du moment", "energie", ENERGIES)}
      ${groupeChoix("Pour quand ?", "horizon", CONFIG.horizons)}
      ${groupeChoix("Côté curiosité", "decouverte", CURIOSITES)}
      ${preferences({ ville: false })}
    </div>
    <div class="barre-action">
      <button class="bouton-principal" data-action="commencer" ${etat.prenom.trim() ? "" : "disabled"}>Découvrir ma sélection ${icone("arrow-right", 18)}</button>
    </div>`;
}

function ecranPourVous() {
  const d = donnees;
  const une = d.sorties?.find((o) => o.affiche) || null;
  const autres = (d.sorties || []).filter((o) => o !== une);
  const ecrans = d.ecrans || [];
  const rayon = etat.prefs.ville ? ` · ${etat.prefs.rayon} km` : "";
  return `${entete(dateDuJour(), `Salut ${etat.prenom}, qu'est-ce qu'on fait aujourd'hui ?`)}
    ${instrument()}
    <div style="margin-top:12px">${selecteurBudget()}</div>
    <div id="contenu" class="${d.chargement ? "chargement" : ""}">
      <div class="titre-section"><h2 class="titre-2">À l'écran ce soir</h2>
        <button class="lien-discret" data-action="onglet" data-onglet="ecrans">Tout voir ${icone("chevron-right", 16)}</button></div>
      ${ecrans.length ? `<div class="carrousel">${ecrans.map(carteOeuvre).join("")}</div>`
        : d.chargement ? squelettesAffiches(2) : videEcrans()}
      <div class="titre-section"><h2 class="titre-2">Sortir · ${esc(nomVille())}${esc(rayon)}</h2>
        <button class="lien-discret" data-action="onglet" data-onglet="sorties">Tout voir ${icone("chevron-right", 16)}</button></div>
      ${selecteurHorizon()}
      ${une ? `<article class="une apparition" data-carte="${esc(une.id)}">
          ${visuelSortie(une, "")}
          <div class="une-texte">
            <span class="categorie">${icone(ICONES_CATEGORIE[une.categorie] || "compass", 14)}${esc(une.categorie_libelle || "")} · ${esc(une.ville || "")}${une.distance_km != null ? ` · à ${km(une.distance_km)}` : ""}</span>
            <h2>${esc(une.titre)}</h2>
            <div class="muet petit">${esc(libelleDate(une))} · ${esc(tarif(une))}</div>
            <div style="margin-top:12px">${ligneCollab(une)}</div>
          </div>
        </article>` : ""}
      <div style="margin-top:14px">${autres.length ? autres.map(carteSortie).join("")
        : une ? "" : d.chargement ? squelettesSorties(1) : videSorties()}</div>
    </div>`;
}

function ecranEcrans() {
  const d = donnees;
  const liste = d.grille || [];
  const surtitre = { tout: "Films & Séries", film: "Films", serie: "Séries" }[etat.ecrans];
  return `${entete(surtitre, "Ce soir, à l'écran")}
    <div class="segment segment-3" role="group" aria-label="Type de contenu">
      <button data-action="segment" data-valeur="tout" aria-pressed="${etat.ecrans === "tout"}">Tout</button>
      <button data-action="segment" data-valeur="film" aria-pressed="${etat.ecrans === "film"}">${icone("film", 16)}Films</button>
      <button data-action="segment" data-valeur="serie" aria-pressed="${etat.ecrans === "serie"}">${icone("tv", 16)}Séries</button>
    </div>
    <div style="margin-top:12px">${selecteurBudget()}</div>
    ${instrument()}
    <div id="contenu" class="${d.chargement ? "chargement" : ""}" style="margin-top:26px">
      ${liste.length ? `<div class="grille-affiches">${liste.map(carteOeuvre).join("")}</div>`
        : d.chargement ? squelettesAffiches(4) : videEcrans()}
    </div>`;
}

function ecranSorties() {
  const d = donnees;
  const liste = d.grille || [];
  return `${entete("Sorties", "Sortir près de chez toi")}
    ${statutAgenda()}
    <div style="margin-top:16px">${localisation()}</div>
    <div style="margin-top:14px">${selecteurHorizon()}</div>
    <div style="margin-top:12px">${selecteurBudget()}</div>
    <div class="puces defilement" style="margin-top:8px">${CONFIG.categories.filter((c) => c.sorties).map((c) => `<button class="puce" data-action="pref"
        data-groupe="categories" data-valeur="${esc(JSON.stringify(c.id))}" aria-pressed="${etat.prefs.categories.includes(c.id)}">
        ${icone(ICONES_CATEGORIE[c.id], 15)}${esc(c.nom)}</button>`).join("")}</div>
    ${instrument()}
    <div id="contenu" class="${d.chargement ? "chargement" : ""}" style="margin-top:22px">
      ${liste.length ? liste.map(carteSortie).join("") : d.chargement ? squelettesSorties(2) : videSorties()}
    </div>`;
}

function ecranProfil() {
  const vus = etat.dejaVus;
  const mesPlans = donnees.mesPlans;
  const autres = comptes().filter((c) => c.id !== etat.uid);
  return `${entete("Profil", etat.prenom)}
    <div class="compte">
      <span class="muet">Connecté sur cet appareil</span>
      <div class="puces" style="margin-top:10px">
        ${autres.map((c) => `<button class="puce" data-action="changer-compte" data-uid="${esc(c.id)}">${icone("user", 14)}${esc(c.prenom)}</button>`).join("")}
        <button class="puce" data-action="nouveau-compte">${icone("plus", 14)}Nouveau compte</button>
      </div>
    </div>
    <section class="groupe">
      <span class="surtitre">Mes plans</span>
      ${mesPlans === undefined ? `<div class="squelette" style="height:64px"></div>`
        : mesPlans.length ? `<div class="liste-vus"><ul>${mesPlans.map((p) => `<li>
            ${icone(p.oeuvre_type === "sortie" ? "ticket" : p.oeuvre_type === "serie" ? "tv" : "film", 16, "tres-muet")}
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
      <span class="surtitre">Déjà vus · ${vus.length}</span>
      <div class="liste-vus">${vus.length ? `<ul>${vus.map((o) => `<li>
          ${icone(o.type === "serie" ? "tv" : "film", 16, "tres-muet")}
          <span class="titre">${esc(o.titre)}</span>
          <button class="bouton-icone" data-action="retirer-vu" data-id="${esc(o.id)}" aria-label="Retirer ${esc(o.titre)}">${icone("x", 14)}</button>
        </li>`).join("")}</ul>` : `<div class="vide">Touche « Déjà vu » sur un film ou une série : on s'en servira pour affiner tes recommandations.</div>`}</div>
      <input class="champ" id="recherche-vu" type="search" placeholder="Ajouter un film ou une série déjà vu…" autocomplete="off" style="margin-top:12px">
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
  const d = new Date();
  const ce_soir = new Date(`${jourParis(d)}T21:00:00`);
  // 21h heure de Paris ≈ 21h locale pour un public en France ; sinon demain
  return ce_soir > d ? ce_soir : new Date(ce_soir.getTime() + 864e5);
}

function rendreFeuille() {
  const racine = $("#feuille");
  if (!feuille) { racine.hidden = true; racine.innerHTML = ""; return; }
  const { oeuvre: o, plans } = feuille;
  const estSortie = o.type === "sortie";
  const plansHtml = plans === null ? `<div class="squelette" style="height:90px"></div>`
    : plans.length ? plans.map((p) => `<div class="plan">
        <div class="plan-tete">
          <div>
            <div class="plan-quand">${esc(libelleInstant(new Date(p.debut)))}</div>
            <div class="tres-muet petit">${esc(avecQui(p))} · proposé par ${esc(p.auteur)}</div>
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
  racine.hidden = false;
  racine.innerHTML = `<div class="feuille-fond" data-action="fermer-feuille"></div>
    <section class="feuille-panneau" role="dialog" aria-modal="true" aria-label="Organiser ${esc(o.titre)}">
      <div class="feuille-tete">
        <div style="min-width:0">
          <span class="surtitre">${estSortie ? "Sortie à plusieurs" : "Watch-party"}</span>
          <h2 class="titre-2" style="margin-top:4px">${esc(o.titre)}</h2>
        </div>
        <button class="bouton-icone" data-action="fermer-feuille" aria-label="Fermer">${icone("x", 16)}</button>
      </div>
      <div class="feuille-corps">
        ${plansHtml}
        <form class="proposer" id="form-plan">
          <span class="surtitre">Proposer un créneau</span>
          <label class="petit muet">Quand
            <input class="champ" type="datetime-local" name="debut" required value="${esc(valeurLocale(creneauParDefaut(o)))}" min="${esc(valeurLocale(new Date()))}">
          </label>
          <label class="petit muet">${estSortie ? "Point de rendez-vous" : "Lien de la watch-party"}
            <input class="champ" name="rendez_vous" maxlength="200"
              placeholder="${estSortie ? "Devant la gare, le campus, l'entrée…" : "Lien Discord, Teleparty… (https://)"}">
          </label>
          <label class="petit muet">Un mot (facultatif)
            <input class="champ" name="message" maxlength="280" placeholder="${estSortie ? "On y va ensemble ?" : "On lance l'épisode à 21h ?"}">
          </label>
          <button class="bouton-principal" type="submit">${icone("plus", 18)}Proposer ce créneau</button>
        </form>
      </div>
    </section>`;
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
  ecran.innerHTML = ECRANS[etat.onglet]();
}

function rendreContenu() {
  const zone = $("#contenu");
  if (!zone) return rendre();
  const tmp = document.createElement("div");
  tmp.innerHTML = ECRANS[etat.onglet]();
  const nouvelle = tmp.querySelector("#contenu");
  if (nouvelle) zone.replaceWith(nouvelle);
}

function corps(type, k) {
  const v = etat.prefs.ville;
  return {
    type, k,
    genres: etat.prefs.genres,
    deja_vus: etat.dejaVus.map((o) => o.id),
    decouverte: etat.decouverte,
    plateformes: etat.prefs.plateformes,
    lat: v?.lat ?? null,
    lon: v?.lon ?? null,
    rayon_km: etat.prefs.rayon,
    horizon: etat.horizon,
    budget: etat.prefs.budget,
    categories: etat.prefs.categories,
  };
}

async function couvertureSiVide(sorties, signal) {
  const v = etat.prefs.ville;
  if (sorties.length || !v) return null;
  try { return await api(`/api/couverture?lat=${v.lat}&lon=${v.lon}`, undefined, signal); } catch (_) { return null; }
}

async function charger({ partiel = false } = {}) {
  if (!etat.uid) return;
  if (etat.onglet === "profil") { rendre(); chargerMesPlans(); return; }
  controleur?.abort();
  controleur = new AbortController();
  const signal = controleur.signal;
  cleQuota = `${etat.onglet}:${etat.ecrans}:${nbPepites()}`;
  donnees = { ...donnees, chargement: true };
  partiel ? $("#contenu")?.classList.add("chargement") : rendre();
  try {
    if (etat.onglet === "pour-vous") {
      const [ecrans, sorties] = await Promise.all([
        api("/api/recommandations", corps("tout", 9), signal),
        api("/api/recommandations", corps("sortie", 6), signal),
      ]);
      donnees = { ecrans, sorties, couverture: await couvertureSiVide(sorties, signal) };
    } else if (etat.onglet === "ecrans") {
      donnees = { grille: await api("/api/recommandations", corps(etat.ecrans, 20), signal) };
    } else if (etat.onglet === "sorties") {
      const grille = await api("/api/recommandations", corps("sortie", 20), signal);
      donnees = { grille, couverture: await couvertureSiVide(grille, signal) };
    }
  } catch (e) {
    if (e.name === "AbortError") return;
    donnees = { erreur: true };
    toast("Le serveur ne répond pas.");
  }
  partiel ? rendreContenu() : rendre();
}

async function chargerMesPlans() {
  try { donnees = { ...donnees, mesPlans: await api("/api/mes-plans") }; } catch (_) { donnees = { ...donnees, mesPlans: [] }; }
  if (etat.onglet === "profil" && !feuille) rendre();
}

const chargerSiQuotaChange = debounce(() => {
  if (`${etat.onglet}:${etat.ecrans}:${nbPepites()}` !== cleQuota) charger({ partiel: true });
}, 60);
const chargerApresRayon = debounce(() => charger({ partiel: true }), 150);

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
function memoriserCompte(id, prenom) {
  const liste = comptes().filter((c) => c.id !== id);
  stock.ecrire("comptes", [{ id, prenom }, ...liste].slice(0, 8));
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
  } catch (_) {
    if (!local) {
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
    horizon: local?.horizon || prefsServeur.horizon || "semaine",
  };
  delete etat.prefs.dejaVus;
  delete etat.prefs.horizon;
  normaliserHorizon();
  memoriserCompte(uid, etat.prenom);
  stock.ecrire("actif", uid);
  sauvegarder();
  donnees = {};
  haut();
  toast(`Bonjour ${etat.prenom}`);
  charger();
}

// ------------------------------------------------------------------ //
// Actions                                                              //
// ------------------------------------------------------------------ //
const actions = {
  pref(b) {
    const { groupe } = b.dataset;
    const valeur = JSON.parse(b.dataset.valeur);
    const liste = etat.prefs[groupe];
    etat.prefs[groupe] = liste.includes(valeur) ? liste.filter((v) => v !== valeur) : [...liste, valeur];
    sauvegarder();
    if (!etat.uid || etat.onglet === "profil") b.setAttribute("aria-pressed", etat.prefs[groupe].includes(valeur));
    else charger();
  },
  budget(b) {
    if (etat.prefs.budget === b.dataset.valeur) return;
    etat.prefs.budget = b.dataset.valeur;
    sauvegarder();
    charger();
  },
  horizon(b) {
    if (etat.horizon === b.dataset.valeur) return;
    etat.horizon = b.dataset.valeur;
    sauvegarder();
    charger();
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
    b.disabled = true;
    try {
      const { ville, ...prefs } = etat.prefs;
      const u = await api("/api/utilisateurs", { prenom, ville, prefs: { ...prefs, horizon: etat.horizon } });
      etat.uid = u.id;
      etat.prenom = u.prenom;
      etat.onglet = ENERGIES.find((e) => e.id === etat.energie)?.onglet || "pour-vous";
      // envie de séries sans envie de cinéma : Films & Séries s'ouvre sur les séries
      const cats = etat.prefs.categories;
      if (cats.includes("series") && !cats.includes("cinema")) etat.ecrans = "serie";
      memoriserCompte(u.id, u.prenom);
      sauvegarder();
      haut();
      charger();
    } catch (e) {
      b.disabled = false;
      toast(`Connexion impossible : ${e.message}`);
    }
  },
  "changer-compte"(b) { changerCompte(b.dataset.uid); },
  "c-est-parti"() {
    etape = etat.uid ? "application" : "questionnaire";  // compte connu : directement à la sélection
    haut();
    rendre();
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
    etat.onglet = b.dataset.onglet;
    sauvegarder();
    donnees = {};
    haut();
    charger();
  },
  segment(b) {
    if (etat.ecrans === b.dataset.valeur) return;
    etat.ecrans = b.dataset.valeur;
    sauvegarder();
    donnees = {};
    charger();
  },
  "deja-vu"(b) {
    const id = b.dataset.id;
    const o = trouver(id);
    if (!o || etat.dejaVus.some((v) => v.id === id)) return;
    etat.dejaVus.push({ id, titre: o.titre, type: o.type });
    sauvegarder();
    b.closest("[data-carte]")?.classList.add("sortante");
    toast(`« ${o.titre} » ajouté à tes déjà vus · sélection ajustée`);
    setTimeout(() => charger({ partiel: true }), 260);
  },
  "ouvrir-plans"(b) {
    const o = trouver(b.dataset.id) || { id: b.dataset.id, titre: b.dataset.titre, type: b.dataset.type };
    ouvrirFeuille(o);
  },
  "fermer-feuille"() { feuille = null; rendreFeuille(); },
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
const rechercherVille = debounce(async (q) => {
  const liste = $("#suggestions-ville");
  if (!liste) return;
  if (q.length < 2) { liste.hidden = true; return; }
  try { resultatsVille = (await api(`/api/communes?q=${encodeURIComponent(q)}`)).communes; } catch (_) { resultatsVille = []; }
  liste.innerHTML = resultatsVille.length
    ? resultatsVille.map((c, i) => `<li><button data-action="choisir-ville" data-index="${i}">
        ${icone("map-pin", 16, "tres-muet")}<span style="flex:1">${esc(c.nom)}</span>
        <span class="tres-muet petit">${esc(c.code_postal || "")}</span></button></li>`).join("")
    : `<li class="vide">Aucune commune trouvée</li>`;
  liste.hidden = false;
}, 250);

let resultatsRecherche = [];
const rechercherVu = debounce(async (q) => {
  const liste = $("#suggestions-vu");
  if (!liste) return;
  if (q.length < 2) { liste.hidden = true; return; }
  try { resultatsRecherche = await api(`/api/oeuvres?q=${encodeURIComponent(q)}&limite=6`); } catch (_) { resultatsRecherche = []; }
  liste.innerHTML = resultatsRecherche.length
    ? resultatsRecherche.map((o, i) => `<li><button data-action="ajouter-vu" data-index="${i}">
        ${icone(o.type === "serie" ? "tv" : "film", 16, "tres-muet")}<span style="flex:1">${esc(o.titre)}</span>
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
});

document.addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  if (f.id === "form-plan" && feuille) {
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

document.addEventListener("keydown", (e) => { if (e.key === "Escape" && feuille) actions["fermer-feuille"](); });

document.addEventListener("input", (e) => {
  const id = e.target.id;
  if (id === "curseur") {
    etat.decouverte = Number(e.target.value) / 100;
    const n = nbPepites();
    $("#valeur-curseur").innerHTML = valeurCurseur(n);
    $("#piste-remplie").style.width = `calc((100% - 18px) * ${etat.decouverte})`;
    e.target.setAttribute("aria-valuetext", `${n} découvertes sur 10`);
    chargerSiQuotaChange();
  } else if (id === "rayon") {
    etat.prefs.rayon = Number(e.target.value);
    $("#valeur-rayon").textContent = `${etat.prefs.rayon} km`;
    if (etat.uid && etat.onglet !== "profil") chargerApresRayon();
  } else if (id === "champ-prenom") {
    etat.prenom = e.target.value;
    const b = document.querySelector('[data-action="commencer"]');
    if (b) b.disabled = !etat.prenom.trim();
  } else if (id === "champ-ville") {
    rechercherVille(e.target.value.trim());
  } else if (id === "recherche-vu") {
    rechercherVu(e.target.value.trim());
  }
});
document.addEventListener("change", (e) => { if (["curseur", "rayon"].includes(e.target.id)) sauvegarder(); });

// ------------------------------------------------------------------ //
// Démarrage                                                            //
// ------------------------------------------------------------------ //
(async function demarrer() {
  restaurer();
  try {
    [CONFIG, agenda] = await Promise.all([api("/api/config"), api("/api/agenda")]);
  } catch (_) {
    $("#ecran").innerHTML = `<div class="vide" style="margin-top:40vh">Serveur injoignable. Lance <code>uvicorn backend.main:app</code>.</div>`;
    return;
  }
  if (!ONGLETS.some((o) => o.id === etat.onglet)) etat.onglet = "pour-vous";
  normaliserHorizon();
  if (etat.uid) {
    // le compte existe-t-il encore côté serveur (base réinitialisée) ?
    try { await api("/api/utilisateurs/moi"); } catch (_) { etat = { ...etat, uid: null }; }
  }
  if (etat.uid) charger(); else rendre();
  setInterval(rafraichirAgenda, 60000);  // « il y a X min » reste juste
})();
