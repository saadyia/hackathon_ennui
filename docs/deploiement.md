# Déploiement de « ofk? »

Le serveur sert l'API **et** le frontend sur le même port : un seul service suffit.
Il écoute sur `0.0.0.0`, lit `PORT` (8000 par défaut) et n'a besoin d'aucun calcul au démarrage
(les données pré-calculées de `backend/data/` sont versionnées). Image Docker : ~23 Mo de code et de données,
dépendances d'exécution sans pandas (`backend/requirements.txt`).

## Option 1 : Render (lien HTTPS permanent, gratuit)
1. Pousser le dépôt sur GitHub.
2. Render > **New > Blueprint** > choisir le dépôt : `render.yaml` crée le service Docker.
3. Attendre « Live », puis ouvrir `https://<nom>.onrender.com`. Vérification : `/api/sante`.
- Plan gratuit : mise en veille après 15 min sans visite (réveil 30 à 60 s) ; ouvrir le lien juste avant la démo.
- SQLite est sur un disque éphémère : comptes, amis et plans sont perdus à chaque redéploiement
  (les 4 profils de démo sont recréés au démarrage). Disque persistant sur `/app/backend/data` si besoin.

## Option 2 : Railway
New Project > Deploy from GitHub : le `Dockerfile` est détecté, `PORT` est fourni. Générer un domaine
dans Settings > Networking. Même remarque sur la persistance (ajouter un volume sur `/app/backend/data`).

## Option 3 : tunnel depuis son ordinateur (le plus simple pour une démo, données conservées)
```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
brew install cloudflared        # une seule fois
cloudflared tunnel --url http://localhost:8000   # affiche un lien https://….trycloudflare.com
```
Le lien HTTPS permet d'installer la PWA sur iPhone. L'ordinateur doit rester allumé et connecté.

## Docker en local
```bash
docker build -t ofk .
docker run -p 8000:8000 ofk            # http://localhost:8000
docker run -p 8000:8000 -e ENNUI_SYNC=0 ofk   # sans synchronisation de l'agenda (hors ligne)
```

## Variables d'environnement
| Variable | Défaut | Rôle |
|---|---|---|
| `PORT` | 8000 | port d'écoute (fourni par Render / Railway) |
| `ENNUI_SYNC` | 1 | synchronisation OpenAgenda toutes les 6 h ; 0 pour la couper |
| `ENNUI_ORIGINES` | `*` | CORS : origines autorisées, séparées par des virgules |
| `TMDB_API_KEY` | — | facultatif (scripts d'enrichissement) ; jamais dans le dépôt |

## Avant la démo
- Rafraîchir les sorties en local (`python3 backend/fetch_france.py`), reconstruire, commiter, pousser :
  le service redéployé part d'un agenda frais (sinon la synchro auto s'en charge au bout de 6 h).
- Tester sur un téléphone en 4G, pas seulement en Wi-Fi.
