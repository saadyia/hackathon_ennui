# CLAUDE.md — hackathon_ennui

> Contexte principal du projet. `frontend/` et `backend/` ont leur propre `CLAUDE.md`,
> chargé automatiquement quand Claude travaille dans ces dossiers.

## 1. Vue d'ensemble et objectifs

- **Problème :** l'ennui et l'isolement des étudiants sur des campus excentrés, surtout le week-end.
- **Utilisateurs cibles :** étudiants partout en France (40 villes universitaires couvertes en sorties), sans historique (cold start).
- **Solution :** application web mobile de recommandation culturelle hybride : films, séries et événements
  culturels réels à venir près de chez soi, selon les goûts, la ville, le rayon, l'horizon temporel et les abonnements.
- **Direction artistique :** sobre, éditoriale, haut de gamme (MUBI / DICE / Apple TV). Mode sombre, **zéro émoji**.

### Parcours
1. **Connexion express** « Seul chez soi ne veut pas dire isolé. » : prénom + ville (toute la France, API Adresse) + rayon,
   envies, genres, plateformes. Compte en SQLite + `localStorage`, plusieurs comptes par appareil (changement en 1 clic dans Profil).
2. **Pour vous** (sélection mixte), **Films & Séries** (Tout / Films / Séries), **Sorties** (ville, rayon, horizon, type), **Profil**.
   Horizons : Aujourd'hui / Ce week-end, Dans la semaine, Dans le mois.
3. **Curseur Zone de confort — Découverte** : 0/10 = genres cochés ; 10/10 = hors de ses genres (malus -90 %). Étiquettes « Pépite » / « Hors piste ».
4. **Budget** : Tous les prix, Gratuit, Moins de 10 €, Moins de 25 €.
5. **Déjà vu** : retire l'œuvre et l'ajoute au profil, ce qui affine les recommandations en direct.
6. **Plans collaboratifs** : « Rejoindre » / « Proposer un créneau » (watch-party ou sortie), participants, point de rendez-vous ou lien, messages. « Mes plans » dans Profil.
7. **Agenda synchronisé automatiquement** toutes les 6 h (OpenAgenda), graphe reconstruit à chaud.

### Objectifs du hackathon
- **Priorité absolue :** MVP fluide, sans latence, **aucune dépendance réseau bloquante pendant la démo**.
- **Deadline / livrables / critères du jury :** _à compléter_

## 2. Stack technique et commandes

| Couche      | Technologie |
|-------------|-------------|
| Backend     | Python 3.9+, FastAPI, NumPy, SciPy, Pandas |
| Données     | Pré-calculées en local : `P.npz` (creux), `pi_star.npy`, `noeuds.json` |
| Frontend    | `frontend/index.html` + `assets/app.css` + `assets/app.js` (module ES), CSS écrit à la main, police et icônes Lucide en local |
| Sources     | MovieLens (films), TVmaze (séries), OpenAgenda (sorties France), API Adresse (communes), TMDB (affiches + plateformes FR.flatrate) |

### Commandes (depuis la racine)
```bash
pip install -r backend/requirements.txt
python3 backend/fetch_france.py          # rafraîchit les événements à venir (réseau, ~1 min) — à refaire avant la démo
python3 backend/fetch_series.py          # optionnel : rafraîchit les séries (réseau, ~10 s)
python3 backend/enrich_tmdb.py --movielens /chemin/ml-latest-small   # clé TMDB dans .env (~5 min)
python3 backend/build_graph.py --movielens /chemin/ml-latest-small   # pré-calcul (< 1 s)
uvicorn backend.main:app --reload        # http://127.0.0.1:8000 (ENNUI_SYNC=0 : pas de synchro auto)
# Tests : aucun pour l'instant
```

## 3. Règles d'architecture et conventions de code

- **Séparation stricte :** `fetch_*.py` / `enrich_tmdb.py` (réseau, hors ligne) → `build_graph.py` (hors ligne)
  → `moteur.py` (calcul pur) → `main.py` (HTTP uniquement) → frontend.
- **Réseau à l'exécution :** `/api/communes` (API Adresse, timeout 3 s, repli local) et la synchro de l'agenda en tâche de fond
  (thread, jamais sur le chemin d'une requête). Les fichiers `backend/data/*.json` sont versionnés (repli). Le fichier `tmdb.json` aussi, une fois créé.
- **Persistance :** SQLite `backend/data/ennui.sqlite3` (non versionné). Identifiant de compte = jeton aléatoire dans l'en-tête `X-Utilisateur`.
  Ce n'est pas une authentification (pas de mot de passe) : c'est un outil de démo.
- **Budget de latence :** < 20 ms de calcul par requête (~17 ms). Aucune I/O par requête.
- **Identifiants publics :** `film:<movieId>`, `serie:<tvmazeId>`, `sortie:oa-<uid>` (OpenAgenda).
- **Dates :** jamais d'événement passé. La prochaine occurrence est recalculée à chaque requête (fuseau Europe/Paris).
- **Plateformes :** uniquement TMDB `results.FR.flatrate`. **Aucune simulation.** Une donnée non vérifiée s'affiche « Disponibilité non vérifiée ».
- **Design :** zéro émoji ; icônes Lucide (`stroke-width 1.5`) ; pas de CDN ; couleurs définies uniquement par les variables de `app.css`.
- **Honnêteté des données :** ne jamais inventer de prix, d'horaires, de dates, de plateformes ni de participants. Plus aucune donnée simulée.
- **Langue :** code, commentaires et interface en français.
- **Python 3.9 :** pas de syntaxe `X | None` ; utiliser `typing.Optional` / `List`.

## 4. Fichiers de contexte secondaires

- Spécifications fonctionnelles : @docs/specs.md
- Architecture, données et modèle mathématique : @docs/architecture.md
- Tâches et avancement : @docs/todo.md
- Contrat d'API (lu à la demande) : `docs/api.md`
- Contexte frontend : `frontend/CLAUDE.md`
- Contexte backend : `backend/CLAUDE.md`
