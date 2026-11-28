"""
Pré-calcul hors ligne du graphe de recommandation.

Entrées :
    - dataset MovieLens ml-latest-small (ratings.csv, movies.csv, links.csv)
    - backend/data/series.json      séries TVmaze (fetch_series.py)
    - backend/data/livres.json      livres GoodReads francisés (import_books.py)
    - backend/data/jeux.json        jeux vidéo Wikidata francisés (import_games.py)
    - backend/data/affiches.json    affiches et titres FR des films via Wikidata/Wikipédia (enrich_affiches.py)
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
                     (films, puis séries, livres, jeux, sorties)

Usage :
    python3 backend/build_graph.py --movielens /chemin/vers/ml-latest-small

Différences avec tipe_final.py (voir docs/architecture.md) :
    - S = AᵀA calculé en creux (au lieu de la double boucle Python en dense)
    - élagage hybride des voisins (sinon P a ~10⁷ entrées et une requête dépasse 20 ms) :
      par film, on garde les K_COMPTAGE plus fortes co-occurrences (les "classiques")
      + les K_COSINUS plus fortes similarités cosinus (les voisins spécifiques, souvent
      moins populaires). Un élagage par comptage seul ne garde que des hubs et rend
      les œuvres de niche inatteignables par la marche. Les poids restent S_ij.
    - séries, livres et sorties ajoutés comme nœuds, reliés aux films par similarité de genres
    - pi_star calculé sur P téléportée (alpha=0.15) : garantit la convergence
"""

import argparse
import json
import os
import re
import urllib.parse
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse

SEUIL = 3.5            # note minimale pour "aimé"
K_COMPTAGE = 20        # voisins gardés par co-occurrence brute (20 : latence < 20 ms)
K_COSINUS = 20         # voisins gardés par similarité cosinus
MIN_COOCCURRENCE = 2   # support minimal pour la sélection cosinus (évite le bruit)
K_FILMS_EXTERNE = 10   # films reliés à chaque nœud externe (10 : garde la requête < 20 ms avec ~14 600 nœuds)
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
    vf = vecteurs_genres(genres_films).T
    poids_films = np.log1p(nb_likes)[None, :]
    liens = []  # (x, f, score)
    for debut in range(0, n_x, 500):  # par lots : la matrice complète ferait ~240 Mo
        lot = externes[debut:debut + 500]
        # errstate : faux warnings du BLAS Accelerate (macOS) avec NumPy 2.0
        with np.errstate(all="ignore"):
            score = (vecteurs_genres([x["genres"] for x in lot]) @ vf) * poids_films
        assert np.isfinite(score).all()
        top = np.argpartition(-score, K_FILMS_EXTERNE, axis=1)[:, :K_FILMS_EXTERNE]
        for j in range(len(lot)):
            liens += [(debut + j, int(f), float(score[j, f])) for f in top[j] if score[j, f] > 0]

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


LOGO = re.compile(r"(^|[_\W])(logo|wordmark|title|titre|icon|banner)([_\W]|$)", re.I)


def image_valide(url):
    """Écarte les images qui ne sont pas des affiches ou jaquettes (logos, bannières…), d'après le nom du fichier."""
    if not url:
        return None
    nom = urllib.parse.unquote(url.rsplit("/", 1)[-1]).rsplit(".", 1)[0]
    return None if LOGO.search(nom) else url


def appliquer_affiches(noeud: dict, info_tmdb: dict, info_wiki: dict) -> dict:
    """Affiche et titre FR d'un film : TMDB d'abord, sinon Wikipédia/Wikidata (enrich_affiches.py)."""
    info_tmdb, info_wiki = info_tmdb or {}, info_wiki or {}
    if info_tmdb.get("poster_path"):
        noeud["affiche"], noeud["source_affiche"] = URL_AFFICHE + info_tmdb["poster_path"], "TMDB"
    elif image_valide(info_wiki.get("affiche")):
        noeud["affiche"], noeud["source_affiche"] = info_wiki["affiche"], "Wikipédia"
    else:
        noeud["affiche"], noeud["source_affiche"] = None, None
    noeud["titre"] = info_tmdb.get("titre_fr") or info_wiki.get("titre_fr") or noeud.get("titre_original") or noeud["titre"]
    return noeud


def metadonnees_films(movie_ids, films, liens, nb_likes, tmdb_films, affiches_films=None):
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
        noeud = {
            "index": idx,
            "id": f"film:{mid}",
            "type": "film",
            "titre": titre,
            "titre_original": titre,
            "annee": annee,
            "genres": genres,
            "nb_likes": int(nb_likes[idx]),
            "tmdbId": int(tmdb_id) if tmdb_id is not None and not pd.isna(tmdb_id) else None,
            "resume": (info or {}).get("overview") or None,
            "plateformes": info["plateformes"] if info else [],
            "plateformes_verifiees": info is not None,
        }
        noeuds.append(appliquer_affiches(noeud, info, (affiches_films or {}).get(str(mid))))
    return noeuds


def resumes_fr():
    """Introductions Wikipédia FR (enrich_resumes.py) : jamais de texte anglais dans l'interface."""
    return charger_json("resumes.json", {"films": {}, "series": {}, "livres": {}})


def metadonnees_series(series, decalage, tmdb_series):
    resumes = resumes_fr()["series"]
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
            # TMDB (fr-FR) sinon Wikipédia FR ; le résumé TVmaze est en anglais : jamais affiché
            "resume": (info or {}).get("overview") or resumes.get(str(s["tvmaze_id"])),
            "plateformes": info["plateformes"] if info else [],
            "plateformes_verifiees": info is not None,
        })
    return noeuds


def metadonnees_livres(livres, decalage):
    resumes = resumes_fr()["livres"]
    return [{
        "index": decalage + i,
        "id": f"livre:{l['id']}",
        "type": "livre",
        "titre": l["titre"],
        "titre_original": l["titre_original"],
        "auteur": l["auteur"],
        "annee": l["annee"],
        "pages": l["pages"],
        "note": l["note"],
        "genres": l["genres"],
        "themes": l.get("themes", []),  # roman, polar, sff, essais, bd, bio (filtre de l'onglet Lecture)
        "affiche": l["couverture"],
        "resume": l["resume"] or resumes.get(l["id"]),  # uniquement en français (Google Books ou Wikipédia FR)
        "francais": l["francais"],      # édition française trouvée
        "plateformes": [],
    } for i, l in enumerate(livres)]


def metadonnees_jeux(jeux, decalage):
    return [{
        "index": decalage + i,
        "id": f"jeu:{j['id']}",
        "type": "jeu",
        "titre": j["titre"],
        "titre_original": j["titre_original"],
        "annee": j["annee"],
        "genres": j["genres"],          # genres de l'application (graphe, affinité)
        "genres_fr": j["genres_fr"],    # libellés affichés (français)
        "consoles": j["consoles"],      # pc, mac, playstation, xbox, switch, mobile
        "modes": j["modes"],            # solo, coop, multi
        "studio": j["studio"],
        "editeur": j["editeur"],
        "affiche": image_valide(j["jaquette"]),
        "resume": j["resume"],          # extrait de Wikipédia en français, sinon rien
        "plateformes": [],
    } for i, j in enumerate(jeux)]


def metadonnees_sorties(sorties, decalage):
    noeuds = []
    for i, s in enumerate(sorties):
        noeuds.append({
            "index": decalage + i,
            "id": f"sortie:{s['id']}",
            "type": "sortie",
            "titre": s["titre"],
            "genres": s["genres"],
            "ambiances": s.get("ambiances", []),   # calme, insolite, drole, competitif, artistique
            "categorie": s["categorie"],
            "ville": s["ville"],
            "lieu": s["lieu"],
            "adresse": s.get("adresse"),
            "lat": s["lat"],
            "lon": s["lon"],
            "acces": s.get("acces"),
            "prix": s.get("prix"),
            # prix_num : tarif publié, sinon déduit de la description (« gratuit », « entrée libre », « 5 € »)
            "prix_num": s.get("prix") if s.get("prix") is not None else prix_depuis_texte(
                s.get("conditions"), s.get("description_longue"), s.get("description")),
            "tarif": s.get("tarif"),
            "date_debut": s["date_debut"],     # YYYY-MM-DD (Europe/Paris)
            "date_fin": s["date_fin"],         # YYYY-MM-DD (Europe/Paris)
            "occurrences": s["occurrences"],   # [[début ISO, fin ISO], ...]
            "affiche": s.get("image"),
            "credit_image": s.get("credit_image"),
            # description complète (OpenAgenda, texte long) pour la fiche ; à défaut la description courte
            "resume": s.get("description_longue") or s.get("description"),
            "url": s.get("url"),
            "source": s.get("source", "openagenda"),
            "propose_par": s.get("propose_par"),
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


# ------------------------------------------------------------------ #
# Prix et temps disponible                                             #
# ------------------------------------------------------------------ #

MOTS_GRATUIT = re.compile(r"\bgratuit|entr[ée]e libre|acc[eè]s libre|\b0\s?(€|euros?)\b|sans r[ée]servation et gratuit", re.I)
MONTANT = re.compile(r"(\d+(?:[.,]\d{1,2})?)\s*(?:€|euros?)", re.I)


def prix_depuis_texte(*textes):
    """prix_num (euros) : 0.0 si gratuit / entrée libre, sinon plus petit montant écrit, sinon None."""
    for t in textes:
        if not t:
            continue
        montants = [float(x.replace(",", ".")) for x in MONTANT.findall(t)]
        if MOTS_GRATUIT.search(t) and not [m for m in montants if m > 0]:
            return 0.0
        if montants:
            return min(montants)
    return None


GENRES_JEU_EXPRESS = {"Détente", "Réflexion", "Jeu d'ambiance", "Arcade", "Rythme", "Cartes", "Sport", "Course",
                      "Plateforme", "Jeu de société", "Combat", "Tir"}
GENRES_JEU_LONG = {"RPG", "Action-RPG", "RPG tactique", "MMORPG", "Monde ouvert", "Stratégie", "Stratégie au tour par tour",
                   "Stratégie en temps réel", "Simulation", "Gestion", "Survie", "Simulation de vie", "Aventure", "Metroidvania"}


def duree_categorie(nd: dict) -> str:
    """Temps disponible : « express » (< 45 min), « soiree » (1 h 30 – 2 h 30), « long » (demi-journée / week-end)."""
    t, genres = nd["type"], set(nd.get("genres", []))
    if t == "film":
        return "soiree"
    if t == "serie":  # sitcoms et animation : épisodes de ~22 min
        return "express" if genres & {"Comedy", "Animation"} and "Drama" not in genres else "soiree"
    if t == "livre":
        if "bd" in nd.get("themes", []) or (nd.get("pages") or 999) <= 200:
            return "express"   # BD, nouvelles, livres courts
        return "long"
    if t == "jeu":
        g = set(nd.get("genres_fr", []))
        if g & GENRES_JEU_LONG:
            return "long"
        return "express" if g & GENRES_JEU_EXPRESS else "soiree"
    # sorties
    titre = (nd.get("titre") or "").lower()
    if nd.get("categorie") == "nature" or re.search(r"festival|randonn|journ[ée]e enti[èe]re|week-end", titre):
        return "long"
    if nd.get("categorie") == "lecture" or re.search(r"rencontre|d[ée]dicace|lecture|ap[ée]ro|visite flash", titre):
        return "express"
    return "soiree"   # concerts, spectacles, ciné, expositions


EMOJIS = re.compile("[\U0001F000-\U0001FAFF\U0001F1E6-\U0001F1FF\u2600-\u27BF\u2B00-\u2BFF\u2300-\u23FF\uFE0F\u200D\u20E3]")
CHAMPS_TEXTE = ("titre", "resume", "lieu", "adresse", "acces", "tarif", "studio", "editeur", "auteur")


def sans_emoji(noeud: dict) -> dict:
    """Règle « zéro émoji » garantie à la source : les textes externes (OpenAgenda, Wikipédia…) en contiennent parfois."""
    for champ in CHAMPS_TEXTE:
        v = noeud.get(champ)
        if isinstance(v, str) and EMOJIS.search(v):
            v = re.sub(r"[ \t]{2,}", " ", EMOJIS.sub("", v))
            noeud[champ] = re.sub(r"^\s+|\s+$", "", re.sub(r" *\n *", "\n", v)) or None
    return noeud


def assembler(S_films, noeuds_films, series, livres, jeux, sorties, tmdb_series, journal=print):
    """Films + séries + livres + jeux + sorties -> P, pi_star, noeuds.json (écritures atomiques)."""
    genres_films = [nd["genres"] for nd in noeuds_films]
    nb_likes = np.array([nd["nb_likes"] for nd in noeuds_films])
    S = relier_externes(S_films, genres_films, nb_likes, series + livres + jeux + sorties)
    journal(f"Externes : {len(series)} séries + {len(livres)} livres + {len(jeux)} jeux + {len(sorties)} sorties, "
            f"{S.nnz:,} entrées au total")
    P, n_isoles = normaliser_lignes(S)
    journal(f"P : {P.shape[0]} nœuds, {n_isoles} nœud(s) isolé(s)")
    pi = pi_star(P)

    noeuds = list(noeuds_films)
    noeuds += metadonnees_series(series, len(noeuds_films), tmdb_series)
    noeuds += metadonnees_livres(livres, len(noeuds))
    noeuds += metadonnees_jeux(jeux, len(noeuds))
    noeuds += metadonnees_sorties(sorties, len(noeuds))
    noeuds = [sans_emoji(nd) for nd in noeuds]
    for nd in noeuds:
        nd["duree_categorie"] = duree_categorie(nd)
        if nd["type"] == "sortie" and nd.get("prix") is None and nd.get("prix_num") is not None:
            nd["tarif"] = "Gratuit" if nd["prix_num"] == 0 else f"Dès {nd['prix_num']:g} €".replace(".", ",")

    SORTIE.mkdir(parents=True, exist_ok=True)
    # format .npz explicite : np.save / save_npz ajouteraient une extension au fichier .tmp
    ecrire_atomique(SORTIE / "P.npz", lambda t: sparse.save_npz(open(t, "wb"), P))
    ecrire_atomique(SORTIE / "pi_star.npy", lambda t: np.save(open(t, "wb"), pi.astype(np.float64)))
    ecrire_atomique(SORTIE / "noeuds.json",
                    lambda t: t.write_text(json.dumps(noeuds, ensure_ascii=False), encoding="utf-8"))
    return len(noeuds)


def externes_locaux(sorties_supplementaires=()):
    """Livres, jeux et sorties (fichiers locaux + sorties publiées par les utilisateurs)."""
    livres = charger_json("livres.json", {"livres": []})["livres"]
    jeux = charger_json("jeux.json", {"jeux": []})["jeux"]
    sorties = charger_json("france.json")["sorties"] + list(sorties_supplementaires)
    return livres, jeux, sorties


def reconstruire_externes(journal=print, sorties_supplementaires=()):
    """
    Reconstruction à chaud (scheduler.py, publication d'une sortie) : réutilise les co-occurrences
    des films déjà calculées (S_films.npz), sans relire MovieLens. Réapplique aussi les affiches
    (tmdb.json, affiches.json) : un enrichissement d'affiches ne demande pas de build complet.
    """
    S_films = sparse.load_npz(SORTIE / "S_films.npz").tocsr()
    noeuds = json.loads((SORTIE / "noeuds.json").read_text(encoding="utf-8"))
    noeuds_films = [nd for nd in noeuds if nd["type"] == "film"]
    assert len(noeuds_films) == S_films.shape[0], "S_films.npz et noeuds.json incohérents : relancer le build"
    tmdb, wiki = charger_tmdb(), charger_json("affiches.json", {"films": {}})["films"]
    resumes = resumes_fr()["films"]
    for nd in noeuds_films:
        mid = nd["id"].split(":")[1]
        appliquer_affiches(nd, tmdb["films"].get(mid), wiki.get(mid))
        nd["resume"] = (tmdb["films"].get(mid) or {}).get("overview") or resumes.get(mid)
    livres, jeux, sorties = externes_locaux(sorties_supplementaires)
    return assembler(S_films, noeuds_films, charger_json("series.json")["series"], livres, jeux, sorties,
                     tmdb["series"], journal)


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
    affiches = charger_json("affiches.json", {"films": {}})["films"]
    noeuds_films = metadonnees_films(movie_ids, films, liens, nb_likes, tmdb["films"], affiches)
    resumes = resumes_fr()["films"]
    for nd in noeuds_films:
        nd["resume"] = nd["resume"] or resumes.get(nd["id"].split(":")[1])
    print(f"Affiches de films : {sum(1 for n in noeuds_films if n['affiche'])}/{len(noeuds_films)}")

    SORTIE.mkdir(parents=True, exist_ok=True)
    ecrire_atomique(SORTIE / "S_films.npz", lambda t: sparse.save_npz(open(t, "wb"), S))
    try:  # sorties publiées par les utilisateurs (base locale), si elle existe
        try:
            from . import database
        except ImportError:
            import database
        communaute = database.sorties_communaute() if database.CHEMIN.exists() else []
    except Exception:
        communaute = []
    livres, jeux, sorties = externes_locaux(communaute)
    assembler(S, noeuds_films, charger_json("series.json")["series"], livres, jeux, sorties, tmdb["series"])
    print(f"Écrit dans {SORTIE} en {time.perf_counter() - t0:.1f} s")


if __name__ == "__main__":
    main()
