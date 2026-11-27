# CLAUDE.md — frontend

> Complète le CLAUDE.md racine. Ne répéter ici que ce qui est spécifique au frontend.

## Stack
HTML + CSS écrit à la main + JavaScript vanilla (module ES). **Aucun CDN, aucun build.**
```
frontend/
├── index.html             # coquille : #ecran, #onglets, #toast
└── assets/
    ├── app.css            # design system (variables :root), composants
    ├── app.js             # état, écrans, actions, appels API
    ├── icones.js          # icônes Lucide (ISC) copiées en local
    └── fonts/             # Plus Jakarta Sans variable (OFL)
```

## Lancement
Via le backend : `uvicorn backend.main:app --reload` puis http://127.0.0.1:8000

## Règles de design (strictes)
- **Zéro émoji**, y compris dans les catégories et les toasts. Icônes uniquement via `icone(nom)` (Lucide, `stroke-width 1.5`).
  Pour une nouvelle icône : copier le contenu SVG depuis `lucide-static` dans `icones.js`.
- Couleurs seulement via les variables : fond `#0A0A0C`, cartes `#141417`, bordures `rgba(255,255,255,.08)`.
  `--accent` (champagne) est réservé au tag Pépite et au curseur.
- Mobile plein écran ; à partir de 480 px, cadre de 430 px qui défile en interne, avec onglets et bouton d'action en `position: sticky`.

## Conventions
- Rendu par chaînes de gabarits + `esc()` sur **toute** donnée venant de l'API. Les événements passent par la délégation `data-action`.
- Le curseur ne recharge que si le quota `round(s·10)` change. `rendreContenu()` ne remplace que `#contenu` (ne pas casser le glissement).
- Images distantes (TVmaze, OpenAgenda) : toujours au-dessus d'un visuel de repli, avec `onerror="this.remove()"`.
- État par compte dans `localStorage` : `ennui.v4.etat.<uid>`, plus `ennui.v4.comptes` (comptes connus) et `ennui.v4.actif`.
  Accès protégés par try/catch. Les préférences sont aussi poussées sur le serveur (`PUT /api/utilisateurs/moi`, debounce).
  `prefs.ville` = `{nom, contexte, lat, lon}` ou `null`.
- Toute requête porte l'en-tête `X-Utilisateur` (fonction `api()`).
- Types de contenus : table `TYPES` (libellé, icône, « Déjà vu » ou « Déjà lu », nom du plan collectif). Ne pas coder de cas par type ailleurs.
- Feuille : `#feuille` (bottom sheet), état `feuille = {oeuvre, plans}` ou `{mode: "publier"}`, rendu par `rendreFeuille()`.
  Les liens de rendez-vous ne sont cliquables que s'ils commencent par `https://` (`lienSur()`).
- Dates des sorties : uniquement via `libelleDate()` à partir de `prochaine` (fuseau Europe/Paris, jamais l'heure locale du navigateur).
- Plateformes : afficher seulement si `plateformes_verifiees`, sinon « Disponibilité non vérifiée ». Jamais de badge supposé.
- Captures headless : utiliser `--force-prefers-reduced-motion` (sinon les animations restent à opacité 0)
  et une capture directe avec `--virtual-time-budget` long pour voir les images. La largeur minimale de fenêtre en headless est 500 px.
