# CLAUDE.md — frontend

> Complète le CLAUDE.md racine. Ne répéter ici que ce qui est spécifique au frontend.

## Stack
HTML + CSS écrit à la main + JavaScript vanilla (module ES). **Aucun CDN, aucun build.**
```
frontend/
├── index.html             # coquille + chargement des librairies locales
├── vendor/                # librairies UI copiées en local (licences à côté)
│   ├── lucide.min.js      # icônes (ISC) — utilisées via icone(nom), stroke 1.5
│   ├── nouislider.min.*   # curseurs Confort ↔ Découverte et périmètre (MIT)
│   ├── swiper-bundle.min.*# carrousels de « Pour vous » (MIT)
│   └── gsap.min.js        # animations (GreenSock Standard License, gratuite)
└── assets/
    ├── app.css            # design system (variables :root), composants, thèmes noUiSlider/Swiper
    ├── app.js             # état, écrans, actions, appels API
    └── fonts/             # Plus Jakarta Sans (titres), Inter (texte), JetBrains Mono (chiffres) — OFL
```

## Règles de design (strictes)
- **Zéro émoji.** Icônes : uniquement `icone(nom)` (données de `vendor/lucide.min.js`, SVG stroke 1.5, aucune passe DOM).
- Typographie : `--police-titres` (Plus Jakarta Sans), `--police-texte` (Inter), `.chiffre` / `--police-chiffres`
  (JetBrains Mono, `tabular-nums`) **seulement** pour les nombres (km, tarifs, années, horaires, participants).
- Couleurs via variables ; `--accent` (champagne) réservé à Pépite, Hors piste, curseurs et actions collaboratives.
- Profondeur : halo `.app::before`, verre dépoli `--verre` + `backdrop-filter`, bordures `--trait`.
- Ratios stricts : `.visuel.affiche` 2/3 (films, séries, livres), `.visuel.paysage` 16/10 (sorties, jeux), `.voile` pour la lisibilité.

## Composants
- `monterComposants(racine)` après **chaque** rendu : noUiSlider (`#curseur-ui`, `#rayon-ui`), Swiper (`.swiper.rangee`),
  apparition des cartes en cascade (GSAP). `rendreContenu()` ne remplace que `#contenu` (les curseurs survivent).
- Animations : seulement si `MOUVEMENT` (GSAP présent et pas `prefers-reduced-motion`). Classe `html.anime` = GSAP actif.
- Fiche détaillée : clic sur le visuel ou le titre d'une carte (`data-action="ouvrir-plans"`) -> bottom sheet `#feuille`
  (`detailOeuvre()` + plans). Ouverture/fermeture animées (`animerOuvertureFeuille`, `fermerFeuille`).
- Envies : `CONFIG.envies` (univers `chez-soi` / `sorties`) ; anciennes valeurs migrées par `MIGRATION_ENVIES`.
- Chez soi : segments Tout / Films & Séries / Lecture / Jeux vidéo ; filtres dédiés dans `filtresChezSoi()`
  (thèmes de lecture ; machine et mode de jeu).
- Types de contenus : table `TYPES` ; état par compte dans `localStorage` (`ennui.v4.*`), accès sous try/catch.
- Plateformes : afficher seulement si `plateformes_verifiees`. Liens de rendez-vous cliquables seulement en `https://`.

## Lancement et captures
Via le backend : `uvicorn backend.main:app --reload`. Captures headless : `--force-prefers-reduced-motion`,
`--virtual-time-budget` long ; l'accueil « On fait koi ? » s'affiche à chaque ouverture (cliquer « C'est parti ! »).
