// Avatars vectoriels minimalistes : portrait éditorial en trait fin, duotone (fond sombre + blanc cassé).
// Aucun fichier image : un petit objet JSON { bg, hair, accessory, expression } suffit (stocké en SQLite + localStorage).

const BLANC = "#F8FAFC";

export const AVATAR_OPTIONS = {
  bg: [
    { id: "ardoise", nom: "Ardoise", couleur: "#1E293B" },
    { id: "indigo", nom: "Indigo", couleur: "#312E81" },
    { id: "ambre", nom: "Ambre profond", couleur: "#78350F" },
    { id: "emeraude", nom: "Émeraude sombre", couleur: "#064E3B" },
    { id: "prune", nom: "Prune", couleur: "#4C1D95" },
    { id: "acier", nom: "Acier", couleur: "#334155" },
  ],
  hair: [
    { id: "court", nom: "Court" }, { id: "milong", nom: "Mi-long" }, { id: "boucle", nom: "Bouclé" },
    { id: "chignon", nom: "Chignon" }, { id: "afro", nom: "Afro" }, { id: "frange", nom: "Frange" },
    { id: "rase", nom: "Rasé" }, { id: "ondule", nom: "Ondulé" },
  ],
  accessory: [
    { id: "aucun", nom: "Aucun" }, { id: "lunettes-rect", nom: "Lunettes fines" }, { id: "lunettes-rondes", nom: "Lunettes rondes" },
    { id: "casque", nom: "Casque audio" }, { id: "bonnet", nom: "Bonnet" },
  ],
  expression: [
    { id: "serein", nom: "Serein" }, { id: "sourire", nom: "Sourire léger" },
    { id: "curieux", nom: "Curieux" }, { id: "concentre", nom: "Concentré" },
  ],
};

const ids = (cle) => AVATAR_OPTIONS[cle].map((o) => o.id);
const valide = (cfg) => cfg && Object.keys(AVATAR_OPTIONS).every((k) => ids(k).includes(cfg[k]));

/** Hachage stable (FNV-1a) : un même prénom donne toujours le même avatar, sur tous les appareils. */
function hachage(texte) {
  let h = 2166136261;
  for (const c of String(texte || "")) { h ^= c.codePointAt(0); h = Math.imul(h, 16777619) >>> 0; }
  return h >>> 0;
}

export function avatarDepuisPrenom(prenom) {
  let h = hachage((prenom || "").trim().toLowerCase());
  const tirer = (cle) => { const l = ids(cle); const v = l[h % l.length]; h = Math.floor(h / l.length) ^ 0x9e37; return v; };
  return { bg: tirer("bg"), hair: tirer("hair"), accessory: h % 3 === 0 ? tirer("accessory") : "aucun", expression: tirer("expression") };
}

export function avatarAleatoire(actuel) {
  const pick = (cle) => { const l = ids(cle); return l[Math.floor(Math.random() * l.length)]; };
  let cfg;
  do {
    cfg = { bg: pick("bg"), hair: pick("hair"), accessory: Math.random() < 0.55 ? "aucun" : pick("accessory"), expression: pick("expression") };
  } while (actuel && JSON.stringify(cfg) === JSON.stringify(actuel));
  return cfg;
}

/** Avatar d'une personne : sa configuration enregistrée, sinon celle dérivée de son prénom. */
export const avatarDe = (p) => (valide(p?.avatar) ? p.avatar : avatarDepuisPrenom(p?.prenom));

// ------------------------------------------------------------------ //
// Dessin (viewBox 64 × 64 ; tête centrée en 32,31)                     //
// ------------------------------------------------------------------ //
const trait = (d, extra = "") => `<path d="${d}" fill="none" stroke="${BLANC}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" ${extra}/>`;
const plein = (d, extra = "") => `<path d="${d}" fill="${BLANC}" ${extra}/>`;

// Cheveux : [derrière la tête, devant la tête]
const CHEVEUX = {
  court: ["", plein("M20.6 29.5C19.8 19.5 25.4 15.2 32.2 15.2C39 15.2 44.6 19.6 43.6 29.5C42.4 24.6 39.4 22.4 35.4 22.1C32.6 23.6 27.8 24.2 24.2 23.4C22.4 24.6 21.2 26.6 20.6 29.5Z")],
  milong: [plein("M19.6 44C18.4 36 18.6 27 20.4 22.5L43.8 22.5C45.6 27 45.8 36 44.6 44C43 44.8 41.6 44.6 40.6 43.6L40.8 30L23.4 30L23.6 43.6C22.6 44.6 21.2 44.8 19.6 44Z"),
    plein("M20.4 30C19.6 19.6 25.6 15 32.2 15C38.8 15 44.8 19.6 44 30C42.2 25 38.8 22.4 32.2 22C29 24.6 24.6 26.6 20.4 30Z")],
  boucle: ["", ["22.4,25.6,3.6", "24.2,20,3.8", "28.6,16.6,3.9", "34,15.6,4", "39.2,17.6,3.8", "42.2,22.4,3.6", "43.2,27.4,2.8", "21,30,2.6"]
    .map((c) => { const [x, y, r] = c.split(","); return `<circle cx="${x}" cy="${y}" r="${r}" fill="${BLANC}"/>`; }).join("")],
  chignon: [`<circle cx="32.2" cy="11.6" r="4.6" fill="${BLANC}"/>`,
    plein("M20.8 29C20.4 19.6 25.6 15.6 32.2 15.6C38.8 15.6 44 19.6 43.6 29C41.6 23.2 37.6 20.6 32.2 20.6C26.8 20.6 22.8 23.2 20.8 29Z")],
  afro: [`<circle cx="32.2" cy="25" r="16.2" fill="${BLANC}"/>`, ""],
  frange: ["", plein("M20.4 31C19.6 20 25 15 32.2 15C39.4 15 44.8 20 44 31L42.6 25.2L21.8 25.2Z")],
  rase: ["", plein("M21 27.6C21 19.8 26 16.4 32.2 16.4C38.4 16.4 43.4 19.8 43.4 27.6C41.4 22.6 37.2 21 32.2 21C27.2 21 23 22.6 21 27.6Z", 'opacity="0.45"')],
  ondule: [plein("M18.8 43.4C16.8 38 21.2 35 19.2 29.4C17.6 20.4 24.4 14.6 32.2 14.6C40 14.6 46.8 20.4 45.2 29.4C43.2 35 47.6 38 45.6 43.4C44 44.4 42.2 44.2 41.2 43.2L41.4 30.4L23 30.4L23.2 43.2C22.2 44.2 20.4 44.4 18.8 43.4Z"),
    plein("M20.8 29.6C21 21.4 26.2 17.4 32.2 17.4C38.2 17.4 43.4 21.4 43.6 29.6C41.8 25.8 39.4 23.2 36 22.6C34.4 24.2 31.6 24.6 29.4 23.6C26 24.4 22.6 26.4 20.8 29.6Z")],
};

const EXPRESSIONS = {
  serein: trait("M25.9 30.6Q27.6 31.9 29.3 30.6") + trait("M35.1 30.6Q36.8 31.9 38.5 30.6") + trait("M29.9 38Q32.2 38.7 34.5 38"),
  sourire: `<circle cx="27.6" cy="30.6" r="1" fill="${BLANC}"/><circle cx="36.8" cy="30.6" r="1" fill="${BLANC}"/>` + trait("M28.9 37.2Q32.2 40.2 35.5 37.2"),
  curieux: `<circle cx="27.6" cy="30.8" r="1" fill="${BLANC}"/><circle cx="36.8" cy="30.8" r="1" fill="${BLANC}"/>`
    + trait("M25.8 27.4Q27.6 26.4 29.4 27.2") + trait("M35 26.2Q36.8 24.8 38.6 25.9") + `<circle cx="32.2" cy="38.2" r="1.1" fill="none" stroke="${BLANC}" stroke-width="1.3"/>`,
  concentre: `<circle cx="27.6" cy="31" r="1" fill="${BLANC}"/><circle cx="36.8" cy="31" r="1" fill="${BLANC}"/>`
    + trait("M25.8 27.8L29.4 28.3") + trait("M35 28.3L38.6 27.8") + trait("M30.4 38.2L34 38.2"),
};

const ACCESSOIRES = {
  aucun: "",
  "lunettes-rect": trait("M24.2 28.6h6.4v4.4h-6.4z", 'stroke-width="1.3"') + trait("M33.8 28.6h6.4v4.4h-6.4z", 'stroke-width="1.3"')
    + trait("M30.6 30.2Q32.2 29.4 33.8 30.2", 'stroke-width="1.2"') + trait("M24.2 29.6L21 28.8M40.2 29.6L43.4 28.8", 'stroke-width="1.2"'),
  "lunettes-rondes": `<circle cx="27.6" cy="30.8" r="3.3" fill="none" stroke="${BLANC}" stroke-width="1.3"/><circle cx="36.8" cy="30.8" r="3.3" fill="none" stroke="${BLANC}" stroke-width="1.3"/>`
    + trait("M30.9 30.4Q32.2 29.6 33.5 30.4", 'stroke-width="1.2"') + trait("M24.3 30.2L21 29.4M40.1 30.2L43.4 29.4", 'stroke-width="1.2"'),
  casque: trait("M19.4 31C18.6 17.4 26 12.8 32.2 12.8C38.4 12.8 45.8 17.4 45 31", 'stroke-width="2.2"')
    + `<rect x="16.6" y="27.4" width="5" height="9" rx="2.4" fill="${BLANC}"/><rect x="42.8" y="27.4" width="5" height="9" rx="2.4" fill="${BLANC}"/>`,
  bonnet: plein("M20.2 25.4C20.2 15.6 25.6 11.8 32.2 11.8C38.8 11.8 44.2 15.6 44.2 25.4Z")
    + `<rect x="19" y="23.2" width="26.4" height="4.6" rx="2.3" fill="${BLANC}"/><circle cx="32.2" cy="10.6" r="2.6" fill="${BLANC}"/>`,
};

/**
 * Portrait SVG. config = { bg, hair, accessory, expression } (valeurs inconnues : repli sur la première option).
 * size = côté en pixels. Le fond est un disque ; la tête est remplie de la couleur de fond (masque les cheveux arrière).
 */
export function renderAvatarSVG(config, size = 48) {
  const c = valide(config) ? config : avatarDepuisPrenom("");
  const fond = AVATAR_OPTIONS.bg.find((b) => b.id === c.bg).couleur;
  const [arriere, avant] = CHEVEUX[c.hair];
  const bonnet = c.accessory === "bonnet";
  const idClip = `av${Math.random().toString(36).slice(2, 8)}`;
  return `<svg class="avatar-svg" width="${size}" height="${size}" viewBox="0 0 64 64" role="img" aria-hidden="true" xmlns="http://www.w3.org/2000/svg">
    <defs><clipPath id="${idClip}"><circle cx="32" cy="32" r="32"/></clipPath></defs>
    <g clip-path="url(#${idClip})">
      <rect width="64" height="64" fill="${fond}"/>
      <circle cx="32" cy="22" r="26" fill="#FFFFFF" opacity="0.05"/>
      ${arriere}
      ${trait("M11 66C12.6 53.6 21 48.4 32.2 48.4C43.4 48.4 51.8 53.6 53.4 66")}
      ${trait("M28.6 43.6L28.4 48.6M35.8 43.6L36 48.6")}
      <ellipse cx="32.2" cy="31" rx="11.4" ry="13.4" fill="${fond}" stroke="${BLANC}" stroke-width="1.5"/>
      ${bonnet ? "" : avant}
      ${trait("M32.4 32.2L31.4 35.4L32.8 35.6", 'stroke-width="1.2"')}
      ${EXPRESSIONS[c.expression]}
      ${ACCESSOIRES[c.accessory]}
    </g>
  </svg>`;
}
