# CLAUDE.md — frontend

> Complète le CLAUDE.md racine. Ne répéter ici que ce qui est spécifique au frontend.

## Stack
HTML + CSS écrit à la main + JavaScript vanilla (module ES). **Aucun CDN, aucun build.**
```
frontend/
├── index.html             # coquille + chargement des librairies locales
├── vendor/                # librairies UI copiées en local (licences à côté)
│   ├── lucide.min.js      # icônes (ISC) — utilisées via icone(nom), stroke 1.5
│   ├── nouislider.min.*   # curseurs : Confort ↔ Découverte (1 à 10) et périmètre (MIT)
│   ├── swiper-bundle.min.*# carrousels de « Pour vous » (MIT)
│   ├── gsap.min.js        # animations (GreenSock Standard License, gratuite)
│   ├── leaflet/           # carte des sorties (BSD-2) — tuiles OpenStreetMap assombries en CSS
│   └── dicebear/          # personnages (core MIT ; lorelei CC0, micah CC BY 4.0) — LICENCES.txt
└── assets/
    ├── app.css            # design system (variables :root), composants, thèmes noUiSlider/Swiper
    ├── app.js             # état, écrans, actions, appels API
    └── fonts/             # Plus Jakarta Sans (titres), Inter (texte), JetBrains Mono (chiffres) — OFL
```

## Règles de design (strictes)
- **Zéro émoji.** Icônes : uniquement `icone(nom)` (données de `vendor/lucide.min.js`, SVG stroke 1.5, aucune passe DOM).
- Fond : dégradé bleu nuit `#0B0F19` → `#121726` + léger halo neutre (sur `.app`). Plus aucun indigo : un seul accent.
- Typographie 100 % sans empattement : `--police-titres` (Plus Jakarta Sans 600/700, `-0.025em`) pour le logo, les grands titres
  et les titres de cartes ; `--police-texte` (Inter 400/500) pour tout le reste (boutons, filtres, navigation) ; `.chiffre` / `--police-chiffres`
  (JetBrains Mono, `tabular-nums`) **seulement** pour les nombres (km, tarifs, années, horaires, participants).
- Couleurs via variables ; **un seul accent** `--accent` (champagne) : éléments actifs, curseur 1–10, Pépite / Hors piste, marque-page actif, « ? » du logo.
- Logo : `icons/logo-ofk.svg` (tracés vectoriels Plus Jakarta Sans Bold, lettres `currentColor`, « ? » en `var(--logo-accent)`),
  injecté dans `.marque` au démarrage (`LOGO`) et en ligne dans le splash de `index.html`. Icônes PWA dérivées (`icone.svg`, PNG).
- Splash : `#splash` dans `index.html` (« ofk » glisse vers le haut en fondu, le « ? » rebondit en `cubic-bezier(0.34,1.56,0.64,1)` et luit,
  sous-titre « On fait quoi ? » à 0,8 s), retiré par `fermerSplash()` après le premier rendu, 1,4 s minimum.
- Avatars : module `assets/avatar.js` (DiceBear local : `avatarsPrets` attendu au démarrage, `renderAvatar(config, size, prenom, {zoom})`,
  `STYLES` avec les vraies valeurs `hair` / `glasses` / `mouth` / `eyes`, `FONDS`, `avatarDe`, `avatarDepuisPrenom`, `avatarAleatoire`),
  importé par `app.js`. Liseré `0 0 0 1px rgba(255,255,255,.14)`. Studio : onglets Style / Fond / Coiffure / Détails (Lunettes,
  Expression, Regard) + Aléatoire (nouveau personnage), vignettes zoomées sur le visage. `etat.avatar` (null = déduit du prénom) ; anneau lumineux `.avatar.anneau` si l'humeur est active.
- Amis : `social` (code, amis, suggestions) + `etat.dispo` chargés par `chargerSocial()` (démarrage, connexion, toutes les 60 s),
  mis à jour en place (`rafraichirSocial`). `rangeeAvatars()` en haut de Pour vous : moi (badge +, popover `#popover-humeur`),
  amis actifs (tap = étiquette d'humeur), « Amis ». `blocsPourVous()` ordonne les rangées selon l'humeur. Tiroirs
  `feuille.mode` `"amis"` (`panneauAmis`) et `"avatar"` (`panneauStudio` : aperçu, Aléatoire, onglets Fond / Coupe / Accessoire /
  Expression). `blocCode()` dans Profil ; `apercuInscription()` dans le questionnaire.
- Profondeur : halo `.app::before`, verre dépoli `--verre` + `backdrop-filter`, bordures `--trait`.
- Ratios stricts : `.visuel.affiche` 2/3 (films, séries, livres), `.visuel.paysage` 16/10 (sorties, jeux), `.voile` pour la lisibilité.

## Composants
- Confort ↔ Découverte : curseur continu noUiSlider **1 à 10** (`cran()`, `versDecouverte(c) = (c-1)/9`), badge `n/10`,
  libellé et aide qui évoluent (`LIBELLES_CRANS`, `AIDES_CRANS`), rechargement partiel à chaque cran.
- Transitions : changement d'onglet / sous-onglet = glissement horizontal + fondu (`transitionEcran(direction)`, `expo.out`) ;
  filtres = mise à jour en place (`choisirDansGroupe`) + rechargement partiel en fondu (`rendreContenu`, hauteur conservée).
- Cartes de films, séries, livres : extrait du synopsis (`.extrait`, 3 lignes).
- PWA : `manifest.json`, `sw.js` (servis à la racine par FastAPI), `icons/` (SVG + PNG générés depuis `icone.svg`),
  balises Apple dans `index.html`. Service worker : réseau d'abord pour la page et le code, cache d'abord pour vendor/polices/icônes,
  jamais de cache pour `/api/`. Incrémenter `VERSION` dans `sw.js` si la liste des fichiers de la coquille change.
- Cartes : survol/toucher = `translateY(-4px) scale(1.015)` + bordure claire + ombre douce ; arête supérieure éclairée ;
  tous les boutons, onglets et puces : `:active { transform: scale(0.98) }`.
- Chez soi : sous-onglets à pilule glissante (`.segment-pilule` + `.segment-indicateur`, `--index`) ; zone `#zone-chez-soi` à hauteur
  verrouillée, fondu `opacity` + `translateY(6px)` 220 ms `cubic-bezier(0.22,1,0.36,1)` (`rendreZone`).
- Filtres contextuels : « Temps disponible » seulement dans Films & Séries et Sorties (`dureeVisible()`) ; jeux : Solo / Multijoueur (co-op inclus).
- « Mes envies » : marque-page (`boutonSauver`, action `sauver`) sur les cartes et dans la fiche ; `etat.envies` synchronisé avec le compte ;
  section dans Profil ; fiche rouverte via `/api/oeuvre?id=` si l'élément n'est plus affiché.
- Temps réel : `synchroniser()` (12 s, onglet visible, réveil sur `visibilitychange` / `focus` / `pageshow`),
  `appliquerChangementsPlans()` (mises à jour ciblées, reportées si `occupe()`), `nouveaux` (Map plan -> œuvre) ->
  `pastilleNouveau()`, `marquerOngletNouveau()` ; `pileMembres()` (avatars des participants).
- Billetterie des sorties : `tagBillet(o)` (Entrée libre, Sur réservation, Complet) sur les cartes et la fiche,
  `lienReservation(o)` (« Réserver » en https, ou téléphone).
- PIN : `reprendreProfil(code, pin)` (403 -> étape PIN dans le tiroir de reprise), `panneauPin()` (Profil), `etat.pinActif` ;
  champs `.champ-pin` (chiffres seulement, JetBrains Mono).
- Comptes : `reprendreProfil(code)`, tiroir `feuille.mode === "reprise"` (`panneauReprise`, `chargerProfils`) ;
  au démarrage, `api()` expose `erreur.status` : seul un 401 fait oublier le compte.
- « Choisir à ma place » : `candidatsTirage()` = tout le pool affiché, `dernierTirage` évite la répétition, effet ~500 ms.
- États vides : `.etat-vide` + bouton « Réinitialiser les filtres » (budget, temps, mode, envies, horizon « Dans le mois »).
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
