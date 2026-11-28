"""
Moteur de recommandation : PageRank personnalisé + restart biaisé anti-hubs.

Chargé une seule fois au démarrage de l'API (artefacts produits par build_graph.py).
Une requête = 2 marches aléatoires sur une matrice creuse (~15 ms au total).

Cold start : l'utilisateur n'a pas d'historique. Le point de départ v_u est construit à
partir de ses genres favoris (films les plus aimés de chaque genre) et, au fil de l'usage,
des œuvres marquées « Déjà vu » (voir vecteur_depart).

Deux marches, une par extrémité du curseur :
    v_u  = distribution de départ (genres + œuvres déjà vues)
    b    ∝ pi_star^(-beta), restreint aux films du voisinage à 2 pas du départ
    r    = (1 - lambda) v_u + lambda b                    (distribution de restart)
    pi   <- (1 - alpha) pi P + alpha r                    (jusqu'à (1-alpha)^n <= TOL_MARCHE)

    CONFORT    : alpha=0.10, beta=0, lambda=0  -> PageRank personnalisé classique
    DECOUVERTE : alpha=0.50, beta=2, lambda=1  -> restart biaisé vers la niche du voisinage

Deux notions séparées : la NICHE (popularité, via pi_star) et le DÉPAYSEMENT (genres).

    confort    : pi_confort × aff                         aff = affinité avec les genres cochés
    découverte : pi_decouverte / pi_star × q × (1 - MALUS_MAX · s · m)
        pi_decouverte / pi_star : lift, ce qui est sur-représenté autour de l'utilisateur (niche)
        m  : part des genres de l'œuvre qui sont des genres COCHÉS par l'utilisateur
        s  : position du curseur ; à 10/10 une œuvre 100 % dans les genres cochés perd 90 %
        q  : plancher de qualité (films aimés par au moins MIN_LIKES_DECOUVERTE personnes)
    La cohérence reste assurée par la marche : seules les œuvres atteignables depuis les
    goûts de l'utilisateur ont un pi_decouverte non négligeable.

Étiquettes des résultats découverte : « pepite » (niche dans ses genres, m >= 0.5) ou
« hors-piste » (majoritairement hors de ses genres).

Affinité de genres : aff_i = EPS_AFFINITE + cos(genres_i, profil), profil = genres cochés +
genres des « Déjà vu ». Sans ce terme, partir de 25 films par genre suffit à peine : la
marche dérive vers les mêmes classiques (Pulp Fiction, Shawshank) quels que soient les genres.

Le curseur s ∈ [0, 1] fixe un quota : sur k résultats, round(s·k) viennent du classement
découverte, le reste du classement confort, entrelacés. Chaque résultat est étiqueté
("confort" / "decouverte") pour l'affichage.

Pourquoi pas une interpolation continue de alpha/beta avec s ? Mesuré sur MovieLens :
le top-10 reste figé sur les hubs jusqu'à s≈0.45 puis bascule d'un coup (effet
interrupteur) ; une fusion de rangs pondérée a le même défaut. Le quota est linéaire.

Séries et sorties sont des nœuds du même graphe, reliés aux films par genres : la même
marche les classe à partir des goûts de l'utilisateur. Pour elles, le classement confort
est aussi divisé par pi_star (lift_confort=True) : sinon celles reliées aux films les plus
populaires sortent en tête pour tout le monde.
"""

import json
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
from scipy import sparse

DOSSIER_DONNEES = Path(__file__).resolve().parent / "data" / "processed"
TOL_MARCHE = 0.05  # erreur relative visée : (1-alpha)^n <= 5 %, suffisant pour classer
FILMS_PAR_GENRE = 25   # films de référence par genre favori dans v_u
PART_DEJA_VUS = 0.6    # poids des « Déjà vu » dans v_u quand il y a aussi des genres
EPS_AFFINITE = 0.15    # plancher de l'affinité : un genre éloigné reste recommandable
MALUS_MAX = 0.9        # découverte à 10/10 : -90 % sur les œuvres des genres cochés
BONUS_AMBIANCE = 4.0      # sortie portant une ambiance choisie : score x (1 + BONUS)
MIN_LIKES_DECOUVERTE = 5  # en dessous, un film est trop confidentiel pour être fiable
BUDGETS = ("tous", "gratuit", "moins10", "moins25")
PLAFOND_BUDGET = {"gratuit": 0.0, "moins10": 10.0, "moins25": 25.0}
ARTE = 234
SEUIL_AFFICHES_STRICT = 0.9  # au-delà de 90 % d'œuvres avec affiche, les autres sont exclues…
MIN_AFFICHES_STRICT = 1500   # … ou dès que 1 500 œuvres du type ont une affiche (catalogue assez riche)
BONUS_SANS_AFFICHE = 0.3     # en dessous : une œuvre sans affiche voit son score multiplié par 0.3
PARIS = ZoneInfo("Europe/Paris")
HORIZONS = ("maintenant", "aujourdhui", "weekend", "semaine", "mois", "court")  # "court" : anciens profils
DUREE_MAINTENANT = timedelta(hours=3)  # « Maintenant » : en cours ou qui commence dans les 3 h
Fenetre = Tuple[float, float]            # (début, fin) en timestamps


def fenetres(horizon: str, maintenant: Optional[datetime] = None) -> List[Fenetre]:
    """
    Intervalles de temps couverts par un horizon (fuseau Europe/Paris) :
      maintenant : maintenant -> +3 h (en cours ou sur le point de commencer)
      aujourdhui : maintenant -> minuit
      weekend    : samedi 0h -> lundi 0h à venir (le week-end en cours si on est samedi ou dimanche)
      court      : aujourdhui + weekend (anciens profils)
      semaine    : maintenant -> +7 jours
      mois       : maintenant -> +30 jours
    """
    now = (maintenant or datetime.now(PARIS)).astimezone(PARIS)
    if horizon == "maintenant":
        return [(now.timestamp(), (now + DUREE_MAINTENANT).timestamp())]
    if horizon == "semaine":
        return [(now.timestamp(), (now + timedelta(days=7)).timestamp())]
    if horizon == "mois":
        return [(now.timestamp(), (now + timedelta(days=30)).timestamp())]
    minuit = now.replace(hour=0, minute=0, second=0, microsecond=0)
    fin_du_jour = minuit + timedelta(days=1)
    samedi = minuit + timedelta(days=(5 - now.weekday()) % 7)  # aujourd'hui si on est samedi
    if now.weekday() == 6:                                      # dimanche : week-end en cours
        samedi = minuit - timedelta(days=1)
    fin_weekend = samedi + timedelta(days=2)
    if horizon == "aujourdhui":
        return [(now.timestamp(), fin_du_jour.timestamp())]
    if horizon == "weekend":
        return [(max(now, samedi).timestamp(), fin_weekend.timestamp())]
    return [(now.timestamp(), fin_du_jour.timestamp()), (max(now, samedi).timestamp(), fin_weekend.timestamp())]


def haversine_km(lat0: float, lon0: float, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """Distance de grand cercle (km) entre un point et des tableaux de points."""
    p = np.pi / 180
    a = (np.sin((lat - lat0) * p / 2) ** 2
         + np.cos(lat0 * p) * np.cos(lat * p) * np.sin((lon - lon0) * p / 2) ** 2)
    return 12742.0 * np.arcsin(np.sqrt(a))


@dataclass(frozen=True)
class Parametres:
    alpha: float       # poids du restart
    beta: float        # pénalisation des hubs dans le restart
    part_niche: float  # lambda : part du restart envoyée vers les œuvres de niche


CONFORT = Parametres(alpha=0.10, beta=0.0, part_niche=0.0)
DECOUVERTE = Parametres(alpha=0.50, beta=2.0, part_niche=1.0)


@dataclass
class Recommandation:
    index: int
    score: float
    origine: str  # "confort" | "decouverte"
    noeud: dict
    etiquette: Optional[str] = None  # découverte : "pepite" | "hors-piste"


def cle_titre(noeud: dict) -> str:
    """« Apéro des randonneurs — Brest » et « … — Vannes » : un seul résultat."""
    return noeud["titre"].split(" — ")[0].split(" - ")[0].strip().lower()


def meilleurs(scores: np.ndarray, k: int) -> np.ndarray:
    """Indices des k plus grands scores finis, par ordre décroissant."""
    k = min(k, len(scores))
    top = np.argpartition(-scores, k - 1)[:k]
    top = top[np.argsort(-scores[top])]
    return top[np.isfinite(scores[top])]


class Moteur:
    def __init__(self, dossier: Path = DOSSIER_DONNEES):
        P = sparse.load_npz(dossier / "P.npz").tocsr()
        # pi @ P  ==  P.T @ pi : on stocke P.T en CSR pour un produit rapide
        self.PT = P.T.tocsr()
        self.n = P.shape[0]
        self.pi_star = np.load(dossier / "pi_star.npy")
        with open(dossier / "noeuds.json", encoding="utf-8") as fh:
            self.noeuds: List[dict] = json.load(fh)
        self.index_par_id: Dict[str, int] = {nd["id"]: nd["index"] for nd in self.noeuds}

        # masques pré-calculés : aucun parcours Python des nœuds par requête
        self.types = np.array([nd["type"] for nd in self.noeuds])
        self.masque_type = {t: self.types == t for t in set(self.types)}
        self.masque_plateforme: Dict[int, np.ndarray] = {}
        self.masque_categorie: Dict[str, np.ndarray] = {}
        self.masque_ambiance: Dict[str, np.ndarray] = {}
        for nd in self.noeuds:
            for a in nd.get("ambiances", []):
                self.masque_ambiance.setdefault(a, np.zeros(self.n, dtype=bool))[nd["index"]] = True
            for p in nd.get("plateformes", []):
                self.masque_plateforme.setdefault(p, np.zeros(self.n, dtype=bool))[nd["index"]] = True
            if nd.get("categorie"):
                self.masque_categorie.setdefault(nd["categorie"], np.zeros(self.n, dtype=bool))[nd["index"]] = True
        # plateformes : seules les données confirmées par TMDB (FR.flatrate) comptent
        self.verifie = np.array([bool(nd.get("plateformes_verifiees")) for nd in self.noeuds])
        self.plateformes_verifiees = bool(self.verifie.any())
        # Affiches (films, séries, livres, jeux). Par type : si au moins 90 % ont une vraie affiche, ou
        # au moins 1 500 œuvres, les autres sont exclues (100 % d'affiches à l'écran) ; sinon
        # (enrichissement en cours) elles sont fortement défavorisées, pour ne pas vider le catalogue.
        self.a_affiche = np.array([bool(nd.get("affiche")) for nd in self.noeuds])
        vide = np.zeros(self.n, dtype=bool)
        self.couverture_affiches = {t: float(self.a_affiche[m].mean()) for t, m in self.masque_type.items() if t != "sortie"}
        self.sans_affiche_exclu = vide.copy()
        self.bonus_affiche = np.ones(self.n)
        for t, part in self.couverture_affiches.items():
            m = self.masque_type[t] & ~self.a_affiche
            if part >= SEUIL_AFFICHES_STRICT or int((self.masque_type[t] & self.a_affiche).sum()) >= MIN_AFFICHES_STRICT:
                self.sans_affiche_exclu |= m
            else:
                self.bonus_affiche[m] = BONUS_SANS_AFFICHE
        self.ecran = self.masque_type.get("film", vide) | self.masque_type.get("serie", vide)
        # Synopsis en français obligatoire pour les films et séries : même règle que les affiches
        # (stricte dès 90 % d'œuvres décrites ou 1 500 œuvres décrites).
        self.a_resume = np.array([bool(nd.get("resume")) for nd in self.noeuds])
        for t in ("film", "serie"):
            m = self.masque_type.get(t, vide)
            decrits = int((m & self.a_resume).sum())
            if m.any() and (decrits / m.sum() >= SEUIL_AFFICHES_STRICT or decrits >= MIN_AFFICHES_STRICT):
                self.sans_affiche_exclu |= m & ~self.a_resume
        # jeux vidéo : consoles possédées et modes de jeu
        self.masque_console: Dict[str, np.ndarray] = {}
        self.jeu_multi = vide.copy()   # co-op ou multijoueur (badge « Co-op / Multi »)
        self.jeu_coop = vide.copy()
        self.jeu_multijoueur = vide.copy()
        self.jeu_solo = vide.copy()
        for nd in self.noeuds:
            if nd["type"] != "jeu":
                continue
            for c in nd.get("consoles", []):
                self.masque_console.setdefault(c, vide.copy())[nd["index"]] = True
            modes = set(nd.get("modes", []))
            self.jeu_multi[nd["index"]] = bool(modes & {"coop", "multi"})
            self.jeu_coop[nd["index"]] = "coop" in modes
            self.jeu_multijoueur[nd["index"]] = "multi" in modes
            self.jeu_solo[nd["index"]] = "solo" in modes
        # thèmes littéraires des livres (onglet Lecture), en matrice binaire pour le calcul de m_theme
        self.themes = sorted({t for nd in self.noeuds for t in nd.get("themes", [])})
        pos_t = {t: j for j, t in enumerate(self.themes)}
        lignes = [nd["index"] for nd in self.noeuds for t in nd.get("themes", [])]
        colonnes = [pos_t[t] for nd in self.noeuds for t in nd.get("themes", [])]
        self.T = sparse.csr_matrix((np.ones(len(lignes)), (lignes, colonnes)), shape=(self.n, max(1, len(self.themes))))
        self.nb_themes = np.maximum(1.0, np.asarray(self.T.sum(axis=1)).ravel())

        # coordonnées des sorties (NaN ailleurs), pour le filtre de Haversine
        self.lat = np.array([nd.get("lat") if nd.get("lat") is not None else np.nan for nd in self.noeuds])
        self.lon = np.array([nd.get("lon") if nd.get("lon") is not None else np.nan for nd in self.noeuds])

        # occurrences des sorties, à plat : (nœud, début, fin) en timestamps
        lignes = [(nd["index"], datetime.fromisoformat(d).timestamp(), datetime.fromisoformat(f).timestamp())
                  for nd in self.noeuds for d, f in nd.get("occurrences", [])]
        occ = np.array(lignes, dtype=float).reshape(-1, 3)
        self.occ_noeud = occ[:, 0].astype(np.int64)
        self.occ_debut = occ[:, 1]
        self.occ_fin = occ[:, 2]

        # films de référence par genre (les plus aimés), pour le cold start
        films = sorted((nd for nd in self.noeuds if nd["type"] == "film"), key=lambda nd: -nd["nb_likes"])
        self.references_genre: Dict[str, np.ndarray] = {}
        for nd in films:
            for g in nd["genres"]:
                ref = self.references_genre.setdefault(g, [])
                if len(ref) < FILMS_PAR_GENRE:
                    ref.append(nd["index"])
        self.references_genre = {g: np.array(v) for g, v in self.references_genre.items()}
        self.films_populaires = np.array([nd["index"] for nd in films[:50]])

        # matrice genres (n x G), lignes normalisées, pour l'affinité utilisateur
        # (les ambiances des sorties, ex. "calme", y sont des colonnes comme les autres)
        etiquettes = [nd.get("genres", []) + nd.get("ambiances", []) for nd in self.noeuds]
        self.genres = sorted({g for e in etiquettes for g in e})
        pos = {g: j for j, g in enumerate(self.genres)}
        lignes = [nd["index"] for nd, e in zip(self.noeuds, etiquettes) for g in e]
        colonnes = [pos[g] for e in etiquettes for g in e]
        G = sparse.csr_matrix((np.ones(len(lignes)), (lignes, colonnes)), shape=(self.n, len(self.genres)))
        normes = np.sqrt(np.asarray(G.multiply(G).sum(axis=1)).ravel())
        normes[normes == 0] = 1.0
        self.G = sparse.diags(1.0 / normes) @ G
        self.G_binaire = G.tocsr()
        self.nb_genres = np.maximum(1.0, np.asarray(G.sum(axis=1)).ravel())

        # qualité minimale en découverte (films très confidentiels exclus) ; prix des sorties
        likes = np.array([nd.get("nb_likes") or 0 for nd in self.noeuds])
        self.qualite = np.where(self.types == "film", (likes >= MIN_LIKES_DECOUVERTE).astype(float), 1.0)
        self.prix = np.array([nd.get("prix") if nd.get("prix") is not None else np.nan for nd in self.noeuds])

    # -------------------------------------------------------------- #

    def indices(self, ids: Sequence[str]) -> List[int]:
        """Identifiants publics ("film:1") -> indices du graphe (inconnus ignorés)."""
        return [self.index_par_id[i] for i in ids if i in self.index_par_id]

    def vecteur_depart(self, deja_vus: Sequence[int], genres: Sequence[str]) -> np.ndarray:
        """
        v_u : PART_DEJA_VUS sur les œuvres déjà vues, le reste réparti entre les genres
        favoris (uniforme sur les FILMS_PAR_GENRE films les plus aimés de chaque genre).
        Sans aucun signal : les 50 films les plus aimés.
        """
        v = np.zeros(self.n)
        genres = [g for g in genres if g in self.references_genre]
        part_vus = (PART_DEJA_VUS if genres else 1.0) if deja_vus else 0.0
        if deja_vus:
            v[list(deja_vus)] += part_vus / len(deja_vus)
        for g in genres:
            ref = self.references_genre[g]
            v[ref] += (1 - part_vus) / len(genres) / len(ref)
        if v.sum() == 0:
            v[self.films_populaires] = 1.0 / len(self.films_populaires)
        return v / v.sum()

    def affinite(self, vus: Sequence[int], genres: Sequence[str]) -> np.ndarray:
        """EPS + cos(genres de chaque nœud, profil de genres de l'utilisateur)."""
        profil = np.zeros(len(self.genres))
        for g in genres:
            if g in self.genres:
                profil[self.genres.index(g)] += 1.0
        if len(vus):
            profil += 0.5 * np.asarray(self.G[list(vus)].sum(axis=0)).ravel()
        if not profil.any():
            return np.ones(self.n)
        return EPS_AFFINITE + self.G @ (profil / np.linalg.norm(profil))

    def part_genres_choisis(self, vus: Sequence[int], genres: Sequence[str]) -> np.ndarray:
        """m_i : part des genres de chaque œuvre qui font partie des genres cochés (à défaut :
        des genres des « Déjà vu »). 0 partout si l'utilisateur n'a exprimé aucun genre."""
        choisis = {g for g in genres if g in self.genres and g not in self.masque_ambiance}  # ambiance = humeur, pas bulle
        if not choisis and len(vus):
            colonnes = np.asarray(self.G_binaire[list(vus)].sum(axis=0)).ravel()
            choisis = {self.genres[j] for j in np.where(colonnes > 0)[0]}
        u = np.array([1.0 if g in choisis else 0.0 for g in self.genres])
        return (self.G_binaire @ u) / self.nb_genres

    def part_themes_choisis(self, themes: Sequence[str]) -> Optional[np.ndarray]:
        """Part des thèmes de chaque livre qui font partie des thèmes choisis (None si aucun thème)."""
        choisis = [t for t in themes if t in self.themes]
        if not choisis:
            return None
        u = np.array([1.0 if t in choisis else 0.0 for t in self.themes])
        return (self.T @ u) / self.nb_themes

    def autorises(self, types: Iterable[str], plateformes: Iterable[int] = (),
                  centre: Optional[Tuple[float, float]] = None, rayon_km: float = 15.0,
                  categories: Iterable[str] = (), horizon: str = "mois", budget: str = "tous",
                  consoles: Iterable[str] = (), mode_jeu: str = "tous") -> np.ndarray:
        """
        Masque des nœuds recommandables (listes vides = pas de filtre).
          - plateformes (films, séries) : présence CONFIRMÉE par TMDB sur l'une d'elles ;
            ignoré si le catalogue n'a aucune donnée vérifiée (pas de clé TMDB)
          - centre + rayon (sorties) : distance de Haversine <= rayon
          - horizon (sorties) : au moins une occurrence dans la fenêtre ; jamais rien de passé
          - consoles (jeux) : jouable sur au moins une console de l'utilisateur ;
            mode_jeu (jeux) : "solo" | "coop" | "multi" | "tous"
          - budget : sorties -> tarif connu <= plafond (prix inconnu exclu) ;
                     films/séries -> seulement ce qui est inclus SANS SURCOÛT : confirmé par TMDB
                     sur un abonnement de l'utilisateur ou sur Arte. Sans données TMDB, rien
                     ne peut être garanti : aucun film/série ne passe.
        """
        vide = np.zeros(self.n, dtype=bool)
        sortie = self.masque_type.get("sortie", vide)
        livre = self.masque_type.get("livre", vide)
        jeu = self.masque_type.get("jeu", vide)
        masque = vide.copy()
        for t in types:
            masque |= self.masque_type.get(t, vide)
        masque &= ~self.sans_affiche_exclu

        plateformes = list(plateformes)
        if plateformes and self.plateformes_verifiees:
            dispo = vide.copy()
            for p in plateformes:
                dispo |= self.masque_plateforme.get(p, vide)
            masque &= (dispo & self.verifie) | ~self.ecran

        if centre is not None:
            with np.errstate(invalid="ignore"):
                proches = haversine_km(centre[0], centre[1], self.lat, self.lon) <= rayon_km  # NaN -> False
            masque &= proches | ~sortie

        consoles = [c for c in consoles if c in self.masque_console]
        if consoles:
            jouable = vide.copy()
            for c in consoles:
                jouable |= self.masque_console[c]
            masque &= jouable | ~jeu
        if mode_jeu == "multi":
            masque &= self.jeu_multijoueur | ~jeu
        elif mode_jeu == "coop":
            masque &= self.jeu_coop | ~jeu
        elif mode_jeu == "solo":
            masque &= self.jeu_solo | ~jeu

        categories = [c for c in categories if c in self.masque_categorie]  # ignore « livres », etc.
        if categories:
            dans_cat = vide.copy()
            for c in categories:
                dans_cat |= self.masque_categorie.get(c, vide)
            masque &= dans_cat | ~sortie

        dans_fenetre = vide.copy()
        for debut, fin in fenetres(horizon):
            ok = (self.occ_fin >= max(debut, time.time())) & (self.occ_debut <= fin)
            dans_fenetre[self.occ_noeud[ok]] = True
        masque &= dans_fenetre | ~sortie

        if budget in PLAFOND_BUDGET:
            with np.errstate(invalid="ignore"):
                abordable = self.prix <= PLAFOND_BUDGET[budget]  # NaN (prix inconnu) -> False
            inclus = vide.copy()
            for p in set(plateformes) | {ARTE}:
                inclus |= self.masque_plateforme.get(p, vide)
            inclus &= self.verifie
            # livres et jeux : prix inconnu -> exclus dès qu'un budget est demandé
            masque &= np.where(sortie, abordable, np.where(livre | jeu, False, inclus))
        return masque

    def distances(self, centre: Tuple[float, float], indices: Sequence[int]) -> List[float]:
        idx = np.asarray(indices, dtype=np.int64)
        return haversine_km(centre[0], centre[1], self.lat[idx], self.lon[idx]).tolist()

    def prochaine_occurrence(self, index: int, horizon: str = "mois") -> Optional[Tuple[str, str]]:
        """Première occurrence non terminée de la sortie, dans la fenêtre si possible (ISO, Paris)."""
        maintenant = time.time()
        futures = [i for i in np.where(self.occ_noeud == index)[0] if self.occ_fin[i] >= maintenant]
        if not futures:
            return None
        dans = [i for i in futures for d, f in fenetres(horizon)
                if self.occ_fin[i] >= d and self.occ_debut[i] <= f]
        i = min(dans or futures, key=lambda j: self.occ_debut[j])
        iso = lambda ts: datetime.fromtimestamp(ts, PARIS).isoformat()
        return iso(self.occ_debut[i]), iso(self.occ_fin[i])

    def _voisinage(self, v_u: np.ndarray) -> np.ndarray:
        """Masque des nœuds atteignables en 1 ou 2 pas depuis les œuvres de départ."""
        un_pas = self.PT @ v_u
        deux_pas = self.PT @ un_pas
        return (un_pas + deux_pas) > 0

    def marche(self, v_u: np.ndarray, params: Parametres) -> np.ndarray:
        """Distribution pi_u partant de v_u (non nulle sur le départ, à masquer ensuite)."""
        r = v_u
        if params.part_niche > 0:
            voisins = self._voisinage(v_u)
            voisins[v_u > 0] = False
            # restart biaisé sur les films seulement : séries et sorties ont très peu de
            # liens entrants, donc un pi_star minuscule ; pi_star^-beta les rendrait
            # écrasantes (mêmes pépites pour tout le monde). Elles sont atteintes ensuite
            # par la marche depuis ces films de niche.
            voisins &= self.masque_type["film"]
            poids = np.zeros(self.n)
            poids[voisins] = self.pi_star[voisins] ** (-params.beta)
            if poids.sum() > 0:
                r = (1 - params.part_niche) * v_u + params.part_niche * poids / poids.sum()

        # float32 comme P : évite une conversion de type à chaque produit matrice-vecteur
        r = r.astype(np.float32)
        pi = r.copy()
        # nb d'itérations tel que (1-alpha)^n <= TOL_MARCHE : 31 en confort, 5 en découverte
        n_iter = int(np.ceil(np.log(TOL_MARCHE) / np.log(1 - params.alpha)))
        a, b = np.float32(1 - params.alpha), np.float32(params.alpha)
        for _ in range(n_iter):
            pi = a * (self.PT @ pi) + b * r
        return pi.astype(np.float64)

    def recommander(
        self,
        deja_vus: Sequence[str] = (),
        genres: Sequence[str] = (),
        decouverte: float = 0.0,
        k: int = 10,
        autorises: Optional[np.ndarray] = None,
        lift_confort: bool = False,
        cache: Optional[dict] = None,
        themes: Sequence[str] = (),
    ) -> List[Recommandation]:
        """cache : dict partagé entre plusieurs appels d'une même requête (mêmes goûts)
        pour ne calculer chaque marche qu'une fois (ex. films puis séries)."""
        cache = {} if cache is None else cache
        vus = self.indices(deja_vus)
        s = float(np.clip(decouverte, 0.0, 1.0))
        v_u = self.vecteur_depart(vus, genres)
        n_dec = int(round(s * k))

        masque = np.zeros(self.n, dtype=bool) if autorises is None else ~autorises
        masque[vus] = True  # jamais recommander ce qui est déjà vu
        aff = self.affinite(vus, genres)
        # Lecture : les thèmes choisis jouent pour les livres le rôle des genres (confort ↔ découverte)
        m_themes = self.part_themes_choisis(themes)
        livres = self.masque_type.get("livre", np.zeros(self.n, dtype=bool))
        if m_themes is not None:
            aff = np.where(livres, aff * (EPS_AFFINITE + m_themes), aff)
        # ambiances choisies (sorties) : préférence explicite, plus forte que la seule affinité
        choisies = [self.masque_ambiance[g] for g in genres if g in self.masque_ambiance]
        bonus = 1.0 + BONUS_AMBIANCE * np.logical_or.reduce(choisies) if choisies else 1.0

        listes = {}
        if n_dec < k:
            if "confort" not in cache:
                cache["confort"] = self.marche(v_u, CONFORT)
            c = cache["confort"] * aff * self.bonus_affiche * bonus
            if lift_confort:
                c = c / self.pi_star
            c[masque] = -np.inf
            listes["confort"] = (c, meilleurs(c, 3 * k))
        if n_dec > 0:
            if "decouverte" not in cache:
                cache["decouverte"] = self.marche(v_u, DECOUVERTE)
            dans_mes_genres = self.part_genres_choisis(vus, genres)
            if m_themes is not None:
                dans_mes_genres = np.where(livres, m_themes, dans_mes_genres)
            d = (cache["decouverte"] / self.pi_star * self.qualite * self.bonus_affiche
                 * (1 - MALUS_MAX * s * dans_mes_genres) * bonus)
            d[masque] = -np.inf
            listes["decouverte"] = (d, meilleurs(d, 3 * k))

        # entrelacement : la découverte prend ses places réparties uniformément
        quotas = {"confort": k - n_dec, "decouverte": n_dec}
        curseurs = {o: 0 for o in listes}
        pris, titres, resultat = set(), set(), []
        for pos in range(k):
            pris_dec = int(round((pos + 1) * n_dec / k)) - int(round(pos * n_dec / k))
            ordre = ["decouverte", "confort"] if pris_dec else ["confort", "decouverte"]
            for origine in ordre:
                if origine not in listes or quotas[origine] == 0:
                    continue
                scores, top = listes[origine]
                while curseurs[origine] < len(top) and (
                        int(top[curseurs[origine]]) in pris
                        or cle_titre(self.noeuds[int(top[curseurs[origine]])]) in titres):
                    curseurs[origine] += 1
                if curseurs[origine] < len(top):
                    i = int(top[curseurs[origine]])
                    pris.add(i)
                    titres.add(cle_titre(self.noeuds[i]))
                    quotas[origine] -= 1
                    etiquette = None
                    if origine == "decouverte":
                        etiquette = "pepite" if dans_mes_genres[i] >= 0.5 else "hors-piste"
                    resultat.append(Recommandation(i, float(scores[i]), origine, self.noeuds[i], etiquette))
                    break
        return resultat

    def rechercher(self, requete: str, limite: int = 10) -> List[dict]:
        """Recherche de films, séries et livres (titre FR ou original, auteur ; plus populaires d'abord)."""
        q = requete.strip().lower()
        if not q:
            return []
        trouves = [nd for nd in self.noeuds if nd["type"] in ("film", "serie", "livre", "jeu") and (
            q in nd["titre"].lower() or q in (nd.get("titre_original") or "").lower()
            or q in (nd.get("auteur") or "").lower() or q in (nd.get("studio") or "").lower())]
        trouves.sort(key=lambda nd: -(nd.get("nb_likes") or 0))
        return trouves[:limite]
