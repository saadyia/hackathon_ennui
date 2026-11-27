"""
Import et francisation du catalogue de livres (hors ligne).

Entrée : un export GoodReads en CSV (colonnes : title, author, rating, num_ratings, num_reviews,
         genres, description, image_url, pages, publication_date, url). Pas de colonne ISBN.
Sortie : backend/data/livres.json (versionné).

Étapes :
  1. filtre les LIVRES_MAX (2 500) livres les plus lus parmi ceux bien notés (note >= NOTE_MIN),
     une seule édition par couple (titre, auteur) ;
  2. traduit les genres anglais vers les genres de l'application (mêmes identifiants que les
     films : l'interface les affiche en français) ;
  3. cherche l'édition FRANÇAISE sur OpenLibrary (titre + auteur, sans clé) : titre français et
     couverture de cette édition. Google Books (titre + résumé FR) est essayé en option
     (--google-books) : sans clé, son quota est souvent épuisé (HTTP 429).
     Couverture : édition française OpenLibrary, sinon la couverture GoodReads du CSV.
     Aucun texte n'est traduit automatiquement : sans résumé français, on n'affiche pas de résumé.

Reprise possible : les livres déjà enrichis ne sont pas re-téléchargés (cache dans livres.json).

Usage :
    python3 backend/import_books.py --csv ~/Downloads/GoodReadsData.csv [--google-books]
"""

import argparse
import json
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

SORTIE = Path(__file__).resolve().parent / "data" / "livres.json"
UA = "hackathon-ennui/0.1 (projet etudiant)"
LIVRES_MAX = 2500
NOTE_MIN = 3.7
DEBIT_OL = 4  # requêtes / seconde vers OpenLibrary (service bénévole : rester raisonnable)

# genre GoodReads (anglais) -> genre de l'application (identifiants MovieLens, affichés en français)
GENRES = {
    "thriller": "Thriller", "suspense": "Thriller", "mystery": "Mystery", "mystery thriller": "Thriller",
    "crime": "Crime", "detective": "Crime", "true crime": "Crime",
    "science fiction": "Sci-Fi", "dystopia": "Sci-Fi", "science fiction fantasy": "Sci-Fi", "space": "Sci-Fi",
    "cyberpunk": "Sci-Fi", "fantasy": "Fantasy", "magic": "Fantasy", "paranormal": "Fantasy",
    "urban fantasy": "Fantasy", "mythology": "Fantasy", "fairy tales": "Fantasy",
    "horror": "Horror", "gothic": "Horror", "vampires": "Horror",
    "romance": "Romance", "contemporary romance": "Romance", "historical romance": "Romance", "love": "Romance",
    "humor": "Comedy", "comedy": "Comedy", "satire": "Comedy",
    "graphic novels": "Animation", "comics": "Animation", "manga": "Animation", "graphic novels comics": "Animation",
    "adventure": "Adventure", "travel": "Adventure",
    "war": "War", "world war ii": "War", "military fiction": "War", "military history": "War",
    "westerns": "Western", "western": "Western",
    "music": "Musical",
    "childrens": "Children", "young adult": "Children", "middle grade": "Children", "picture books": "Children",
    "nonfiction": "Documentary", "biography": "Documentary", "memoir": "Documentary", "history": "Documentary",
    "science": "Documentary", "self help": "Documentary", "psychology": "Documentary", "philosophy": "Documentary",
    "economics": "Documentary", "politics": "Documentary", "business": "Documentary", "essays": "Documentary",
    "classics": "Drama", "literary fiction": "Drama", "historical fiction": "Drama", "literature": "Drama",
    "contemporary": "Drama", "novels": "Drama", "fiction": "Drama", "poetry": "Drama", "plays": "Drama",
}


def nettoyer(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["num_ratings"] = pd.to_numeric(df["num_ratings"].astype(str).str.replace(",", ""), errors="coerce")
    df = df.dropna(subset=["title", "author", "rating", "num_ratings", "image_url", "url"])
    df = df[(df["rating"] >= NOTE_MIN) & df["image_url"].str.startswith("https://")]
    df = df[~df["image_url"].str.contains("nophoto", na=False)]  # pas de couverture GoodReads
    df["cle"] = df["title"].str.lower().str.strip() + "|" + df["author"].str.lower().str.strip()
    df = df.sort_values("num_ratings", ascending=False).drop_duplicates("cle")
    return df.head(LIVRES_MAX)


def traduire_genres(texte) -> list:
    genres = []
    for g in str(texte or "").split(","):
        g = g.strip().lower()
        if g in GENRES and GENRES[g] not in genres:
            genres.append(GENRES[g])
    return genres[:3] or ["Drama"]


def annee(texte):
    m = re.search(r"(\d{4})\s*$", str(texte or ""))
    return int(m.group(1)) if m else None


def identifiant(url: str) -> str:
    m = re.search(r"/show/(\d+)", url)
    return m.group(1) if m else re.sub(r"\W", "", url)[-16:]


class Cadence:
    def __init__(self, par_seconde):
        self.intervalle, self.verrou, self.dernier = 1 / par_seconde, threading.Lock(), 0.0

    def attendre(self):
        with self.verrou:
            pause = self.dernier + self.intervalle - time.monotonic()
            if pause > 0:
                time.sleep(pause)
            self.dernier = time.monotonic()


def http_json(url, cadence: Cadence):
    for essai in range(4):
        cadence.attendre()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429 or e.code >= 500:
                time.sleep(2 ** (essai + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            time.sleep(2 ** essai)
    return None


def edition_francaise(titre, auteur, cadence):
    """OpenLibrary : l'édition française la plus pertinente (titre, couverture), ou None."""
    params = {"q": f"{titre} {auteur}", "lang": "fr", "limit": 1,
              "fields": "key,title,author_name,editions,editions.title,editions.language,editions.cover_i"}
    d = http_json("https://openlibrary.org/search.json?" + urllib.parse.urlencode(params), cadence)
    for doc in (d or {}).get("docs", []):
        auteurs = " ".join(doc.get("author_name") or []).lower()
        if auteur.split()[-1].lower() not in auteurs:  # garde-fou : bon auteur
            continue
        for ed in (doc.get("editions") or {}).get("docs", []):
            if "fre" in (ed.get("language") or []):
                return {"titre_fr": ed.get("title"), "cover_i": ed.get("cover_i")}
    return None


def google_books(titre, auteur, cadence):
    """Titre et résumé français via Google Books (sans clé : quota partagé, souvent épuisé)."""
    q = urllib.parse.urlencode({"q": f'intitle:"{titre}" inauthor:"{auteur}"', "langRestrict": "fr",
                                "maxResults": 1, "printType": "books"})
    try:
        d = http_json("https://www.googleapis.com/books/v1/volumes?" + q, cadence)
    except urllib.error.HTTPError:
        return None
    for item in (d or {}).get("items", []):
        v = item.get("volumeInfo", {})
        if v.get("language") == "fr":
            return {"titre_fr": v.get("title"), "resume_fr": v.get("description")}
    return None


def main():
    parser = argparse.ArgumentParser(description="Import et francisation des livres GoodReads")
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--google-books", action="store_true", help="essayer aussi Google Books (résumés FR)")
    args = parser.parse_args()

    df = pd.read_csv(args.csv, on_bad_lines="skip", low_memory=False,
                     usecols=["title", "author", "rating", "num_ratings", "genres", "image_url",
                              "pages", "publication_date", "url"])
    print(f"CSV : {len(df):,} lignes")
    df = nettoyer(df)
    print(f"Retenus : {len(df)} livres (note >= {NOTE_MIN}, les plus lus, une édition par titre)")

    cache = {}
    if SORTIE.exists():
        cache = {l["id"]: l for l in json.loads(SORTIE.read_text(encoding="utf-8"))["livres"]}

    livres = []
    for r in df.itertuples():
        lid = f"gr-{identifiant(r.url)}"
        livres.append(cache.get(lid) or {
            "id": lid,
            "titre_original": r.title.strip(),
            "titre": r.title.strip(),
            "auteur": r.author.strip(),
            "annee": annee(r.publication_date),
            "pages": int(r.pages) if pd.notna(r.pages) else None,
            "note": float(r.rating),
            "nb_notes": int(r.num_ratings),
            "genres": traduire_genres(r.genres),
            "couverture": r.image_url,
            "resume": None,
            "francais": False,
            "enrichi": False,
        })

    a_faire = [l for l in livres if not l["enrichi"]]
    print(f"Enrichissement FR : {len(a_faire)} livres à interroger")
    cad_ol, cad_gb = Cadence(DEBIT_OL), Cadence(1)

    def enrichir(l):
        fr = edition_francaise(l["titre_original"], l["auteur"], cad_ol)
        if fr and fr.get("titre_fr"):
            l["titre"], l["francais"] = fr["titre_fr"], True
            if fr.get("cover_i"):
                l["couverture"] = f"https://covers.openlibrary.org/b/id/{fr['cover_i']}-L.jpg"
        if args.google_books:
            gb = google_books(l["titre_original"], l["auteur"], cad_gb)
            if gb:
                l["titre"], l["francais"] = gb.get("titre_fr") or l["titre"], True
                l["resume"] = gb.get("resume_fr")
        l["enrichi"] = True
        return l

    faits = 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        for _ in as_completed([pool.submit(enrichir, l) for l in a_faire]):
            faits += 1
            if faits % 250 == 0:
                SORTIE.write_text(json.dumps({"livres": livres}, ensure_ascii=False), encoding="utf-8")
                print(f"  {faits}/{len(a_faire)}")
                sys.stdout.flush()

    SORTIE.write_text(json.dumps({
        "source": "GoodReads (CSV local) + OpenLibrary (éditions françaises)",
        "livres": livres,
    }, ensure_ascii=False), encoding="utf-8")
    fr = sum(1 for l in livres if l["francais"])
    print(f"Écrit {len(livres)} livres dans {SORTIE} : {fr} avec édition française trouvée, "
          f"{sum(1 for l in livres if l['resume'])} avec résumé FR, 100 % avec couverture")


if __name__ == "__main__":
    main()
