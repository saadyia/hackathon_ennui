# CLAUDE.md — frontend

> Complète le CLAUDE.md racine. Ne répéter ici que ce qui est spécifique au frontend.

## Stack
HTML + CSS écrit à la main + JavaScript vanilla (module ES). **Aucun CDN, aucun build.**
```
frontend/
├── index.html             # coquille + chargement des librairies locales
├── vendor/                # librairies UI copiées en local (licences à côté)
│   ├── lucide.min.js      # icônes (ISC) — utilisées via icone(nom), stroke 1.5
│   ├── nouislider.min.*   # curseur de périmètre (MIT)
│   ├── swiper-bundle.min.*# carrousels de « Pour vous » (MIT)
│   ├── gsap.min.js        # animations (GreenSock Standard License, gratuite)
│   └── leaflet/           # carte des sorties (BSD-2) — tuiles OpenStreetMap assombries en CSS
└── assets/
    ├── app.css            # design system (variables :root), composants, thèmes noUiSlider/Swiper
    ├── app.js             # état, écrans, actions, appels API
    └── fonts/             # Outfit (titres), Inter (texte), JetBrains Mono (chiffres) — OFL
```

## Règles de design (strictes)
- **Zéro émoji.** Icônes : uniquement `icone(nom)` (données de `vendor/lucide.min.js`, SVG stroke 1.5, aucune passe DOM).
- Fond : dégradé bleu nuit `#0B0F19` → `#121726` + halos radiaux indigo/violet (sur `.app`).
- Typographie : `--police-titres` (Outfit, chasse resserrée), `--police-texte` (Inter), `.chiffre` / `--police-chiffres`
  (JetBrains Mono, `tabular-nums`) **seulement** pour les nombres (km, tarifs, années, horaires, participants).
- Couleurs via variables ; `--accent` (champagne) réservé à Pépite, Hors piste, curseurs et actions collaboratives.
- Profondeur : halo `.app::before`, verre dépoli `--verre` + `backdrop-filter`, bordures `--trait`.
- Ratios stricts : `.visuel.affiche` 2/3 (films, séries, livres), `.visuel.paysage` 16/10 (sorties, jeux), `.voile` pour la lisibilité.

## Composants
- Confort ↔ Découverte : contrôle segmenté `PALIERS` (Sur mesure 0, Équilibré 0.3, Exploration 0.6, Hors piste 1), pilule
  animée en CSS (`--index`), sous-titre qui change ; action `palier`.
- Cartes : survol/toucher = `translateY(-4px) scale(1.015)` + bordure lumineuse (`--lueur`) + ombre douce.
- Sorties : bascule Liste / Carte (`etat.vueSorties`) ; `monterCarte()` (Leaflet, cercle du périmètre, repères, clic = fiche).
  CartoDB Dark Matter exige désormais une clé (filigrane « API KEY REQUIRED ») : tuiles OpenStreetMap + `.tuiles-sombres`.
- `monterComposants(racine)` après **chaque** rendu : noUiSlider (`#rayon-ui`), Swiper (`.swiper.rangee`), carte Leaflet,
  apparition des cartes en cascade (GSAP). `rendreContenu()` ne remplace que `#contenu` (les curseurs survivent).
- Animations : seulement si `MOUVEMENT` (GSAP présent et pas `prefers-reduced-motion`). Classe `html.anime` = GSAP actif.
- Fiche détaillée : clic sur le visuel ou le titre d'une carte (`data-action="ouvrir-plans"`) -> bottom sheet `#feuille`
  (`detailOeuvre()` + plans). Ouverture/fermeture animées (`animerOuvertureFeuille`, `fermerFeuille`).
- Questionnaire = profil durable seulement (prénom, ville, genres, thèmes, abonnements, consoles). Plus d'« envies » :
  l'envie du moment = l'onglet. Pour vous mélange films + séries, + livres si thèmes, + jeux si consoles.
- Plateformes : badges seulement quand elles existent, jamais de message technique.
- Chez soi : segments Tout / Films & Séries / Lecture / Jeux vidéo ; filtres dédiés dans `filtresChezSoi()`
  (thèmes de lecture ; machine et mode de jeu).
- Types de contenus : table `TYPES` ; état par compte dans `localStorage` (`ennui.v4.*`), accès sous try/catch.
- Plateformes : afficher seulement si `plateformes_verifiees`. Liens de rendez-vous cliquables seulement en `https://`.

## Lancement et captures
Via le backend : `uvicorn backend.main:app --reload`. Captures headless : `--force-prefers-reduced-motion`,
`--virtual-time-budget` long ; l'accueil « On fait koi ? » s'affiche à chaque ouverture (cliquer « C'est parti ! »).
