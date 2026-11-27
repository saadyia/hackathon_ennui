"""
Affiches officielles et titres français des FILMS, sans clé d'API (filet de sécurité avant TMDB).

Pourquoi pas iTunes ? La recherche de films de l'iTunes Search API renvoie 0 résultat pour
toute requête (vérifié le 27/11/2026, y compris « matrix », pays fr ou us) : inutilisable.

Chaîne utilisée :
  1. Wikidata (API wbsearch « haswbstatement:P345=… », 50 films par requête) : identifiant IMDb
     fourni par MovieLens -> élément Wikidata -> libellé français et articles Wikipédia ;
  2. Wikipédia anglophone, prop=pageimages&pilicense=any : image principale de l'article, c'est-à-dire
     l'affiche officielle (image non libre hébergée par Wikipédia, en basse définition ~250 px).

Les séries ont déjà leur affiche (TVmaze, ~680 px). TMDB (enrich_tmdb.py), s'il est lancé,
reste prioritaire : affiches w342 et plateformes vérifiées.

Limites Wikimedia : sans contact dans le User-Agent, les API répondent vite 429 (constaté :
blocage après ~100 films). Le script est donc lent exprès (1 requête / 2 s), s'arrête proprement
au premier blocage persistant et reprend là où il en était. Pour un débit normal, définir un
contact (URL ou e-mail) : ENNUI_CONTACT="https://…" — voir
https://www.mediawiki.org/wiki/Wikimedia_APIs/Rate_limits

Sortie : backend/data/affiches.json  {"films": {movieId: {affiche, titre_fr, wikidata}}}
Usage :
    python3 backend/enrich_affiches.py --movielens /chemin/ml-latest-small
"""

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

RACINE = Path(__file__).resolve().parent
SORTIE = RACINE / "data" / "affiches.json"
DEFAUT_MOVIELENS = RACINE / "data" / "raw" / "ml-latest-small"
CONTACT = os.environ.get("ENNUI_CONTACT", "").strip()
UA = f"hackathon-ennui/0.1 ({CONTACT})" if CONTACT else "hackathon-ennui/0.1 (projet etudiant)"
LOT = 25
PAUSE = 2.0 if not CONTACT else 0.5


class Bloque(Exception):
    """Wikimedia limite le débit (429 persistant) : on s'arrête et on reprendra plus tard."""
SEUIL = 3.5


def get(url, params):
    u = url + "?" + urllib.parse.urlencode(params)
    for essai in range(3):
        time.sleep(PAUSE)
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                if essai == 2:
                    raise Bloque(url)
                time.sleep(30 * (essai + 1))
                continue
            if e.code >= 500:
                time.sleep(10)
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            time.sleep(10)
    raise RuntimeError(f"Abandon : {url}")


def titre_fr_depuis_article(titre):
    """« Les Évadés (film, 1994) » -> « Les Évadés »."""
    return re.sub(r"\s*\((film|téléfilm)[^)]*\)\s*$", "", titre).strip()


def lot_wikidata(imdb_ids):
    """{imdb: {enwiki, titre_fr, wikidata}} pour un lot d'identifiants IMDb."""
    r = get("https://www.wikidata.org/w/api.php", {
        "action": "query", "list": "search", "format": "json", "srlimit": LOT,
        "srsearch": "haswbstatement:" + "|".join(f"P345={i}" for i in imdb_ids)})
    qids = [x["title"] for x in r["query"]["search"]]
    if not qids:
        return {}
    r = get("https://www.wikidata.org/w/api.php", {
        "action": "wbgetentities", "ids": "|".join(qids), "props": "claims|sitelinks|labels",
        "languages": "fr", "sitefilter": "enwiki|frwiki", "format": "json"})
    voulus, out = set(imdb_ids), {}
    for qid, e in r.get("entities", {}).items():
        sl = e.get("sitelinks", {})
        titre_fr = (e.get("labels", {}).get("fr", {}).get("value")
                    or (titre_fr_depuis_article(sl["frwiki"]["title"]) if "frwiki" in sl else None))
        for c in e.get("claims", {}).get("P345", []):
            imdb = c["mainsnak"].get("datavalue", {}).get("value")
            if imdb in voulus:
                out[imdb] = {"enwiki": sl.get("enwiki", {}).get("title"), "titre_fr": titre_fr, "wikidata": qid}
    return out


def lot_affiches(titres):
    """{titre d'article: URL de l'image principale} (redirections suivies)."""
    r = get("https://en.wikipedia.org/w/api.php", {
        "action": "query", "titles": "|".join(titres), "prop": "pageimages", "piprop": "original",
        "pilicense": "any", "redirects": 1, "format": "json"})
    alias = {x["from"]: x["to"] for x in r["query"].get("normalized", []) + r["query"].get("redirects", [])}
    images = {p["title"]: p["original"]["source"].split("?")[0]
              for p in r["query"]["pages"].values() if p.get("original")}
    out = {}
    for t in titres:
        cible = alias.get(alias.get(t, t), alias.get(t, t))
        if cible in images and re.search(r"\.(jpe?g|png|webp)$", images[cible], re.I):
            out[t] = images[cible]
    return out


def main():
    parser = argparse.ArgumentParser(description="Affiches de films via Wikidata + Wikipédia (sans clé)")
    parser.add_argument("--movielens", type=Path, default=DEFAUT_MOVIELENS)
    args = parser.parse_args()

    evals = pd.read_csv(args.movielens / "ratings.csv")
    liens = pd.read_csv(args.movielens / "links.csv")
    aimes = set(evals[evals["rating"] >= SEUIL]["movieId"])
    films = {int(m): f"tt{int(i):07d}" for m, i in zip(liens["movieId"], liens["imdbId"]) if m in aimes}

    cache = json.loads(SORTIE.read_text(encoding="utf-8")) if SORTIE.exists() else {"films": {}}
    a_faire = {m: i for m, i in films.items() if str(m) not in cache["films"]}
    print(f"{len(films)} films, {len(cache['films'])} déjà traités, {len(a_faire)} à faire")

    items = list(a_faire.items())
    for debut in range(0, len(items), LOT):
        lot = items[debut:debut + LOT]
        try:
            wd = lot_wikidata([i for _, i in lot])
            titres = sorted({v["enwiki"] for v in wd.values() if v["enwiki"]})
            affiches = lot_affiches(titres) if titres else {}
        except Bloque:
            print("Wikimedia limite le débit (429) : arrêt propre, relancer plus tard "
                  "(ou définir ENNUI_CONTACT).", flush=True)
            break
        except RuntimeError as e:  # lot ignoré : il sera repris au prochain lancement
            print(f"  lot {debut} ignoré ({e})", flush=True)
            continue
        for movie_id, imdb in lot:
            v = wd.get(imdb, {})
            cache["films"][str(movie_id)] = {
                "affiche": affiches.get(v.get("enwiki")),
                "titre_fr": v.get("titre_fr"),
                "wikidata": v.get("wikidata"),
            }
        if (debut // LOT) % 4 == 0:
            SORTIE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
            print(f"  {min(debut + LOT, len(items))}/{len(items)}", flush=True)


    SORTIE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    n = len(cache["films"])
    print(f"Terminé : {sum(1 for v in cache['films'].values() if v['affiche'])}/{n} affiches, "
          f"{sum(1 for v in cache['films'].values() if v['titre_fr'])}/{n} titres français")


if __name__ == "__main__":
    main()
