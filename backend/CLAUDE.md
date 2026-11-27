# CLAUDE.md — backend

> Complète le CLAUDE.md racine. Ne répéter ici que ce qui est spécifique au backend.

## Stack
Python 3.9+, FastAPI, NumPy, SciPy (matrices creuses), Pandas (scripts hors ligne seulement). Réseau : `urllib` (stdlib).

## Commandes (depuis la racine du dépôt)
```bash
pip install -r backend/requirements.txt
python3 backend/fetch_france.py [--jours 35]        # réseau : OpenAgenda (40 villes)
python3 backend/fetch_series.py [--nb 220]          # réseau : TVmaze
python3 backend/enrich_tmdb.py --movielens /chemin/ml-latest-small   # clé TMDB_API_KEY (env ou .env)
python3 backend/build_graph.py --movielens /chemin/ml-latest-small
uvicorn backend.main:app --reload                   # ENNUI_SYNC=0 pour couper la synchro auto
```

## Structure
```
backend/
├── fetch_france.py    # hors ligne : événements à venir -> data/france.json
├── fetch_series.py    # hors ligne : séries TVmaze -> data/series.json
├── enrich_tmdb.py     # hors ligne : TMDB (affiches, FR.flatrate) -> data/tmdb.json
├── build_graph.py     # hors ligne : tout -> data/processed/
├── moteur.py          # classe Moteur (calcul pur, testable sans HTTP)
├── main.py            # FastAPI : routes, /assets, comptes, plans, agenda
├── database.py        # SQLite : utilisateurs, plans, participants, messages, meta
├── scheduler.py       # synchro OpenAgenda toutes les 6 h + reconstruction à chaud
├── plateformes.py     # IDs TMDB des plateformes
└── data/
    ├── france.json    # versionné (repli hors ligne)
    ├── tmdb.json      # créé par enrich_tmdb.py (à versionner une fois créé)
    ├── series.json    # versionné (repli hors ligne)
    ├── raw/           # dataset MovieLens (non versionné)
    ├── ennui.sqlite3  # base locale (NON versionnée)
    └── processed/     # S_films.npz, P.npz, pi_star.npy, noeuds.json
```

## Conventions
- Réglages du moteur : constantes en tête de `moteur.py` (`CONFORT`, `DECOUVERTE`, `FILMS_PAR_GENRE`, `PART_DEJA_VUS`, `EPS_AFFINITE`).
- Après une modification d'un `fetch_*` ou de `build_graph.py` : relancer le build, puis vérifier la latence (< 20 ms) et la variété des résultats selon les genres.
- `noeuds.json` est **dans l'ordre des indices de P** (films, séries, sorties) : ne jamais le trier ni le filtrer à part.
- Un même nom de champ doit garder le même type pour tous les nœuds (ex. `fin` = date ISO des événements ; les séries utilisent `annee_fin`).
- Les scripts `fetch_*` gardent le fichier existant si la source est injoignable. Ne jamais écraser un bon fichier par un fichier vide.
- Sur macOS, NumPy 2 + Accelerate émet de faux warnings sur `@` : utiliser `np.errstate` localement.
- Plateformes : ne JAMAIS en déduire ni en simuler. Seul `enrich_tmdb.py` les écrit, depuis `results.FR.flatrate`.
- Dates : tout calcul temporel passe par `moteur.fenetres()` (Europe/Paris). Les occurrences gardent leurs vraies heures.
- Accès au moteur : toujours via `Catalogue.moteur`, lu **une fois** en début de requête (il peut être remplacé à chaud).
- `build_graph.assembler()` est partagé entre le build complet et `reconstruire_externes()` : ne pas dupliquer cette logique.
- Écritures de fichiers de données : toujours atomiques (`.tmp` puis `os.replace`).
- La clé TMDB ne doit jamais apparaître dans le code ni dans les logs ; `.env` est dans `.gitignore`.
