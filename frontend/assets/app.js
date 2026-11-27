// ennui. — application (JavaScript vanilla, module ES, aucune dépendance externe).
import { icone } from "./icones.js";

// ------------------------------------------------------------------ //
// Constantes                                                           //
// ------------------------------------------------------------------ //
const CLE_STOCKAGE = "ennui.v3";
const FUSEAU = "Europe/Paris";
const NOMS_PLATEFORMES = { 8: "Netflix", 119: "Prime Video", 337: "Disney+", 381: "Canal+", 234: "Arte", 350: "Apple TV+" };
const GENRES_FR = {
  "Sci-Fi": "Science-Fiction", Thriller: "Thriller", Drama: "Drame", Comedy: "Comédie", Animation: "Animation",
  Documentary: "Documentaire", Horror: "Horreur", Action: "Action", Romance: "Romance", Crime: "Policier",
  Fantasy: "Fantastique", Adventure: "Aventure", Mystery: "Mystère", Children: "Jeunesse", Musical: "Musical",
  War: "Guerre", Western: "Western", "Film-Noir": "Film noir",
};
const TEINTES = { // teinte HSL des affiches typographiques, par genre principal
  "Sci-Fi": 212, Thriller: 0, Drama: 28, Comedy: 44, Animation: 275, Documentary: 160, Horror: 340,
  Action: 14, Romance: 325, Crime: 222, Fantasy: 258, Adventure: 120, Mystery: 245, Children: 190,
  Musical: 300, War: 80, Western: 35,
};
const ICONES_CATEGORIE = { cinema: "clapperboard", expo: "landmark", scene: "music", nature: "trees", rencontres: "messages-square" };
const ONGLETS = [
  { id: "pour-vous", nom: "Pour vous", icone: "sparkles" },
  { id: "ecrans", nom: "Films & Séries", icone: "clapperboard" },
  { id: "sorties", nom: "Sorties", icone: "ticket" },
  { id: "profil", nom: "Profil", icone: "user" },
];

// ------------------------------------------------------------------ //
// État et persistance                                                  //
// ------------------------------------------------------------------ //
const ETAT_INITIAL = () => ({
  onboarde: false,
  prefs: { ville: null, rayon: 15, categories: [], genres: [], plateformes: [] }, // ville : { nom, contexte, lat, lon }
  horizon: "semaine",   // "court" | "semaine" | "mois"
  dejaVus: [],          // [{ id, titre, type }]
  interesses: [],       // ids marqués « Intéressé »
  decouverte: 0.3,
  onglet: "pour-vous",
  ecrans: "tout",       // "tout" | "film" | "serie"
});
const etat = ETAT_INITIAL();
let CONFIG = null;
let donnees = {};     // résultats de l'onglet courant
let controleur = null;
let cleQuota = null;

function sauvegarder() {
  try { localStorage.setItem(CLE_STOCKAGE, JSON.stringify(etat)); } catch (_) { /* stockage indisponible */ }
}
function restaurer() {
  try {
    const d = JSON.parse(localStorage.getItem(CLE_STOCKAGE) || "null");
    if (d && typeof d === "object") Object.assign(etat, d, { prefs: { ...etat.prefs, ...(d.prefs || {}) } });
  } catch (_) { /* stockage indisponible ou corrompu : on repart de zéro */ }
}

// ------------------------------------------------------------------ //
// Utilitaires                                                          //
// ------------------------------------------------------------------ //
const $ = (sel) => document.querySelector(sel);
/** Remonte en haut : la page sur mobile, le cadre de l'application sur desktop. */
const haut = () => { window.scrollTo(0, 0); $("#app").scrollTo(0, 0); };
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const debounce = (fn, ms) => { let m; return (...a) => { clearTimeout(m); m = setTimeout(() => fn(...a), ms); }; };

async function api(chemin, corps, signal) {
  const r = await fetch(chemin, corps === undefined ? { signal } : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corps), signal,
  });
  if (!r.ok) throw new Error(`${r.status} ${chemin}`);
  return r.json();
}

let minuteurToast;
function toast(message) {
  const t = $("#toast");
  t.textContent = message;
  t.classList.add("visible");
  clearTimeout(minuteurToast);
  minuteurToast = setTimeout(() => t.classList.remove("visible"), 2200);
}

const genresFr = (o, n = 2) => (o.genres || []).slice(0, n).map((g) => GENRES_FR[g] || g).join(", ");
const nbPepites = () => Math.round(etat.decouverte * 10);
const km = (x) => `${x < 10 ? x.toFixed(1) : Math.round(x)} km`.replace(".", ",");
const nomVille = () => etat.prefs.ville?.nom || "Partout en France";

// ------------------------------------------------------------------ //
// Dates (toujours calculées dans le fuseau Europe/Paris)               //
// ------------------------------------------------------------------ //
const jourParis = (d) => d.toLocaleDateString("fr-CA", { timeZone: FUSEAU }); // AAAA-MM-JJ
const heureParis = (d) => d.toLocaleTimeString("fr-FR", { timeZone: FUSEAU, hour: "2-digit", minute: "2-digit" }).replace(":", "h");
const dateCourte = (d) => {
  const t = d.toLocaleDateString("fr-FR", { timeZone: FUSEAU, weekday: "short", day: "numeric", month: "short" });
  return t.charAt(0).toUpperCase() + t.slice(1);
};
const dateDuJour = () => new Date().toLocaleDateString("fr-FR", { timeZone: FUSEAU, weekday: "long", day: "numeric", month: "long" });

/** « Ce soir · 20h30 », « Demain · 14h00 », « Sam. 28 nov. · 20h30 », « En cours · jusqu'à 22h00 ». */
function libelleDate(o) {
  if (!o.prochaine) return "";
  const debut = new Date(o.prochaine.debut);
  const fin = new Date(o.prochaine.fin);
  const maintenant = new Date();
  const auj = jourParis(maintenant);
  const demain = jourParis(new Date(maintenant.getTime() + 864e5));
  const journeeEntiere = heureParis(debut) === "00h00";
  if (debut <= maintenant) {
    return jourParis(fin) === auj ? `En cours · jusqu'à ${heureParis(fin)}`
      : `En cours · jusqu'au ${fin.toLocaleDateString("fr-FR", { timeZone: FUSEAU, day: "numeric", month: "long" })}`;
  }
  const heure = journeeEntiere ? "" : ` · ${heureParis(debut)}`;
  const heureNum = Number(debut.toLocaleString("fr-FR", { timeZone: FUSEAU, hour: "2-digit", hour12: false }));
  if (jourParis(debut) === auj) return (heureNum >= 17 && !journeeEntiere ? "Ce soir" : "Aujourd'hui") + heure;
  if (jourParis(debut) === demain) return `Demain${heure}`;
  return `${dateCourte(debut)}${heure}`;
}

function tarif(o) { return o.tarif || "Tarif non communiqué"; }

// ------------------------------------------------------------------ //
// Briques visuelles                                                    //
// ------------------------------------------------------------------ //
function affiche(o) {
  const teinte = TEINTES[o.genres?.[0]] ?? 230;
  const fond = `background: linear-gradient(160deg, hsl(${teinte} 32% 24%) 0%, hsl(${teinte} 20% 12%) 55%, #141417 100%)`;
  const typo = `<div class="visuel-typo" style="${fond}">
      <span class="surtitre">${o.type === "serie" ? "Série" : "Film"}</span>
      <div><strong>${esc(o.titre)}</strong><div class="annee">${o.annee ?? ""}</div></div>
    </div>`;
  const srcset = o.affiche_mini ? ` srcset="${esc(o.affiche_mini)} 210w, ${esc(o.affiche)} 680w" sizes="180px"` : "";
  const img = o.affiche ? `<img src="${esc(o.affiche_mini || o.affiche)}"${srcset} alt="" loading="lazy" decoding="async" onerror="this.remove()">` : "";
  const pepite = o.origine === "decouverte" ? `<span class="tag tag-pepite">Pépite</span>` : "";
  return `<div class="visuel affiche">${typo}${img}${pepite}</div>`;
}

function visuelSortie(o, format = "paysage") {
  const fond = `background: radial-gradient(120% 90% at 20% 0%, #26262C 0%, #141417 70%)`;
  const img = o.affiche ? `<img src="${esc(o.affiche)}" alt="" loading="lazy" decoding="async" onerror="this.remove()">` : "";
  const credit = o.affiche && o.credit_image ? `<span class="credit">© ${esc(o.credit_image)}</span>` : "";
  const pepite = o.origine === "decouverte" ? `<span class="tag tag-pepite">Pépite</span>` : "";
  return `<div class="visuel ${format}" style="${fond}">
      <div class="visuel-icone">${icone(ICONES_CATEGORIE[o.categorie] || "compass", 40)}</div>${img}${credit}${pepite}
    </div>`;
}

/** Plateformes : seulement ce que TMDB confirme (FR, abonnement). Jamais de supposition. */
function lignePlateformes(o) {
  if (!o.plateformes_verifiees) return `<div class="plateformes"><span class="non-verifie">Disponibilité non vérifiée</span></div>`;
  if (!o.plateformes?.length) return `<div class="plateformes"><span class="non-verifie">Hors abonnements suivis</span></div>`;
  return `<div class="plateformes">${o.plateformes.filter((p) => p in NOMS_PLATEFORMES).map((p) =>
    `<span class="plateforme ${etat.prefs.plateformes.includes(p) ? "possedee" : ""}">${esc(NOMS_PLATEFORMES[p])}</span>`).join("")}</div>`;
}

function carteOeuvre(o, i = 0) {
  const meta = [o.annee, genresFr(o)].filter(Boolean).join(" · ");
  return `<article class="carte-oeuvre apparition" data-carte="${esc(o.id)}" style="animation-delay:${i * 25}ms">
      ${affiche(o)}
      <span class="type-oeuvre">${o.type === "serie" ? "Série" : "Film"}</span>
      <h3>${esc(o.titre)}</h3>
      <div class="meta">${esc(meta)}</div>
      ${lignePlateformes(o)}
      <div class="carte-actions">
        <button class="bouton-ligne" data-action="deja-vu" data-id="${esc(o.id)}">${icone("eye", 14)}Déjà vu</button>
      </div>
    </article>`;
}

function boutonInteret(o) {
  const actif = etat.interesses.includes(o.id);
  const n = o.interesses;
  return `<button class="bouton-ligne" data-action="interet" data-id="${esc(o.id)}" aria-pressed="${actif}">
      ${icone(actif ? "check" : "users", 14)}Intéressé · ${n} étudiant${n > 1 ? "s" : ""}
    </button>`;
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
        <div class="carte-sortie-pied">
          <span class="tarif">${esc(tarif(o))}</span>
          ${boutonInteret(o)}
        </div>
      </div>
    </article>`;
}

const valeurCurseur = (n) => n === 0 ? "Valeurs sûres uniquement" : `<b>${n}</b> pépite${n > 1 ? "s" : ""} sur 10`;

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
               aria-label="Zone de confort ou découverte" aria-valuetext="${n} pépites sur 10">
      </div>
      <div class="instrument-pied"><span>Zone de confort</span><span>Découverte</span></div>
    </div>`;
}

/** Ville (autocomplétion API Adresse) + rayon. `compact` : version de l'onglet Sorties. */
function localisation({ compact = false } = {}) {
  const v = etat.prefs.ville;
  return `<div class="localisation ${compact ? "compacte" : ""}">
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

function selecteurHorizon() {
  return `<div class="segment segment-3" role="group" aria-label="Quand ?">
      ${CONFIG.horizons.map((h) => `<button data-action="horizon" data-valeur="${h.id}" aria-pressed="${etat.horizon === h.id}">${esc(h.nom)}</button>`).join("")}
    </div>`;
}

function entete(surtitre, titre) {
  return `<header class="apparition">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <span class="marque">ennui<span>.</span></span>
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
  const conseil = etat.prefs.ville && etat.prefs.rayon < 50 ? "Élargis le rayon ou l'horizon." : "Essaie un autre horizon.";
  return `<div class="vide">Aucune sortie à venir avec ces filtres. ${conseil}<br>${suggestion}</div>`;
}

// ------------------------------------------------------------------ //
// Écrans                                                               //
// ------------------------------------------------------------------ //
function groupePuces(titre, groupe, options) {
  return `<section class="groupe">
      <span class="surtitre">${esc(titre)}</span>
      <div class="puces">${options.map((o) => `<button class="puce" data-action="pref" data-groupe="${groupe}"
          data-valeur="${esc(JSON.stringify(o.id))}" aria-pressed="${etat.prefs[groupe].includes(o.id)}">${esc(o.nom)}</button>`).join("")}</div>
    </section>`;
}

function preferences() {
  const noteTmdb = CONFIG.plateformes_verifiees ? "" :
    `<p class="tres-muet petit" style="margin:10px 2px 0">Disponibilités en cours de vérification : le filtre s'appliquera dès que les plateformes seront confirmées.</p>`;
  return `<section class="groupe"><span class="surtitre">Où es-tu ?</span>${localisation()}</section>`
    + groupePuces("Envie de…", "categories", CONFIG.categories)
    + groupePuces("Tes genres favoris", "genres", CONFIG.genres)
    + groupePuces("Tes abonnements", "plateformes", CONFIG.plateformes) + noteTmdb;
}

function ecranAccueil() {
  return `<div class="apparition">
      <span class="marque">ennui<span>.</span></span>
      <p class="surtitre" style="margin:44px 0 0">${esc(dateDuJour())}</p>
      <h1 class="titre-1" style="font-size:36px">Qu'est-ce qu'on fait aujourd'hui&nbsp;?</h1>
      <p class="muet" style="margin:12px 0 0">Quelques préférences, et on te prépare une sélection de films, de séries et de sorties près de chez toi.</p>
      ${preferences()}
    </div>
    <div class="barre-action">
      <button class="bouton-principal" data-action="commencer">Découvrir ma sélection ${icone("arrow-right", 18)}</button>
    </div>`;
}

function ecranPourVous() {
  const d = donnees;
  const une = d.sorties?.find((o) => o.affiche) || null;
  const autres = (d.sorties || []).filter((o) => o !== une);
  const ecrans = d.ecrans || [];
  const rayon = etat.prefs.ville ? ` · ${etat.prefs.rayon} km` : "";
  return `${entete(dateDuJour(), "Qu'est-ce qu'on fait aujourd'hui ?")}
    ${instrument()}
    <div id="contenu" class="${d.chargement ? "chargement" : ""}">
      <div class="titre-section"><h2 class="titre-2">À l'écran ce soir</h2>
        <button class="lien-discret" data-action="onglet" data-onglet="ecrans">Tout voir ${icone("chevron-right", 16)}</button></div>
      ${ecrans.length ? `<div class="carrousel">${ecrans.map(carteOeuvre).join("")}</div>`
        : d.chargement ? squelettesAffiches(2) : `<div class="vide">Rien sur tes plateformes pour l'instant.</div>`}
      <div class="titre-section"><h2 class="titre-2">Sortir · ${esc(nomVille())}${esc(rayon)}</h2>
        <button class="lien-discret" data-action="onglet" data-onglet="sorties">Tout voir ${icone("chevron-right", 16)}</button></div>
      ${selecteurHorizon()}
      ${une ? `<article class="une apparition" data-carte="${esc(une.id)}">
          ${visuelSortie(une, "")}
          <div class="une-texte">
            <span class="categorie">${icone(ICONES_CATEGORIE[une.categorie] || "compass", 14)}${esc(une.categorie_libelle || "")} · ${esc(une.ville || "")}${une.distance_km != null ? ` · à ${km(une.distance_km)}` : ""}</span>
            <h2>${esc(une.titre)}</h2>
            <div class="muet petit">${esc(libelleDate(une))} · ${esc(tarif(une))}</div>
            <div style="margin-top:12px">${boutonInteret(une)}</div>
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
    ${instrument()}
    <div id="contenu" class="${d.chargement ? "chargement" : ""}" style="margin-top:26px">
      ${liste.length ? `<div class="grille-affiches">${liste.map(carteOeuvre).join("")}</div>`
        : d.chargement ? squelettesAffiches(4) : `<div class="vide">Rien sur tes plateformes. Ajoute un abonnement dans le profil.</div>`}
    </div>`;
}

function ecranSorties() {
  const d = donnees;
  const liste = d.grille || [];
  return `${entete("Sorties", "Sortir près de chez toi")}
    <div style="margin-top:20px">${localisation({ compact: true })}</div>
    <div style="margin-top:14px">${selecteurHorizon()}</div>
    <div class="puces defilement" style="margin-top:12px">${CONFIG.categories.map((c) => `<button class="puce" data-action="pref"
        data-groupe="categories" data-valeur="${esc(JSON.stringify(c.id))}" aria-pressed="${etat.prefs.categories.includes(c.id)}">
        ${icone(ICONES_CATEGORIE[c.id], 15)}${esc(c.nom)}</button>`).join("")}</div>
    ${instrument()}
    <div id="contenu" class="${d.chargement ? "chargement" : ""}" style="margin-top:22px">
      ${liste.length ? liste.map(carteSortie).join("") : d.chargement ? squelettesSorties(2) : videSorties()}
    </div>`;
}

function ecranProfil() {
  const vus = etat.dejaVus;
  return `${entete("Profil", "Tes préférences")}
    <p class="muet" style="margin:10px 0 0">Elles orientent toutes tes recommandations. Modifie-les quand tu veux.</p>
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
    <section class="groupe">
      <button class="bouton-ligne" data-action="reinitialiser">${icone("rotate-ccw", 14)}Tout réinitialiser</button>
    </section>
    <p class="sources">
      Sources : sorties <a href="https://openagenda.com" target="_blank" rel="noopener">OpenAgenda</a> (via Opendatasoft) ;
      communes <a href="https://adresse.data.gouv.fr" target="_blank" rel="noopener">API Adresse</a> ;
      séries <a href="https://www.tvmaze.com" target="_blank" rel="noopener">TVmaze</a> (CC BY-SA) ;
      affiches et plateformes <a href="https://www.themoviedb.org" target="_blank" rel="noopener">TMDB</a> (abonnements en France uniquement) ;
      films MovieLens (GroupLens).<br>
      Démo : les compteurs « Intéressé » partent d'une valeur simulée.
    </p>`;
}

const ECRANS = { "pour-vous": ecranPourVous, ecrans: ecranEcrans, sorties: ecranSorties, profil: ecranProfil };

// ------------------------------------------------------------------ //
// Rendu et chargement                                                  //
// ------------------------------------------------------------------ //
function rendre() {
  const ecran = $("#ecran");
  const nav = $("#onglets");
  if (!etat.onboarde) {
    nav.hidden = true;
    ecran.className = "ecran sans-onglets";
    ecran.innerHTML = ecranAccueil();
    return;
  }
  nav.hidden = false;
  ecran.className = "ecran";
  nav.innerHTML = ONGLETS.map((o) => `<button class="onglet" data-action="onglet" data-onglet="${o.id}"
      ${etat.onglet === o.id ? 'aria-current="page"' : ""}>${icone(o.icone, 22)}<span>${o.nom}</span></button>`).join("");
  ecran.innerHTML = ECRANS[etat.onglet]();
}

/** Ne re-rend que la zone de résultats (évite de casser un curseur pendant un glissement). */
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
    categories: etat.prefs.categories,
  };
}

async function couvertureSiVide(sorties, signal) {
  const v = etat.prefs.ville;
  if (sorties.length || !v) return null;
  try { return await api(`/api/couverture?lat=${v.lat}&lon=${v.lon}`, undefined, signal); } catch (_) { return null; }
}

async function charger({ partiel = false } = {}) {
  if (!etat.onboarde || etat.onglet === "profil") return;
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

/** Après un changement de préférence : recharge si on est dans le flux, sinon met à jour l'écran. */
function apresPreference() {
  sauvegarder();
  if (etat.onboarde && etat.onglet !== "profil") charger();
  else rendre();
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
    if (!etat.onboarde || etat.onglet === "profil") {
      b.setAttribute("aria-pressed", etat.prefs[groupe].includes(valeur)); // en place, sans re-rendu
    } else {
      charger();
    }
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
  commencer() {
    etat.onboarde = true;
    etat.onglet = "pour-vous";
    sauvegarder();
    haut();
    charger();
  },
  onglet(b) {
    etat.onglet = b.dataset.onglet;
    sauvegarder();
    donnees = {};
    haut();
    etat.onglet === "profil" ? rendre() : charger();
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
  async interet(b) {
    const id = b.dataset.id;
    const actif = !etat.interesses.includes(id);
    etat.interesses = actif ? [...etat.interesses, id] : etat.interesses.filter((x) => x !== id);
    sauvegarder();
    const o = trouver(id);
    const majBoutons = () => document.querySelectorAll(`[data-action="interet"][data-id="${CSS.escape(id)}"]`)
      .forEach((el) => { el.outerHTML = boutonInteret(o); });
    if (o) { o.interesses = Math.max(0, o.interesses + (actif ? 1 : -1)); majBoutons(); }
    if (actif) toast("Noté. Les étudiants intéressés pourront se retrouver.");
    try {
      const r = await api("/api/interets", { id, actif });
      if (o) { o.interesses = r.interesses; majBoutons(); }
    } catch (_) { /* le compteur local reste affiché */ }
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
  reinitialiser() {
    try { localStorage.removeItem(CLE_STOCKAGE); } catch (_) { /* rien */ }
    Object.assign(etat, ETAT_INITIAL());
    donnees = {};
    haut();
    rendre();
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
  if (b && actions[b.dataset.action]) actions[b.dataset.action](b);
  if (!e.target.closest("#champ-ville, #suggestions-ville")) { const l = $("#suggestions-ville"); if (l) l.hidden = true; }
});

document.addEventListener("input", (e) => {
  const id = e.target.id;
  if (id === "curseur") {
    etat.decouverte = Number(e.target.value) / 100;
    const n = nbPepites();
    $("#valeur-curseur").innerHTML = valeurCurseur(n);
    $("#piste-remplie").style.width = `calc((100% - 18px) * ${etat.decouverte})`;
    e.target.setAttribute("aria-valuetext", `${n} pépites sur 10`);
    chargerSiQuotaChange();
  } else if (id === "rayon") {
    etat.prefs.rayon = Number(e.target.value);
    $("#valeur-rayon").textContent = `${etat.prefs.rayon} km`;
    if (etat.onboarde && etat.onglet !== "profil") chargerApresRayon();
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
    CONFIG = await api("/api/config");
  } catch (_) {
    $("#ecran").innerHTML = `<div class="vide" style="margin-top:40vh">Serveur injoignable. Lance <code>uvicorn backend.main:app</code>.</div>`;
    return;
  }
  if (!ONGLETS.some((o) => o.id === etat.onglet)) etat.onglet = "pour-vous";
  if (etat.onboarde && etat.onglet !== "profil") charger(); else rendre();
})();
