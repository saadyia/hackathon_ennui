// Avatars illustrés DiceBear (styles dessinés par des artistes), rendus EN LOCAL :
// frontend/vendor/dicebear (copie des modules ESM @dicebear 9.4.3), aucun appel réseau ni CDN.
//   notionists : Zoish, CC0 1.0 · micah : Micah Lanier, CC BY 4.0 · glass : DiceBear, CC0 1.0 · core : MIT
// Configuration enregistrée : { style, seed, bg, hair?, glasses?, brows?, mouth? }.
// Repli instantané : initiales en Plus Jakarta Sans Bold si les modules ne se chargent pas.

let DB = null;  // { createAvatar, styles: { notionists, micah, glass } }

/** À attendre une fois au démarrage (fichiers locaux : quelques millisecondes). Ne rejette jamais. */
export const avatarsPrets = Promise.all([
  import("../vendor/dicebear/core.js"),
  import("../vendor/dicebear/notionists.js"),
  import("../vendor/dicebear/micah.js"),
  import("../vendor/dicebear/glass.js"),
]).then(([core, notionists, micah, glass]) => {
  DB = { createAvatar: core.createAvatar, styles: { notionists, micah, glass } };
  return true;
}).catch(() => false);

// Fonds : teintes pastel (lisibles sous un trait noir) ; « Aura » utilise la teinte sombre associée.
export const FONDS = [
  { id: "b6e3f4", nom: "Ciel", sombre: "1E293B" },
  { id: "c0aede", nom: "Lavande", sombre: "4C1D95" },
  { id: "d1d4f9", nom: "Pervenche", sombre: "312E81" },
  { id: "ffd5dc", nom: "Rose poudré", sombre: "4C1D95" },
  { id: "ffdfbf", nom: "Pêche", sombre: "78350F" },
  { id: "c7ead8", nom: "Menthe", sombre: "064E3B" },
];

const variantes = (n) => Array.from({ length: n }, (_, i) => `variant${String(i + 1).padStart(2, "0")}`);

// Paramètres réels de chaque style DiceBear, exposés dans le studio.
export const STYLES = [
  {
    id: "notionists", nom: "Éditorial Notion",
    hair: variantes(63).concat("hat"),
    glasses: ["aucune", ...variantes(11)],
    brows: variantes(13),
    mouth: variantes(30),
    options: (c) => ({
      ...(c.hair ? { hair: [c.hair] } : {}),
      ...(c.glasses ? (c.glasses === "aucune" ? { glassesProbability: 0 } : { glasses: [c.glasses], glassesProbability: 100 }) : {}),
      ...(c.brows ? { brows: [c.brows] } : {}),
      ...(c.mouth ? { lips: [c.mouth] } : {}),
      gestureProbability: 0, bodyIconProbability: 0,
    }),
  },
  {
    id: "micah", nom: "Portrait Moderne",
    hair: ["fonze", "mrT", "dougFunny", "mrClean", "dannyPhantom", "full", "turban", "pixie"],
    glasses: ["aucune", "round", "square"],
    brows: ["up", "down", "eyelashesUp", "eyelashesDown"],
    mouth: ["smile", "laughing", "smirk", "surprised", "nervous", "pucker", "sad", "frown"],
    options: (c) => ({
      ...(c.hair ? { hair: [c.hair] } : {}),
      ...(c.glasses ? (c.glasses === "aucune" ? { glassesProbability: 0 } : { glasses: [c.glasses], glassesProbability: 100 }) : {}),
      ...(c.brows ? { eyebrows: [c.brows] } : {}),
      ...(c.mouth ? { mouth: [c.mouth] } : {}),
      earringsProbability: 0,
    }),
  },
  { id: "glass", nom: "Aura Abstraite", hair: [], glasses: [], brows: [], mouth: [], options: () => ({}) },
];
const styleDe = (id) => STYLES.find((s) => s.id === id) || STYLES[0];

const NOMS_DETAILS = { round: "Rondes", square: "Carrées", aucune: "Aucune", up: "Hauts", down: "Bas", eyelashesUp: "Cils hauts",
  eyelashesDown: "Cils bas", smile: "Sourire", laughing: "Rire", smirk: "En coin", surprised: "Surpris", nervous: "Gêné",
  pucker: "Moue", sad: "Triste", frown: "Froncé", fonze: "Banane", mrT: "Crête", dougFunny: "Mèches", mrClean: "Rasé",
  dannyPhantom: "Décoiffé", full: "Long", turban: "Turban", pixie: "Court", hat: "Chapeau" };
/** Libellé court d'une valeur DiceBear (« variant07 » -> « 7 »). */
export const nomValeur = (v) => NOMS_DETAILS[v] || (v.startsWith("variant") ? String(Number(v.slice(7))) : v);

const CLES = ["hair", "glasses", "brows", "mouth"];
function valide(c) {
  if (!c || typeof c !== "object" || !STYLES.some((s) => s.id === c.style) || !FONDS.some((f) => f.id === c.bg)) return false;
  if (typeof c.seed !== "string" || !c.seed) return false;
  const s = styleDe(c.style);
  return CLES.every((k) => c[k] == null || s[k].includes(c[k]));
}

function hachage(texte) {
  let h = 2166136261;
  for (const ch of String(texte || "")) { h ^= ch.codePointAt(0); h = Math.imul(h, 16777619) >>> 0; }
  return h >>> 0;
}

/** Avatar par défaut, stable : même prénom = même portrait sur tous les appareils. */
export function avatarDepuisPrenom(prenom) {
  const seed = (prenom || "ofk").trim() || "ofk";
  return { style: "notionists", seed, bg: FONDS[hachage(seed) % FONDS.length].id };
}

/** Nouveau seed aléatoire (les choix explicites sont remis à zéro) ; le style est conservé. */
export function avatarAleatoire(actuel) {
  const seed = Math.random().toString(36).slice(2, 10);
  return { style: actuel?.style || "notionists", seed, bg: FONDS[Math.floor(Math.random() * FONDS.length)].id };
}

export const avatarDe = (p) => (valide(p?.avatar) ? p.avatar : avatarDepuisPrenom(p?.prenom));

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

/** Repli hors ligne : initiales sur la teinte sombre du fond. */
function initiales(config, size, prenom) {
  const fond = (FONDS.find((f) => f.id === config.bg) || FONDS[0]).sombre;
  const texte = (prenom || config.seed || "?").split(/[\s-]+/).filter(Boolean).slice(0, 2).map((m) => m[0]).join("").toUpperCase();
  return `<svg class="avatar-svg" width="${size}" height="${size}" viewBox="0 0 64 64" aria-hidden="true" xmlns="http://www.w3.org/2000/svg">
    <circle cx="32" cy="32" r="32" fill="#${fond}"/>
    <text x="32" y="33" text-anchor="middle" dominant-baseline="central" fill="#F8FAFC"
      font-family="'Plus Jakarta Sans', ui-sans-serif, system-ui, sans-serif" font-weight="700" font-size="22" letter-spacing="-0.5">${esc(texte)}</text>
  </svg>`;
}

/**
 * Portrait SVG (chaîne) d'après une configuration. size en pixels ; zoom = gros plan sur le visage (vignettes du studio).
 * Les identifiants internes du SVG sont rendus uniques à chaque appel (plusieurs avatars sur une page).
 */
export function renderAvatarSVG(config, size = 48, prenom = "", { zoom = false } = {}) {
  const c = valide(config) ? config : avatarDepuisPrenom(prenom || config?.seed);
  if (!DB) return initiales(c, size, prenom);
  try {
    const style = styleDe(c.style);
    const fond = FONDS.find((f) => f.id === c.bg) || FONDS[0];
    const svg = DB.createAvatar(DB.styles[c.style], {
      seed: c.seed, size, radius: 50, randomizeIds: true,
      backgroundColor: [c.style === "glass" ? fond.sombre : fond.id],
      ...(c.style === "glass" ? { scale: 110 } : zoom ? { scale: 150, translateY: 14 } : { scale: 100 }),
      ...style.options(c),
    }).toString();
    return svg.replace("<svg ", '<svg class="avatar-svg" aria-hidden="true" ');
  } catch (_) {
    return initiales(c, size, prenom);
  }
}
