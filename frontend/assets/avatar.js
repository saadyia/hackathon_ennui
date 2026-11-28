// Avatars « Aura lumineuse » : dégradé atmosphérique multi-couches + monogramme ou glyphe géométrique, en SVG pur.
// Aucune illustration, aucune dépendance. Option : photo importée (DataURL 200 × 200 compressée côté client).
// Configuration enregistrée (SQLite + localStorage) : { atmo, signature, photo? }.

const BLANC = "#F8FAFC";

/** 8 palettes harmonisées avec le fond nuit : base (ombre), coeur (couleur), lueur (source de lumière). */
export const ATMOSPHERES = [
  { id: "indigo", nom: "Indigo Nocturne", base: "#0D1030", coeur: "#3B37B8", lueur: "#A5B4FC" },
  { id: "ambre", nom: "Ambre Solaire", base: "#1C1206", coeur: "#B45309", lueur: "#FCD9A0" },
  { id: "emeraude", nom: "Émeraude Abyssal", base: "#03140F", coeur: "#047857", lueur: "#86EFC5" },
  { id: "carmin", nom: "Carmin Sombre", base: "#1A060B", coeur: "#9F1239", lueur: "#FDA4B4" },
  { id: "cyan", nom: "Cyan Polaire", base: "#03131A", coeur: "#0E7490", lueur: "#A5F0FC" },
  { id: "violet", nom: "Violet Astral", base: "#130A26", coeur: "#6D28D9", lueur: "#DCC2FE" },
  { id: "titane", nom: "Titane", base: "#0E1116", coeur: "#4B5563", lueur: "#E5E9F0" },
  { id: "cuivre", nom: "Cuivre", base: "#170B06", coeur: "#9A3E12", lueur: "#FDC49A" },
];

export const SIGNATURES = [
  { id: "initiale", nom: "Initiale" },
  { id: "double", nom: "Double initiale" },
  { id: "anneau", nom: "Anneau" },
  { id: "etoile", nom: "Étoile" },
  { id: "onde", nom: "Onde" },
  { id: "prisme", nom: "Prisme" },
];

const PHOTO_VALIDE = /^data:image\/(webp|jpeg);base64,[A-Za-z0-9+/=]+$/;
const TAILLE_MAX_PHOTO = 80000;  // caractères (~60 Ko), une image 200 × 200 compressée en fait ~10 à 20

function valide(c) {
  return Boolean(c && typeof c === "object" && ATMOSPHERES.some((a) => a.id === c.atmo) && SIGNATURES.some((s) => s.id === c.signature)
    && (c.photo == null || (typeof c.photo === "string" && c.photo.length <= TAILLE_MAX_PHOTO && PHOTO_VALIDE.test(c.photo))));
}

function hachage(texte) {
  let h = 2166136261;
  for (const ch of String(texte || "")) { h ^= ch.codePointAt(0); h = Math.imul(h, 16777619) >>> 0; }
  return h >>> 0;
}

/** Aura par défaut, stable : même prénom = même atmosphère sur tous les appareils. */
export function avatarDepuisPrenom(prenom) {
  return { atmo: ATMOSPHERES[hachage((prenom || "").trim().toLowerCase()) % ATMOSPHERES.length].id, signature: "initiale" };
}

/** Change d'atmosphère (jamais la même), garde la signature et la photo. */
export function avatarAleatoire(actuel) {
  const autres = ATMOSPHERES.filter((a) => a.id !== actuel?.atmo);
  return { ...(valide(actuel) ? actuel : { signature: "initiale" }), atmo: autres[Math.floor(Math.random() * autres.length)].id };
}

export const avatarDe = (p) => (valide(p?.avatar) ? p.avatar : avatarDepuisPrenom(p?.prenom));

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

/** « Sadia » -> S / SA ; « Jean-Marc Dupont » -> J / JD. */
function monogramme(prenom, double) {
  const mots = String(prenom || "").trim().split(/[\s-]+/).filter(Boolean);
  if (!mots.length) return "";
  if (!double) return mots[0][0].toUpperCase();
  return (mots.length > 1 ? mots[0][0] + mots[1][0] : mots[0].slice(0, 2)).toUpperCase();
}

// Glyphes en trait fin (viewBox 100), centrés
const GLYPHES = {
  anneau: `<circle cx="50" cy="50" r="17" fill="none" stroke="${BLANC}" stroke-width="2.4"/><circle cx="50" cy="50" r="2.6" fill="${BLANC}"/>`,
  etoile: `<path d="M50 27C51.6 43.4 56.6 48.4 73 50C56.6 51.6 51.6 56.6 50 73C48.4 56.6 43.4 51.6 27 50C43.4 48.4 48.4 43.4 50 27Z" fill="none" stroke="${BLANC}" stroke-width="2.2" stroke-linejoin="round"/>`,
  onde: `<path d="M26 50C30 40 34 40 38 50S46 60 50 50S58 40 62 50S70 60 74 50" fill="none" stroke="${BLANC}" stroke-width="2.4" stroke-linecap="round"/>`,
  prisme: `<path d="M50 29L71 67H29Z" fill="none" stroke="${BLANC}" stroke-width="2.2" stroke-linejoin="round"/><path d="M50 29L50 67" stroke="${BLANC}" stroke-width="1.4" opacity="0.55"/>`,
};

let compteur = 0;

/**
 * Avatar circulaire (chaîne SVG). config = { atmo, signature, photo? } ; prenom sert au monogramme.
 * Couches : base sombre, source de lumière haute, coeur coloré bas, halo central doux, vignettage, reflet vitré.
 */
export function renderAvatar(config, size = 48, prenom = "") {
  const c = valide(config) ? config : avatarDepuisPrenom(prenom);
  const a = ATMOSPHERES.find((x) => x.id === c.atmo);
  const id = `au${(compteur++).toString(36)}`;
  let centre = "";
  if (c.photo) {
    centre = `<image href="${c.photo}" x="0" y="0" width="100" height="100" preserveAspectRatio="xMidYMid slice" clip-path="url(#${id}c)"/>
      <circle cx="50" cy="50" r="50" fill="url(#${id}v)" opacity="0.55"/>`;
  } else if (GLYPHES[c.signature]) {
    centre = GLYPHES[c.signature];
  } else {
    const texte = monogramme(prenom, c.signature === "double") || "?";
    centre = `<text x="50" y="51" text-anchor="middle" dominant-baseline="central" fill="${BLANC}"
      font-family="'Plus Jakarta Sans', ui-sans-serif, system-ui, sans-serif" font-weight="700"
      font-size="${texte.length > 1 ? 31 : 38}" letter-spacing="${texte.length > 1 ? -1.4 : -0.8}" opacity="0.96">${esc(texte)}</text>`;
  }
  return `<svg class="avatar-svg" width="${size}" height="${size}" viewBox="0 0 100 100" aria-hidden="true" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <clipPath id="${id}c"><circle cx="50" cy="50" r="50"/></clipPath>
      <radialGradient id="${id}h" cx="28%" cy="18%" r="85%"><stop offset="0" stop-color="${a.lueur}" stop-opacity="0.55"/><stop offset="0.38" stop-color="${a.coeur}" stop-opacity="0.42"/><stop offset="1" stop-color="${a.coeur}" stop-opacity="0"/></radialGradient>
      <radialGradient id="${id}b" cx="82%" cy="92%" r="78%"><stop offset="0" stop-color="${a.coeur}" stop-opacity="0.75"/><stop offset="0.6" stop-color="${a.coeur}" stop-opacity="0.18"/><stop offset="1" stop-color="${a.coeur}" stop-opacity="0"/></radialGradient>
      <radialGradient id="${id}m" cx="50%" cy="50%" r="42%"><stop offset="0" stop-color="${a.lueur}" stop-opacity="0.14"/><stop offset="1" stop-color="${a.lueur}" stop-opacity="0"/></radialGradient>
      <radialGradient id="${id}v" cx="50%" cy="45%" r="58%"><stop offset="0.55" stop-color="#05070D" stop-opacity="0"/><stop offset="1" stop-color="#05070D" stop-opacity="0.55"/></radialGradient>
      <linearGradient id="${id}r" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFFFFF" stop-opacity="0.10"/><stop offset="0.6" stop-color="#FFFFFF" stop-opacity="0"/></linearGradient>
    </defs>
    <g clip-path="url(#${id}c)">
      <rect width="100" height="100" fill="${a.base}"/>
      <rect width="100" height="100" fill="url(#${id}b)"/>
      <rect width="100" height="100" fill="url(#${id}h)"/>
      <rect width="100" height="100" fill="url(#${id}m)"/>
      <rect width="100" height="100" fill="url(#${id}v)"/>
      ${centre}
      <rect width="100" height="40" fill="url(#${id}r)"/>
    </g>
  </svg>`;
}

/**
 * Photo importée -> DataURL carrée 200 × 200 (recadrage centré, WebP si possible, sinon JPEG), < 80 000 caractères.
 */
export async function photoVersDataUrl(fichier) {
  if (!fichier || !/^image\//.test(fichier.type)) throw new Error("Choisis une image.");
  const url = URL.createObjectURL(fichier);
  try {
    const img = await new Promise((ok, ko) => { const i = new Image(); i.onload = () => ok(i); i.onerror = () => ko(new Error("Image illisible.")); i.src = url; });
    const cote = Math.min(img.naturalWidth, img.naturalHeight);
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = 200;
    const ctx = canvas.getContext("2d");
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(img, (img.naturalWidth - cote) / 2, (img.naturalHeight - cote) / 2, cote, cote, 0, 0, 200, 200);
    for (const q of [0.82, 0.7, 0.55]) {
      let d = canvas.toDataURL("image/webp", q);
      if (!d.startsWith("data:image/webp")) d = canvas.toDataURL("image/jpeg", q);  // Safari ancien : pas de WebP
      if (d.length <= TAILLE_MAX_PHOTO) return d;
    }
    throw new Error("Image trop lourde.");
  } finally {
    URL.revokeObjectURL(url);
  }
}
