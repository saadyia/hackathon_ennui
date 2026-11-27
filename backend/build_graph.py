"""
Pré-calcul hors ligne du graphe de recommandation.

Entrées :
    - dataset MovieLens ml-latest-small (ratings.csv, movies.csv, links.csv)
    - backend/data/series.json      séries TVmaze (fetch_series.py)
    - backend/data/france.json      événements à venir en France (fetch_france.py)
    - backend/data/tmdb.json        optionnel, produit par enrich_tmdb.py : affiches et
                                    plateformes FR.flatrate. Sans lui, AUCUNE plateforme n'est
                                    attribuée (jamais de simulation) : plateformes_verifiees=False.
Sorties : backend/data/processed/
    - S_films.npz    co-occurrences élaguées des films seuls (permet de reconstruire le graphe
                     à chaud quand les sorties changent, sans MovieLens : reconstruire_externes)
    - P.npz          matrice de transition creuse (CSR, float32), lignes stochastiques
    - pi_star.npy    état stationnaire global (proxy de popularité, sert au restart biaisé)
    - noeuds.json    métadonnées par nœud, dans l'ordre des indices de P
                     (films, puis séries, puis sorties)

Usage :
    python3 backend/build_graph.py --movielens /chemin/vers/ml-latest-small

Différences avec tipe_final.py (voir docs/architecture.md) :
    - S = AᵀA calculé en creux (au lieu de la double boucle Python en dense)
    - élagage hybride des voisins (sinon P a ~10⁷ entrées et une requête dépasse 20 ms) :
      par film, on garde les K_COMPTAGE plus fortes co-occurrences (les "classiques")
      + les K_COSINUS plus fortes similarités cosinus (les voisins spécifiques, souvent
      moins populaires). Un élagage par comptage seul ne garde que des hubs et rend
      les œuvres de niche inatteignables par la marche. Les poids restent S_ij.
    - séries et sorties ajoutées comme nœuds, reliées aux films par similarité de genres
    - pi_star calculé sur P téléportée (alpha=0.15) : garantit la convergence
"""

import argparse
import json
import os
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse

SEUIL = 3.5            # note minimale pour "aimé"
K_COMPTAGE = 25        # voisins gardés par co-occurrence brute
K_COSINUS = 25         # voisins gardés par similarité cosinus
MIN_COOCCURRENCE = 2   # support minimal pour la sélection cosinus (évite le bruit)
K_FILMS_EXTERNE = 30   # films reliés à chaque série / sortie
PART_EXTERNE = 0.15    # part max. de la ligne d'un film envoyée vers séries / sorties
ALPHA_PI_STAR = 0.15   # téléportation pour le calcul de pi_star
TOL = 1e-10

GENRES = ["Action", "Adventure", "Animation", "Children", "Comedy", "Crime",
          "Documentary", "Drama", "Fantasy", "Film-Noir", "Horror", "Musical",
          "Mystery", "Romance", "Sci-Fi", "Thriller", "War", "Western"]

RACINE = Path(__file__).resolve().parent
DONNEES = RACINE / "data"
SORTIE = DONNEES / "processed"
DEFAUT_MOVIELENS = DONNEES / "raw" / "ml-latest-small"
URL_AFFICHE = "https://image.tmdb.org/t/p/w342"


# ------------------------------------------------------------------ #
# Films                                                                #
# ------------------------------------------------------------------ #

def charger(chemin: Path):
    evals = pd.read_csv(chemin / "ratings.csv")
    films = pd.read_csv(chemin / "movies.csv")
    liens = pd.read_csv(chemin / "links.csv")
    evals = evals[evals["rating"] >= SEUIL].copy()
    return evals, films, liens


def matrice_cooccurrence(evals: pd.DataFrame):
    """S_ij = nb d'utilisateurs ayant aimé i ET j, S_ii = 0."""
    u = pd.Categorical(evals["userId"])
    f = pd.Categorical(evals["movieId"])
    A = sparse.csr_matrix(
        (np.ones(len(evals), dtype=np.float32), (u.codes, f.codes)),
        shape=(len(u.categories), len(f.categories)),
    )
    S = (A.T @ A).tocsr()
    S.setdiag(0)
    S.eliminate_zeros()
    return S, np.asarray(f.categories, dtype=np.int64)


def elaguer_hybride(S: sparse.csr_matrix, nb_likes: np.ndarray,
                    k_comptage=K_COMPTAGE, k_cosinus=K_COSINUS,
                    min_co=MIN_COOCCURRENCE) -> sparse.csr_matrix:
    """Garde, par ligne, l'union des top-k par comptage et des top-k par cosinus."""
    lignes, colonnes, valeurs = [], [], []
    for i in range(S.shape[0]):
        debut, fin = S.indptr[i], S.indptr[i + 1]
        vals = S.data[debut:fin]
        cols = S.indices[debut:fin]
        garde = set(np.argsort(-vals)[:k_comptage].tolist())
        assez = np.where(vals >= min_co)[0]
        if len(assez):
            cos = vals[assez] / np.sqrt(nb_likes[i] * nb_likes[cols[assez]])
            garde |= set(assez[np.argsort(-cos)[:k_cosinus]].tolist())
        garde = np.fromiter(sorted(garde), dtype=np.int64)
        lignes.append(np.full(len(garde), i))
        colonnes.append(cols[garde])
        valeurs.append(vals[garde])
    return sparse.csr_matrix(
        (np.concatenate(valeurs), (np.concatenate(lignes), np.concatenate(colonnes))),
        shape=S.shape, dtype=np.float32,
    )


def vecteurs_genres(liste_genres) -> np.ndarray:
    """Une ligne par élément, indicatrice des GENRES, normalisée (pour le cosinus)."""
    M = np.zeros((len(liste_genres), len(GENRES)))
    pos = {g: j for j, g in enumerate(GENRES)}
    for i, gs in enumerate(liste_genres):
        for g in gs:
            if g in pos:
                M[i, pos[g]] = 1.0
    normes = np.linalg.norm(M, axis=1, keepdims=True)
    normes[normes == 0] = 1.0
    return M / normes


# ------------------------------------------------------------------ #
# Séries et sorties                                                    #
# ------------------------------------------------------------------ #

def relier_externes(S_films: sparse.csr_matrix, genres_films, nb_likes, externes):
    """
    Ajoute des nœuds externes (séries, sorties) au graphe. Pour chaque nœud x :
      - score_f = cos(genres_x, genres_f) * log(1 + likes_f)
      - on relie x aux K_FILMS_EXTERNE films de meilleur score
      - x -> f : poids score_f
      - f -> x : le film f garde au plus PART_EXTERNE de sa masse pour ses nœuds externes,
        répartie également (sinon les films populaires, reliés à des dizaines de séries et
        de sorties, enverraient l'essentiel de la marche hors du catalogue de films)
    """
    n_f, n_x = S_films.shape[0], len(externes)
    # errstate : faux warnings du BLAS Accelerate (macOS) avec NumPy 2.0
    with np.errstate(all="ignore"):
        cos = vecteurs_genres([x["genres"] for x in externes]) @ vecteurs_genres(genres_films).T
    assert np.isfinite(cos).all()
    score = cos * np.log1p(nb_likes)[None, :]

    liens = []  # (x, f, score)
    for x in range(n_x):
        films = np.argsort(-score[x])[:K_FILMS_EXTERNE]
        liens += [(x, int(f), float(score[x, f])) for f in films if score[x, f] > 0]

    somme = np.asarray(S_films.sum(axis=1)).ravel()
    nb_externes = np.bincount([f for _, f, _ in liens], minlength=n_f)

    lignes, colonnes, valeurs = [], [], []
    for x, f, sc in liens:
        lignes += [n_f + x, f]
        colonnes += [f, n_f + x]
        valeurs += [sc, PART_EXTERNE * somme[f] / nb_externes[f]]

    n = n_f + n_x
    S = sparse.bmat([[S_films, None], [None, sparse.csr_matrix((n_x, n_x))]], format="csr")
    S = S + sparse.csr_matrix((valeurs, (lignes, colonnes)), shape=(n, n))
    return S.astype(np.float32).tocsr()


# ------------------------------------------------------------------ #
# Normalisation et état stationnaire                                   #
# ------------------------------------------------------------------ #

def normaliser_lignes(S: sparse.csr_matrix):
    """P_ij = S_ij / sum_k S_ik ; nœud isolé -> boucle sur lui-même (état absorbant)."""
    s = np.asarray(S.sum(axis=1)).ravel()
    isoles = np.where(s == 0)[0]
    if len(isoles):
        S = S + sparse.csr_matrix(
            (np.ones(len(isoles), dtype=np.float32), (isoles, isoles)), shape=S.shape
        )
        s[isoles] = 1.0
    P = sparse.diags((1.0 / s).astype(np.float32)) @ S
    return P.tocsr().astype(np.float32), len(isoles)


def pi_star(P: sparse.csr_matrix, alpha=ALPHA_PI_STAR, tol=TOL, max_iter=3000):
    """Itération de la puissance sur P_alpha = (1-alpha)P + alpha/n J, sans construire J."""
    n = P.shape[0]
    PT = P.T.tocsr()
    pi = np.full(n, 1.0 / n)
    for k in range(max_iter):
        nouveau = (1 - alpha) * (PT @ pi) + alpha / n
        nouveau /= nouveau.sum()
        if np.max(np.abs(nouveau - pi)) < tol:
            print(f"  pi_star : convergence en {k + 1} itérations")
            return nouveau
        pi = nouveau
    print("  [!] pi_star non convergé")
    return pi


# ------------------------------------------------------------------ #
# Métadonnées                                                          #
# ------------------------------------------------------------------ #

ARTICLES = r"(The|A|An|Les|Le|La|L'|Il|El|Die|Der|Das)"


def nettoyer_titre(brut: str):
    """'Matrix, The (1999)' -> ('The Matrix', 1999)."""
    m = re.match(r"^(.*?)\s*\((\d{4})\)\s*$", brut)
    titre, annee = (m.group(1), int(m.group(2))) if m else (brut, None)
    titre = re.split(r" \(", titre)[0]  # titre alternatif entre parenthèses
    m = re.match(rf"^(.*), {ARTICLES}$", titre)
    if m:
        titre = f"{m.group(2)} {m.group(1)}".replace("L' ", "L'")
    return titre, annee


def metadonnees_films(movie_ids, films, liens, nb_likes, tmdb_films):
    films = films.set_index("movieId")
    liens = liens.set_index("movieId")
    noeuds = []
    for idx, mid in enumerate(movie_ids):
        mid = int(mid)
        brut = films.at[mid, "title"] if mid in films.index else f"Film {mid}"
        genres = films.at[mid, "genres"].split("|") if mid in films.index else []
        genres = [g for g in genres if g in GENRES]
        titre, annee = nettoyer_titre(brut)
        tmdb_id = liens.at[mid, "tmdbId"] if mid in liens.index else None
        info = tmdb_films.get(str(mid))
        noeuds.append({
            "index": idx,
            "id": f"film:{mid}",
            "type": "film",
            "titre": (info or {}).get("titre_fr") or titre,
            "annee": annee,
            "genres": genres,
            "nb_likes": int(nb_likes[idx]),
            "tmdbId": int(tmdb_id) if tmdb_id is not None and not pd.isna(tmdb_id) else None,
            "affiche": URL_AFFICHE + info["poster_path"] if info and info.get("poster_path") else None,
            "resume": (info or {}).get("overview") or None,
            "plateformes": info["plateformes"] if info else [],
            "plateformes_verifiees": info is not None,
        })
    return noeuds


def metadonnees_series(series, decalage, tmdb_series):
    noeuds = []
    for i, s in enumerate(series):
        info = tmdb_series.get(str(s["tvmaze_id"]))
        poster = info.get("poster_path") if info else None
        noeuds.append({
            "index": decalage + i,
            "id": f"serie:{s['tvmaze_id']}",
            "type": "serie",
            "titre": (info or {}).get("titre_fr") or s["titre"],
            "annee": s["annee"],
            "annee_fin": s["fin"],
            "genres": s["genres"],
            "note": s["note"],
            "chaine": s["chaine"],
            # affiche TMDB si connue, sinon l'affiche TVmaze (vraie affiche elle aussi)
            "affiche": URL_AFFICHE + poster if poster else s["affiche"],
            "affiche_mini": None if poster else s["affiche_mini"],
            "resume": (info or {}).get("overview") or s["resume"],
            "plateformes": info["plateformes"] if info else [],
            "plateformes_verifiees": info is not None,
        })
    return noeuds


def metadonnees_sorties(sorties, decalage):
    noeuds = []
    for i, s in enumerate(sorties):
        noeuds.append({
            "index": decalage + i,
            "id": f"sortie:{s['id']}",
            "type": "sortie",
            "titre": s["titre"],
            "genres": s["genres"],
            "categorie": s["categorie"],
            "ville": s["ville"],
            "lieu": s["lieu"],
            "adresse": s.get("adresse"),
            "lat": s["lat"],
            "lon": s["lon"],
            "acces": s.get("acces"),
            "prix": s.get("prix"),
            "tarif": s.get("tarif"),
            "date_debut": s["date_debut"],     # YYYY-MM-DD (Europe/Paris)
            "date_fin": s["date_fin"],         # YYYY-MM-DD (Europe/Paris)
            "occurrences": s["occurrences"],   # [[début ISO, fin ISO], ...]
            "affiche": s.get("image"),
            "credit_image": s.get("credit_image"),
            "resume": s.get("description"),
            "url": s.get("url"),
            "plateformes": [],
        })
    return noeuds


# ------------------------------------------------------------------ #
# Assemblage (partagé entre le build complet et la reconstruction à chaud)
# ------------------------------------------------------------------ #

def charger_json(nom, defaut=None):
    chemin = DONNEES / nom
    return json.loads(chemin.read_text(encoding="utf-8")) if chemin.exists() else defaut


def charger_tmdb():
    tmdb = charger_json("tmdb.json", {})
    return tmdb if "films" in tmdb else {"films": {}, "series": {}}  # ancien format ignoré


def ecrire_atomique(chemin: Path, ecrire):
    """Écrit dans un fichier temporaire puis remplace : jamais de fichier à moitié écrit."""
    tmp = chemin.with_name(chemin.name + ".tmp")
    ecrire(tmp)
    os.replace(tmp, chemin)


def assembler(S_films, noeuds_films, series, sorties, tmdb_series, journal=print):
    """Films + séries + sorties -> P, pi_star, noeuds.json (écritures atomiques)."""
    genres_films = [nd["genres"] for nd in noeuds_films]
    nb_likes = np.array([nd["nb_likes"] for nd in noeuds_films])
    S = relier_externes(S_films, genres_films, nb_likes, series + sorties)
    journal(f"Externes : {len(series)} séries + {len(sorties)} sorties, {S.nnz:,} entrées au total")
    P, n_isoles = normaliser_lignes(S)
    journal(f"P : {P.shape[0]} nœuds, {n_isoles} nœud(s) isolé(s)")
    pi = pi_star(P)

    noeuds = list(noeuds_films)
    noeuds += metadonnees_series(series, len(noeuds_films), tmdb_series)
    noeuds += metadonnees_sorties(sorties, len(noeuds_films) + len(series))

    SORTIE.mkdir(parents=True, exist_ok=True)
    # format .npz explicite : np.save / save_npz ajouteraient une extension au fichier .tmp
    ecrire_atomique(SORTIE / "P.npz", lambda t: sparse.save_npz(open(t, "wb"), P))
    ecrire_atomique(SORTIE / "pi_star.npy", lambda t: np.save(open(t, "wb"), pi.astype(np.float64)))
    ecrire_atomique(SORTIE / "noeuds.json",
                    lambda t: t.write_text(json.dumps(noeuds, ensure_ascii=False), encoding="utf-8"))
    return len(noeuds)


def reconstruire_externes(journal=print):
    """
    Reconstruction à chaud après une mise à jour des sorties (scheduler.py) : réutilise les
    co-occurrences des films déjà calculées (S_films.npz), sans relire MovieLens.
    """
    S_films = sparse.load_npz(SORTIE / "S_films.npz").tocsr()
    noeuds = json.loads((SORTIE / "noeuds.json").read_text(encoding="utf-8"))
    noeuds_films = [nd for nd in noeuds if nd["type"] == "film"]
    assert len(noeuds_films) == S_films.shape[0], "S_films.npz et noeuds.json incohérents : relancer le build"
    return assembler(S_films, noeuds_films, charger_json("series.json")["series"],
                     charger_json("france.json")["sorties"], charger_tmdb()["series"], journal)


def main():
    parser = argparse.ArgumentParser(description="Pré-calcul du graphe de recommandation")
    parser.add_argument("--movielens", type=Path, default=DEFAUT_MOVIELENS)
    args = parser.parse_args()

    t0 = time.perf_counter()
    evals, films, liens = charger(args.movielens)
    print(f"Données : {len(evals)} évaluations aimées, "
          f"{evals['userId'].nunique()} utilisateurs, {evals['movieId'].nunique()} films")

    S, movie_ids = matrice_cooccurrence(evals)
    print(f"Co-occurrences : {S.nnz:,} entrées non nulles")
    nb_likes = evals.groupby("movieId").size().reindex(movie_ids).to_numpy()
    S = elaguer_hybride(S, nb_likes.astype(np.float64))
    print(f"Après élagage hybride : {S.nnz:,} entrées")

    tmdb = charger_tmdb()
    print(f"TMDB : {len(tmdb['films'])} films et {len(tmdb['series'])} séries vérifiés"
          + ("" if tmdb["films"] else " (lancer enrich_tmdb.py : sans lui, aucune plateforme n'est affichée)"))
    noeuds_films = metadonnees_films(movie_ids, films, liens, nb_likes, tmdb["films"])

    SORTIE.mkdir(parents=True, exist_ok=True)
    ecrire_atomique(SORTIE / "S_films.npz", lambda t: sparse.save_npz(open(t, "wb"), S))
    assembler(S, noeuds_films, charger_json("series.json")["series"],
              charger_json("france.json")["sorties"], tmdb["series"])
    print(f"Écrit dans {SORTIE} en {time.perf_counter() - t0:.1f} s")


if __name__ == "__main__":
    main()
