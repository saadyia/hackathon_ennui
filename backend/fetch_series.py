"""
Récupère un catalogue de séries populaires via l'API publique TVmaze (sans clé).
https://www.tvmaze.com/api — données sous licence CC BY-SA.

Sortie : backend/data/series.json (versionné : repli si le réseau tombe).

Plateformes : AUCUNE n'est déduite ici (la chaîne d'origine ne dit rien de la disponibilité
en France). Seul enrich_tmdb.py les renseigne, depuis TMDB watch/providers FR.flatrate,
en retrouvant chaque série par ses identifiants IMDb / TheTVDB stockés ici.

Usage :
    python3 backend/fetch_series.py [--nb 220]
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SORTIE = Path(__file__).resolve().parent / "data" / "series.json"
UA = "hackathon-ennui/0.1 (projet etudiant)"
API = "https://api.tvmaze.com"
PAGES = 14  # ~3500 séries parcourues (250 par page, triées par id)

# genres TVmaze -> genres MovieLens
GENRES = {
    "Drama": "Drama", "Comedy": "Comedy", "Science-Fiction": "Sci-Fi", "Thriller": "Thriller",
    "Action": "Action", "Crime": "Crime", "Horror": "Horror", "Romance": "Romance",
    "Adventure": "Adventure", "Fantasy": "Fantasy", "Mystery": "Mystery", "Family": "Children",
    "Children": "Children", "Anime": "Animation", "Supernatural": "Fantasy", "War": "War",
    "Western": "Western", "Music": "Musical", "History": "Drama", "Espionage": "Thriller",
    "Legal": "Drama", "Medical": "Drama", "Sports": "Drama", "Nature": "Documentary",
}

def http_json(url):
    for essai in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}),
                                        timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429 and essai < 4:
                time.sleep(3 * (essai + 1))
                continue
            if e.code == 404:
                return []
            raise


def resume(html):
    if not html:
        return None
    texte = re.sub(r"<[^>]+>", "", html).strip()
    return texte[:400] + ("…" if len(texte) > 400 else "")


def main():
    parser = argparse.ArgumentParser(description="Catalogue de séries TVmaze")
    parser.add_argument("--nb", type=int, default=220)
    args = parser.parse_args()

    shows = []
    try:
        for page in range(PAGES):
            lot = http_json(f"{API}/shows?page={page}")
            if not lot:
                break
            shows += lot
            time.sleep(0.6)  # limite TVmaze : 20 requêtes / 10 s
    except (urllib.error.URLError, TimeoutError) as e:
        if SORTIE.exists():
            print(f"TVmaze injoignable ({e}) : on garde {SORTIE.name} existant.")
            sys.exit(0)
        sys.exit(f"TVmaze injoignable ({e}) et aucun fichier de repli.")
    print(f"TVmaze : {len(shows)} séries parcourues")

    retenues = [
        s for s in shows
        if s.get("image") and s.get("genres") and s.get("type") in ("Scripted", "Animation", "Documentary")
        and (s.get("rating") or {}).get("average") and s["rating"]["average"] >= 7.0
        and s.get("language") in ("English", "French", "Spanish", "Korean", "Japanese", "German", "Danish")
    ]
    retenues.sort(key=lambda s: (-s.get("weight", 0), -s["rating"]["average"]))

    series = []
    for s in retenues[: args.nb]:
        genres = []
        for g in s["genres"]:
            if GENRES.get(g) and GENRES[g] not in genres:
                genres.append(GENRES[g])
        if s["type"] == "Animation" and "Animation" not in genres:
            genres.insert(0, "Animation")
        if s["type"] == "Documentary" and "Documentary" not in genres:
            genres.insert(0, "Documentary")
        chaines = [c["name"] for c in (s.get("webChannel"), s.get("network")) if c]
        ext = s.get("externals") or {}
        series.append({
            "tvmaze_id": s["id"],
            "titre": s["name"],
            "annee": int(s["premiered"][:4]) if s.get("premiered") else None,
            "fin": int(s["ended"][:4]) if s.get("ended") else None,
            "genres": genres[:3],
            "note": s["rating"]["average"],
            "popularite": s.get("weight", 0),
            "chaine": chaines[0] if chaines else None,
            "imdb": ext.get("imdb"),
            "tvdb": ext.get("thetvdb"),
            "affiche": s["image"].get("original") or s["image"].get("medium"),
            "affiche_mini": s["image"].get("medium"),
            "resume": resume(s.get("summary")),
            "langue": s.get("language"),
            "url": s.get("url"),
        })

    SORTIE.write_text(json.dumps({"source": "TVmaze (CC BY-SA)", "series": series},
                                 ensure_ascii=False, indent=1), encoding="utf-8")
    avec = sum(1 for s in series if s["imdb"] or s["tvdb"])
    print(f"Écrit {len(series)} séries dans {SORTIE} ({avec} avec identifiant IMDb/TVDB pour TMDB)")


if __name__ == "__main__":
    main()
