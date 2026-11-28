// Personnages illustrés DiceBear harmonisés avec la DA sombre de « ofk? », rendus EN LOCAL :
// frontend/vendor/dicebear (modules ESM @dicebear 9.4.3), aucun appel réseau ni CDN.
//   lorelei : Lisa Wischofsky, CC0 1.0 · micah : Micah Lanier, CC BY 4.0 · core : MIT
// Fonds sombres feutrés, couleurs désaturées (blanc cassé, gris perle, noir d'encre, pastels très doux).
// Configuration enregistrée : { style, seed, bg, hair?, glasses?, mouth?, eyes? }.
// Repli instantané : initiales en Plus Jakarta Sans Bold sur fond ardoise (chargement, hors ligne).

let DB = null;  // { createAvatar, styles: { lorelei, micah } }

/** À attendre une fois au démarrage (fichiers locaux). Ne rejette jamais. */
export const avatarsPrets = Promise.all([
  import("../vendor/dicebear/core.js"),
  import("../vendor/dicebear/lorelei.js"),
  import("../vendor/dicebear/micah.js"),
]).then(([core, lorelei, micah]) => {
  DB = { createAvatar: core.createAvatar, styles: { lorelei, micah } };
  return true;
}).catch(() => false);

export const FONDS = [
  { id: "1e293b", nom: "Ardoise" },
  { id: "27294a", nom: "Indigo nuit" },
  { id: "422b18", nom: "Ambre sombre" },
  { id: "13382e", nom: "Émeraude profond" },
  { id: "351f47", nom: "Prune nuit" },
  { id: "293548", nom: "Acier" },
];

// Palette éditoriale désaturée (jamais de fluo) : le seed choisit dedans, toujours de façon stable.
const CHEVEUX = ["ece8e1", "cfc8bd", "a89f94", "2b2724", "4a3b32", "6e5a4b", "d8cde6", "c9d5e3"];  // blanc cassé, perle, taupe, encre, bruns, lilas, bleu brume
const PEAUX = ["f3ddd0", "e4c1aa", "c99d82", "a6765c", "7c5543"];
const VETEMENTS = ["ece8e1", "c7ced8", "8e99a8", "2b313c", "e3d7c8", "cfd3ee"];
const LUNETTES = ["ece8e1", "a8b0bb", "1c1f26"];

const variantes = (n) => Array.from({ length: n }, (_, i) => `variant${String(i + 1).padStart(2, "0")}`);
const LORELEI_BOUCHES = [...Array.from({ length: 18 }, (_, i) => `happy${String(i + 1).padStart(2, "0")}`),
  ...Array.from({ length: 9 }, (_, i) => `sad${String(i + 1).padStart(2, "0")}`)];

// Paramètres réels de chaque style DiceBear exposés dans le studio.
export const STYLES = [
  {
    id: "lorelei", nom: "Éditorial",
    hair: variantes(48), glasses: ["aucune", ...variantes(5)], mouth: LORELEI_BOUCHES, eyes: variantes(24),
    options: (c) => ({
      hairColor: CHEVEUX, skinColor: PEAUX, glassesColor: LUNETTES,
      eyebrowsColor: ["1c1f26"], eyesColor: ["1c1f26"], mouthColor: ["1c1f26"], noseColor: ["1c1f26"],
      earringsProbability: 0, hairAccessoriesProbability: 0, frecklesProbability: 0, beardProbability: 0,
      ...(c.hair ? { hair: [c.hair] } : {}),
      ...(c.glasses ? (c.glasses === "aucune" ? { glassesProbability: 0 } : { glasses: [c.glasses], glassesProbability: 100 }) : {}),
      ...(c.mouth ? { mouth: [c.mouth] } : {}),
      ...(c.eyes ? { eyes: [c.eyes] } : {}),
    }),
  },
  {
    id: "micah", nom: "Portrait Studio",
    hair: ["fonze", "mrT", "dougFunny", "mrClean", "dannyPhantom", "full", "turban", "pixie"],
    glasses: ["aucune", "round", "square"],
    mouth: ["smile", "laughing", "smirk", "surprised", "nervous", "pucker", "sad", "frown"],
    eyes: ["eyes", "round", "smiling", "eyesShadow", "smilingShadow"],
    options: (c) => ({
      baseColor: PEAUX, hairColor: CHEVEUX, shirtColor: VETEMENTS, glassesColor: LUNETTES,
      eyeShadowColor: ["e6e1ec"], earringsProbability: 0, facialHairProbability: 0,
      ...(c.hair ? { hair: [c.hair] } : {}),
      ...(c.glasses ? (c.glasses === "aucune" ? { glassesProbability: 0 } : { glasses: [c.glasses], glassesProbability: 100 }) : {}),
      ...(c.mouth ? { mouth: [c.mouth] } : {}),
      ...(c.eyes ? { eyes: [c.eyes] } : {}),
    }),
  },
];
const styleDe = (id) => STYLES.find((s) => s.id === id) || STYLES[0];

const NOMS = { aucune: "Aucune", round: "Rondes", square: "Carrées", smile: "Sourire", laughing: "Rire", smirk: "En coin",
  surprised: "Surpris", nervous: "Gêné", pucker: "Moue", sad: "Triste", frown: "Froncé", eyes: "Naturels", smiling: "Rieurs",
  eyesShadow: "Ombrés", smilingShadow: "Rieurs ombrés", fonze: "Banane", mrT: "Crête", dougFunny: "Mèches", mrClean: "Rasé",
  dannyPhantom: "Décoiffé", full: "Long", turban: "Turban", pixie: "Court" };
/** Libellé court d'une valeur DiceBear (« variant07 » -> « 7 », « happy03 » -> « Joie 3 »). */
export function nomValeur(v) {
  if (NOMS[v]) return NOMS[v];
  const m = /^(variant|happy|sad)(\d+)$/.exec(v);
  if (!m) return v;
  return `${m[1] === "happy" ? "Joie " : m[1] === "sad" ? "Calme " : ""}${Number(m[2])}`;
}

const CLES = ["hair", "glasses", "mouth", "eyes"];
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

/** Personnage par défaut, stable : même prénom = même personnage sur tous les appareils. */
export function avatarDepuisPrenom(prenom) {
  const seed = (prenom || "ofk").trim() || "ofk";
  return { style: "lorelei", seed, bg: FONDS[hachage(seed) % FONDS.length].id };
}

/** Nouveau personnage : nouveau seed, fond au hasard, choix explicites remis à zéro ; le style est conservé. */
export function avatarAleatoire(actuel) {
  return { style: actuel?.style || "lorelei", seed: Math.random().toString(36).slice(2, 10),
    bg: FONDS[Math.floor(Math.random() * FONDS.length)].id };
}

export const avatarDe = (p) => (valide(p?.avatar) ? p.avatar : avatarDepuisPrenom(p?.prenom));

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

/** Repli : initiales en Plus Jakarta Sans Bold sur fond ardoise. */
function initiales(size, prenom, seed) {
  const texte = (prenom || seed || "?").split(/[\s-]+/).filter(Boolean).slice(0, 2).map((m) => m[0]).join("").toUpperCase() || "?";
  return `<svg class="avatar-svg" width="${size}" height="${size}" viewBox="0 0 64 64" aria-hidden="true" xmlns="http://www.w3.org/2000/svg">
    <circle cx="32" cy="32" r="32" fill="#1E293B"/>
    <text x="32" y="33" text-anchor="middle" dominant-baseline="central" fill="#F8FAFC"
      font-family="'Plus Jakarta Sans', ui-sans-serif, system-ui, sans-serif" font-weight="700" font-size="${texte.length > 1 ? 21 : 25}" letter-spacing="-0.5">${esc(texte)}</text>
  </svg>`;
}

/**
 * Personnage SVG (chaîne). size en pixels ; prenom pour le repli ; zoom = gros plan sur le visage (vignettes du studio).
 * Les identifiants internes du SVG sont rendus uniques à chaque appel.
 */
export function renderAvatar(config, size = 48, prenom = "", { zoom = false } = {}) {
  const c = valide(config) ? config : avatarDepuisPrenom(prenom || config?.seed);
  if (!DB) return initiales(size, prenom, c.seed);
  try {
    const svg = DB.createAvatar(DB.styles[c.style], {
      seed: c.seed, size, radius: 50, randomizeIds: true, backgroundColor: [c.bg],
      ...(zoom ? { scale: 135, translateY: c.style === "micah" ? 8 : 6 } : { scale: 104, translateY: 2 }),
      ...styleDe(c.style).options(c),
    }).toString();
    return svg.replace("<svg ", '<svg class="avatar-svg" aria-hidden="true" ');
  } catch (_) {
    return initiales(size, prenom, c.seed);
  }
}
