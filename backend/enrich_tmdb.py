"""
Enrichissement hors ligne via l'API TMDB : affiche, titre FR, résumé et plateformes FR
pour TOUS les films et séries du catalogue.

Règle stricte sur les plateformes : on lit UNIQUEMENT results["FR"]["flatrate"]
(abonnements inclus en France). Jamais rent, buy, free ni ads. Un titre n'apparaît sous
Netflix que si TMDB confirme Netflix en FR.flatrate ; aucune simulation nulle part.

    films  : GET /movie/{tmdb_id}?append_to_response=watch/providers   (id via MovieLens links.csv)
    séries : GET /find/{imdb_id|tvdb_id}  puis  GET /tv/{tmdb_id}?append_to_response=watch/providers
             (append_to_response renvoie exactement /…/{id}/watch/providers, en une seule requête)

Ne tourne JAMAIS pendant la démo : écrit backend/data/tmdb.json, fusionné par build_graph.py.

Clé : variable d'environnement TMDB_API_KEY, ou ligne TMDB_API_KEY=... dans le fichier .env
à la racine du dépôt (ignoré par git). Clé v3 (32 caractères) ou jeton de lecture v4.

Usage (depuis la racine) :
    python3 backend/enrich_tmdb.py --movielens /chemin/ml-latest-small [--rafraichir]
    python3 backend/build_graph.py --movielens /chemin/ml-latest-small
"""

import argparse
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

RACINE = Path(__file__).resolve().parent
SORTIE = RACINE / "data" / "tmdb.json"
SERIES = RACINE / "data" / "series.json"
DEFAUT_MOVIELENS = RACINE / "data" / "raw" / "ml-latest-small"
API = "https://api.themoviedb.org/3"
SEUIL = 3.5
DEBIT_MAX = 35  # requêtes / seconde (limite TMDB ≈ 50)

# provider_id TMDB (FR.flatrate) -> plateforme de l'application.
# Les offres « avec publicité » sont le même abonnement que l'offre principale.
FOURNISSEURS = {
    8: 8, 1796: 8,                 # Netflix, Netflix Standard avec pub
    119: 119, 9: 119, 2100: 119,   # Amazon Prime Video (+ variantes d'id)
    337: 337,                      # Disney+
    381: 381,                      # Canal+
    234: 234,                      # Arte
    350: 350,                      # Apple TV+
}


def lire_cle() -> str:
    cle = os.environ.get("TMDB_API_KEY", "").strip()
    env = RACINE.parent / ".env"
    if not cle and env.exists():
        for ligne in env.read_text(encoding="utf-8").splitlines():
            if ligne.strip().startswith("TMDB_API_KEY="):
                cle = ligne.split("=", 1)[1].strip().strip('"').strip("'")
    return cle


class Client:
    def __init__(self, cle: str):
        self.cle = cle
        self.verrou = threading.Lock()
        self.dernier = 0.0

    def get(self, chemin: str, params: dict) -> dict:
        params = dict(params)
        entetes = {"Accept": "application/json"}
        if len(self.cle) > 40:  # jeton v4 (JWT)
            entetes["Authorization"] = f"Bearer {self.cle}"
        else:
            params["api_key"] = self.cle
        url = f"{API}{chemin}?{urllib.parse.urlencode(params)}"
        for essai in range(5):
            with self.verrou:  # cadence globale entre les threads
                attente = self.dernier + 1 / DEBIT_MAX - time.monotonic()
                if attente > 0:
                    time.sleep(attente)
                self.dernier = time.monotonic()
            try:
                req = urllib.request.Request(url, headers=entetes)
                with urllib.request.urlopen(req, timeout=15) as r:
                    return json.load(r)
            except urllib.error.HTTPError as e:
                if e.code == 429 or e.code >= 500:
                    time.sleep(2 ** essai)
                    continue
                raise
            except (urllib.error.URLError, TimeoutError):
                time.sleep(2 ** essai)
        raise RuntimeError(f"Abandon : {chemin}")


def plateformes_flatrate(d: dict) -> list:
    """UNIQUEMENT results.FR.flatrate. Liste vide = vérifié, sur aucune plateforme suivie."""
    fr = (d.get("watch/providers") or {}).get("results", {}).get("FR", {})
    return sorted({FOURNISSEURS[p["provider_id"]] for p in fr.get("flatrate", [])
                   if p.get("provider_id") in FOURNISSEURS})


def fiche(d: dict, titre_cle: str) -> dict:
    return {
        "tmdb_id": d.get("id"),
        "titre_fr": d.get(titre_cle),
        "poster_path": d.get("poster_path"),
        "overview": d.get("overview") or None,
        "plateformes": plateformes_flatrate(d),
        "verifie_le": datetime.now(timezone.utc).date().isoformat(),
    }


def film(client, movie_id, tmdb_id):
    d = client.get(f"/movie/{tmdb_id}", {"language": "fr-FR", "append_to_response": "watch/providers"})
    return "films", str(movie_id), fiche(d, "title")


def serie(client, s):
    tv_id = None
    for source, valeur in (("imdb_id", s.get("imdb")), ("tvdb_id", s.get("tvdb"))):
        if valeur and not tv_id:
            r = client.get(f"/find/{valeur}", {"external_source": source})
            if r.get("tv_results"):
                tv_id = r["tv_results"][0]["id"]
    if not tv_id:
        return "series", str(s["tvmaze_id"]), None
    d = client.get(f"/tv/{tv_id}", {"language": "fr-FR", "append_to_response": "watch/providers"})
    return "series", str(s["tvmaze_id"]), fiche(d, "name")


def main():
    parser = argparse.ArgumentParser(description="Enrichissement TMDB (affiches + plateformes FR.flatrate)")
    parser.add_argument("--movielens", type=Path, default=DEFAUT_MOVIELENS)
    parser.add_argument("--rafraichir", action="store_true", help="re-télécharger même ce qui est en cache")
    args = parser.parse_args()

    cle = lire_cle()
    if not cle:
        print("TMDB_API_KEY absente (ni variable d'environnement, ni .env) : rien à faire.\n"
              "Sans TMDB, les cartes affichent « Disponibilité non vérifiée » et une affiche typographique.")
        sys.exit(0)
    client = Client(cle)
    try:
        client.get("/configuration", {})
    except urllib.error.HTTPError as e:
        sys.exit(f"Clé TMDB refusée ({e.code}). Vérifier TMDB_API_KEY.")

    cache = {"films": {}, "series": {}}
    if SORTIE.exists() and not args.rafraichir:
        ancien = json.loads(SORTIE.read_text(encoding="utf-8"))
        if "films" in ancien:  # ignore l'ancien format (sans séries ni règle flatrate)
            cache = ancien

    evals = pd.read_csv(args.movielens / "ratings.csv")
    liens = pd.read_csv(args.movielens / "links.csv").dropna(subset=["tmdbId"])
    aimes = set(evals[evals["rating"] >= SEUIL]["movieId"])
    films = [(int(m), int(t)) for m, t in zip(liens["movieId"], liens["tmdbId"])
             if m in aimes and str(int(m)) not in cache["films"]]
    series = [s for s in json.loads(SERIES.read_text(encoding="utf-8"))["series"]
              if str(s["tvmaze_id"]) not in cache["series"]]
    print(f"En cache : {len(cache['films'])} films, {len(cache['series'])} séries. "
          f"À télécharger : {len(films)} films, {len(series)} séries.")

    erreurs, faits = 0, 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        taches = [pool.submit(film, client, m, t) for m, t in films]
        taches += [pool.submit(serie, client, s) for s in series]
        for tache in as_completed(taches):
            try:
                genre, cle_id, valeur = tache.result()
                if valeur is not None:
                    cache[genre][cle_id] = valeur
                else:
                    erreurs += 1
            except Exception:  # 404 (film retiré de TMDB) ou abandon réseau : on continue
                erreurs += 1
            faits += 1
            if faits % 500 == 0:
                SORTIE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
                print(f"  {faits}/{len(taches)}")

    SORTIE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    sur_plateforme = sum(1 for g in ("films", "series") for v in cache[g].values() if v["plateformes"])
    print(f"Terminé : {len(cache['films'])} films, {len(cache['series'])} séries "
          f"({sur_plateforme} sur au moins une plateforme suivie), {erreurs} introuvable(s).")
    print("Relancer build_graph.py pour intégrer ces données.")


if __name__ == "__main__":
    main()
