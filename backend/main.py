"""
API FastAPI : moteur de recommandation, espace collaboratif (SQLite), synchronisation de
l'agenda en tâche de fond, et service du frontend (100 % local, aucun CDN).

Lancement (depuis la racine du dépôt) :
    uvicorn backend.main:app --reload
Variables : ENNUI_SYNC=0 désactive la synchronisation automatique de l'agenda.
"""

import hashlib
import json
import math
import os
import threading
import unicodedata
import urllib.parse
import urllib.request
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Literal, Optional
from zoneinfo import ZoneInfo

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

try:  # lancé comme paquet (uvicorn backend.main:app)
    from . import database
    from .moteur import BUDGETS, HORIZONS, Moteur
    from .plateformes import PLATEFORMES
    from .scheduler import Synchroniseur
except ImportError:  # lancé depuis backend/ (uvicorn main:app)
    import database
    from moteur import BUDGETS, HORIZONS, Moteur
    from plateformes import PLATEFORMES
    from scheduler import Synchroniseur

RACINE = Path(__file__).resolve().parent
FRONTEND = RACINE.parent / "frontend"
API_ADRESSE = "https://api-adresse.data.gouv.fr/search/"
PARIS = ZoneInfo("Europe/Paris")


# ------------------------------------------------------------------ #
# Moteur (remplaçable à chaud) et cycle de vie                         #
# ------------------------------------------------------------------ #

class Catalogue:
    """Référence vers le moteur courant : la synchronisation le remplace d'un bloc."""
    moteur: Moteur = None
    villes: Dict[str, List[float]] = {}

    @classmethod
    def charger(cls) -> int:
        moteur = Moteur()
        villes = json.loads((RACINE / "data" / "france.json").read_text(encoding="utf-8"))["villes"]
        cls.moteur, cls.villes = moteur, villes  # remplacement atomique pour les requêtes suivantes
        return int(moteur.masque_type["sortie"].sum())


database.initialiser()
Catalogue.charger()
synchro = Synchroniseur(Catalogue.charger)


@asynccontextmanager
async def cycle_de_vie(_app):
    synchro.demarrer()
    yield
    await synchro.arreter()


app = FastAPI(title="hackathon_ennui", lifespan=cycle_de_vie)
# CORS : le frontend est servi par cette même application (même origine), mais on autorise aussi des origines
# externes (autre front, test depuis un autre domaine). ENNUI_ORIGINES = liste séparée par des virgules, « * » par défaut.
# Pas de cookies : l'identité passe par l'en-tête X-Utilisateur, donc allow_credentials reste à False.
ORIGINES = [o.strip() for o in os.environ.get("ENNUI_ORIGINES", "*").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=ORIGINES, allow_credentials=False,
                   allow_methods=["GET", "POST", "PUT", "OPTIONS"], allow_headers=["Content-Type", "X-Utilisateur"])
app.mount("/assets", StaticFiles(directory=FRONTEND / "assets"), name="assets")
app.mount("/vendor", StaticFiles(directory=FRONTEND / "vendor"), name="vendor")  # librairies UI locales
app.mount("/icons", StaticFiles(directory=FRONTEND / "icons"), name="icons")

# Deux univers, six envies. Les catégories fines d'OpenAgenda (fetch_france.py) sont regroupées ;
# celles qui sont hors sujet (ateliers, cuisine, sport, café, créatif…) ne sont plus proposées.
UNIVERS_CHEZ_SOI = {"ecrans": "Films & Séries", "lecture": "Lecture", "jeux": "Jeux vidéo"}
CATEGORIES = {  # univers Sorties : groupe -> libellé
    "culture": "Sorties culturelles",
    "soirees": "Soirées & Concerts",
    "nature": "Balades & Nature",
}
GROUPES_SORTIES = {  # groupe -> catégories fines OpenAgenda
    "culture": ["culture", "cinema", "expo", "scene", "lecture"],
    "soirees": ["soirees"],
    "nature": ["nature"],
}
SORTIES_AUTORISEES = [c for fines in GROUPES_SORTIES.values() for c in fines]
LIBELLES_FINS = {  # étiquette affichée sur les cartes de sorties
    "culture": "Sortie culturelle", "cinema": "Cinéma", "expo": "Expositions & Musées",
    "scene": "Spectacles & Scène", "lecture": "Rencontre littéraire",
    "soirees": "Soirées & Concerts", "nature": "Balades & Nature",
}
THEMES_LIVRES = {"roman": "Roman & Fiction", "polar": "Thriller & Polar", "sff": "Science-Fiction & Fantasy",
                 "essais": "Développement & Essais", "bd": "BD & Manga", "bio": "Biographie & Histoire"}
DUREES = {"tout": "Tout", "express": "Express · < 45 min", "soiree": "Soirée · 1h30 – 2h30",
          "long": "Demi-journée / Week-end"}
MODES_JEU = {"tous": "Tous les modes", "solo": "Solo", "multi": "Multijoueur"}  # multijoueur = co-op ou en ligne
GENRES = {  # libellé affiché -> genre MovieLens
    "Science-Fiction": "Sci-Fi", "Thriller": "Thriller", "Drame": "Drama", "Comédie": "Comedy",
    "Animation": "Animation", "Documentaire": "Documentary", "Horreur": "Horror", "Action": "Action",
    "Romance": "Romance", "Policier": "Crime", "Fantastique": "Fantasy",
    "Historique": "War",  # MovieLens n'a pas de genre « Histoire » : « War » est le plus proche
}
AMBIANCES = {  # étiquettes des sorties, repérées dans leur texte par fetch_france.py
    "festif": "Faire la fête",
    "calme": "Tranquille",
    "drole": "Pour rire",
    "insolite": "Insolite",
    "competitif": "Esprit de compét'",
    "artistique": "Inspirant",
}
HORIZONS_PROPOSES = ("maintenant", "aujourdhui", "weekend", "semaine", "mois")
HORIZONS_LIBELLES = {"maintenant": "Maintenant", "aujourdhui": "Aujourd'hui", "weekend": "Ce week-end",
                     "semaine": "Dans la semaine", "mois": "Dans le mois", "court": "Aujourd'hui / Ce week-end"}
BUDGETS_LIBELLES = {"tous": "Tous les prix", "gratuit": "Gratuit", "moins10": "Moins de 10 €", "moins25": "Moins de 25 €"}
PLATEFORMES_PROPOSEES = [8, 119, 337, 381, 234, 350]  # abonnements (FR.flatrate) uniquement
CONSOLES = {"pc": "PC", "mac": "Mac", "switch": "Switch", "playstation": "PlayStation", "xbox": "Xbox", "mobile": "Mobile"}


# ------------------------------------------------------------------ #
# Schémas                                                              #
# ------------------------------------------------------------------ #

class Ville(BaseModel):
    nom: str = Field(..., min_length=1, max_length=80)
    contexte: Optional[str] = Field(None, max_length=120)
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)


class Avatar(BaseModel):
    """Personnage illustré DiceBear (lorelei / micah), rendu côté client avec les modules locaux (frontend/vendor/dicebear).
    Les valeurs fines (coiffure, lunettes, expression, regard) sont vérifiées par style côté client ; ici, format seulement."""
    style: Literal["lorelei", "micah"]
    seed: str = Field(..., min_length=1, max_length=40)
    bg: Literal["1e293b", "27294a", "422b18", "13382e", "351f47", "293548"]
    hair: Optional[str] = Field(None, pattern=r"^[A-Za-z0-9]{1,24}$")
    glasses: Optional[str] = Field(None, pattern=r"^[A-Za-z0-9]{1,24}$")
    mouth: Optional[str] = Field(None, pattern=r"^[A-Za-z0-9]{1,24}$")
    eyes: Optional[str] = Field(None, pattern=r"^[A-Za-z0-9]{1,24}$")


class Profil(BaseModel):
    prenom: str = Field(..., min_length=1, max_length=30)
    ville: Optional[Ville] = None
    prefs: dict = Field(default_factory=dict)
    avatar: Optional[Avatar] = None

    @field_validator("prenom")
    @classmethod
    def nettoyer_prenom(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("prénom vide")
        return v

    @field_validator("prefs")
    @classmethod
    def limiter_prefs(cls, v: dict) -> dict:
        if len(json.dumps(v)) > 30000:
            raise ValueError("préférences trop volumineuses")
        return v


class DemandeRecommandation(BaseModel):
    type: Literal["film", "serie", "livre", "jeu", "tout", "sortie"] = "film"
    ecrans: List[Literal["film", "serie", "livre", "jeu"]] = Field(default_factory=lambda: ["film", "serie"],
                                                         description="composition du type « tout »")
    genres: List[str] = Field(default_factory=list, description="genres MovieLens (ex. Sci-Fi)")
    deja_vus: List[str] = Field(default_factory=list, max_length=300)
    decouverte: float = Field(0.0, ge=0.0, le=1.0, description="0 = zone de confort, 1 = découverte")
    plateformes: List[int] = Field(default_factory=list, description="abonnements (films, séries)")
    lat: Optional[float] = Field(None, ge=-90, le=90)
    lon: Optional[float] = Field(None, ge=-180, le=180)
    rayon_km: float = Field(15.0, ge=5.0, le=50.0)
    horizon: Literal["maintenant", "aujourdhui", "weekend", "semaine", "mois", "court"] = "semaine"
    budget: Literal["tous", "gratuit", "moins10", "moins25"] = "tous"
    categories: List[str] = Field(default_factory=list)
    consoles: List[str] = Field(default_factory=list, description="jeux : pc, mac, playstation, xbox, switch, mobile")
    mode_jeu: Literal["tous", "solo", "coop", "multi"] = "tous"
    themes: List[str] = Field(default_factory=list, description="livres : roman, polar, sff, essais, bd, bio")
    duree: Literal["tout", "express", "soiree", "long"] = "tout"
    k: int = Field(10, ge=1, le=40)


class DemandePlan(BaseModel):
    oeuvre_id: str = Field(..., max_length=80)
    debut: str = Field(..., description="ISO 8601 ; sans fuseau = heure de Paris (champ datetime-local)")
    rendez_vous: str = Field("", max_length=200, description="point de rendez-vous ou lien de watch-party")
    message: str = Field("", max_length=280)


class DemandeSortie(BaseModel):
    titre: str = Field(..., min_length=3, max_length=100)
    categorie: str
    lieu: str = Field(..., min_length=2, max_length=120)
    ville: Ville
    debut: str = Field(..., description="ISO 8601 ; sans fuseau = heure de Paris")
    duree_h: float = Field(3.0, gt=0, le=24)
    prix: Optional[float] = Field(None, ge=0, le=500, description="euros ; 0 = gratuit ; vide = non précisé")
    description: str = Field("", max_length=500)


class Participation(BaseModel):
    actif: bool = True


class Message(BaseModel):
    texte: str = Field(..., min_length=1, max_length=280)


# ------------------------------------------------------------------ #
# Utilitaires                                                          #
# ------------------------------------------------------------------ #

CHAMPS_INTERNES = {"index", "occurrences"}


def exposer(noeud: dict) -> dict:
    public = {k: v for k, v in noeud.items() if k not in CHAMPS_INTERNES}
    if noeud.get("categorie"):
        public["categorie_libelle"] = LIBELLES_FINS.get(noeud["categorie"])
    return public


def utilisateur_requis(uid: Optional[str]) -> dict:
    u = database.lire_utilisateur(uid) if uid else None
    if not u:
        raise HTTPException(status_code=401, detail="Connexion requise")
    return u


def lire_date(texte: str) -> datetime:
    try:
        d = datetime.fromisoformat(texte)
    except ValueError:
        raise HTTPException(status_code=422, detail="Date invalide")
    return d.replace(tzinfo=PARIS) if d.tzinfo is None else d


# ------------------------------------------------------------------ #
# Routes : base                                                        #
# ------------------------------------------------------------------ #

@app.get("/", include_in_schema=False)
def index():
    return FileResponse(FRONTEND / "index.html")


@app.get("/manifest.json", include_in_schema=False)
def manifeste():
    return FileResponse(FRONTEND / "manifest.json", media_type="application/manifest+json")


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    # servi à la racine : sa portée couvre toute l'application ; jamais mis en cache par le navigateur
    return FileResponse(FRONTEND / "sw.js", media_type="text/javascript",
                        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})


@app.get("/api/sante")
def sante():
    m = Catalogue.moteur
    return {"statut": "ok", "noeuds": m.n, "par_type": {t: int(x.sum()) for t, x in m.masque_type.items()},
            "plateformes_verifiees": m.plateformes_verifiees, "agenda": synchro.etat()}


@app.get("/api/config")
def config():
    return {
        "categories": [{"id": k, "nom": v, "sorties": True} for k, v in CATEGORIES.items()],
        # « jeux » est à la fois une catégorie de sorties (événements gaming) et l'envie qui ajoute
        # les jeux vidéo « Chez soi » dans Pour vous : une seule envie, les deux sens
        "envies": [{"id": k, "nom": v, "univers": "chez-soi"} for k, v in UNIVERS_CHEZ_SOI.items()]
                  + [{"id": k, "nom": v, "univers": "sorties"} for k, v in CATEGORIES.items()],
        "themes": [{"id": k, "nom": v} for k, v in THEMES_LIVRES.items()],
        "durees": [{"id": k, "nom": v} for k, v in DUREES.items()],
        "consoles": [{"id": k, "nom": v} for k, v in CONSOLES.items()],
        "modes_jeu": [{"id": k, "nom": v} for k, v in MODES_JEU.items()],
        "genres": [{"id": v, "nom": k} for k, v in GENRES.items()],
        "ambiances": [{"id": k, "nom": v} for k, v in AMBIANCES.items()],
        "plateformes": [{"id": i, "nom": PLATEFORMES[i]} for i in PLATEFORMES_PROPOSEES],
        "plateformes_verifiees": Catalogue.moteur.plateformes_verifiees,
        "horizons": [{"id": h, "nom": HORIZONS_LIBELLES[h]} for h in HORIZONS_PROPOSES],
        "budgets": [{"id": b, "nom": BUDGETS_LIBELLES[b]} for b in BUDGETS],
        "rayon": {"min": 5, "max": 50, "defaut": 15},
        "villes_couvertes": sorted(Catalogue.villes),
    }


def _sans_accents(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


@lru_cache(maxsize=512)
def _communes(q: str):
    """API Adresse (data.gouv.fr), communes uniquement ; repli local si le réseau ne répond pas."""
    try:
        url = f"{API_ADRESSE}?{urllib.parse.urlencode({'q': q, 'type': 'municipality', 'limit': 5})}"
        req = urllib.request.Request(url, headers={"User-Agent": "hackathon-ennui/0.1"})
        with urllib.request.urlopen(req, timeout=3) as r:
            feats = json.load(r)["features"]
        return tuple({
            "nom": f["properties"]["name"], "code_postal": f["properties"].get("postcode"),
            "contexte": f["properties"].get("context"),
            "lat": f["geometry"]["coordinates"][1], "lon": f["geometry"]["coordinates"][0],
        } for f in feats), "api-adresse"
    except Exception:
        cible = _sans_accents(q)
        return tuple({"nom": v, "code_postal": None, "contexte": "Hors ligne : villes couvertes",
                      "lat": c[0], "lon": c[1]}
                     for v, c in Catalogue.villes.items() if _sans_accents(v).startswith(cible))[:5], "local"


@app.get("/api/communes")
def communes(q: str = Query(..., min_length=2, max_length=60)):
    resultats, source = _communes(q.strip())
    return {"source": source, "communes": list(resultats)}


@app.get("/api/couverture")
def couverture(lat: float, lon: float):
    """Ville couverte (avec des sorties collectées) la plus proche d'un point."""
    def dist(c):
        p = math.pi / 180
        a = (math.sin((c[0] - lat) * p / 2) ** 2
             + math.cos(lat * p) * math.cos(c[0] * p) * math.sin((c[1] - lon) * p / 2) ** 2)
        return 12742 * math.asin(math.sqrt(a))
    ville, coords = min(Catalogue.villes.items(), key=lambda kv: dist(kv[1]))
    return {"ville": ville, "lat": coords[0], "lon": coords[1], "distance_km": round(dist(coords), 1)}


@app.get("/api/oeuvre")
def oeuvre(id: str = Query(..., max_length=80)):
    """Une œuvre ou une sortie par son identifiant (fiche de « Mes envies », de « Mes plans »)."""
    m = Catalogue.moteur
    i = m.index_par_id.get(id)
    if i is None:
        raise HTTPException(status_code=404, detail="Œuvre introuvable (sortie passée ou retirée du catalogue)")
    return exposer(m.noeuds[i])


@app.get("/api/oeuvres")
def rechercher(q: str = Query(..., min_length=2), limite: int = Query(10, ge=1, le=30)):
    return [exposer(nd) for nd in Catalogue.moteur.rechercher(q, limite)]


# ------------------------------------------------------------------ #
# Routes : recommandations                                             #
# ------------------------------------------------------------------ #

POIDS_ECRANS = {"film": 2, "serie": 1, "livre": 1, "jeu": 1}  # « tout » : 2 films, 1 série, 1 livre, 1 jeu…


def _entrelacer(listes: Dict[str, list], k: int) -> list:
    out = []
    while any(listes.values()) and len(out) < k:
        for t, l in listes.items():
            out += l[:POIDS_ECRANS[t]]
            listes[t] = l[POIDS_ECRANS[t]:]
    return out[:k]


@app.post("/api/recommandations")
def recommander(d: DemandeRecommandation, x_utilisateur: Optional[str] = Header(None)):
    m = Catalogue.moteur  # référence figée pour toute la requête (synchronisation à chaud)
    centre = (d.lat, d.lon) if d.lat is not None and d.lon is not None else None
    cache: dict = {}  # marches partagées entre films et séries
    # envies de sorties -> catégories fines ; aucune -> toutes les catégories autorisées (jamais les hors-sujet)
    groupes = [c for c in d.categories if c in GROUPES_SORTIES]
    categories = [f for g in groupes for f in GROUPES_SORTIES[g]] or SORTIES_AUTORISEES
    genres_ecrans = [g for g in d.genres if g not in AMBIANCES]  # les ambiances ne concernent que les sorties

    def classer(type_, k):
        autorises = m.autorises([type_], d.plateformes, centre, d.rayon_km, categories, d.horizon, d.budget,
                                d.consoles, d.mode_jeu, d.duree)
        genres = d.genres if type_ == "sortie" else genres_ecrans
        return m.recommander(d.deja_vus, genres, d.decouverte, k, autorises,
                             lift_confort=type_ in ("serie", "livre", "jeu", "sortie"), cache=cache,
                             themes=d.themes if type_ == "livre" else ())

    if d.type == "tout":
        types = list(dict.fromkeys(d.ecrans)) or ["film"]
        total = sum(POIDS_ECRANS[t] for t in types)
        recos = _entrelacer({t: classer(t, max(1, round(d.k * POIDS_ECRANS[t] / total)) + 1) for t in types}, d.k)
    else:
        recos = classer(d.type, d.k)

    plans = database.plans_par_oeuvre([r.noeud["id"] for r in recos], x_utilisateur)
    distances = m.distances(centre, [r.index for r in recos]) if centre and d.type == "sortie" else []
    sortie = []
    for i, r in enumerate(recos):
        o = {**exposer(r.noeud), "score": r.score, "origine": r.origine, "etiquette": r.etiquette,
             "plans": plans.get(r.noeud["id"], [])}
        if r.noeud["type"] == "sortie":
            prochaine = m.prochaine_occurrence(r.index, d.horizon)
            o["prochaine"] = {"debut": prochaine[0], "fin": prochaine[1]} if prochaine else None
            if distances:
                o["distance_km"] = round(distances[i], 1)
        sortie.append(o)
    return sortie


# ------------------------------------------------------------------ #
# Routes : comptes (connexion express)                                 #
# ------------------------------------------------------------------ #

@app.post("/api/utilisateurs")
def creer_utilisateur(p: Profil, taches: BackgroundTasks):
    if p.ville:  # ville hors couverture : collecte ciblée en arrière-plan
        taches.add_task(synchro.ajouter_ville, p.ville.nom, p.ville.lat, p.ville.lon)
    return database.creer_utilisateur(p.prenom, p.ville.model_dump() if p.ville else None, p.prefs,
                                      p.avatar.model_dump(exclude_none=True) if p.avatar else None)


@app.get("/api/utilisateurs/moi")
def moi(x_utilisateur: Optional[str] = Header(None)):
    return utilisateur_requis(x_utilisateur)


class Dispo(BaseModel):
    statut: Literal["indispo", "sortir", "distance"]


class DemandeAmi(BaseModel):
    code: str = Field(..., min_length=3, max_length=40)


class DemandeReprise(BaseModel):
    code: str = Field(..., min_length=3, max_length=40)
    pin: Optional[str] = Field(None, pattern=r"^\d{4}$")


class DemandePin(BaseModel):
    pin: Optional[str] = Field(None, pattern=r"^\d{4}$", description="4 chiffres ; null = retirer le PIN")


# Anti-essais : 5 PIN faux en 15 min par profil -> reprise bloquée jusqu'à la fin de la fenêtre (mémoire du processus)
ESSAIS_MAX, FENETRE_ESSAIS = 5, timedelta(minutes=15)
_echecs_pin: Dict[str, List[datetime]] = {}
_verrou_pin = threading.Lock()


@app.post("/api/utilisateurs/reprendre")
def reprendre_profil(d: DemandeReprise):
    """Reprendre un profil existant sur un nouvel appareil (ou après avoir perdu le stockage du navigateur)
    avec son code « Prénom#123 », et son PIN s'il en a un. Renvoie le compte complet, jeton compris."""
    u = database.utilisateur_par_code(d.code)
    if not u:
        raise HTTPException(status_code=404, detail="Aucun profil avec ce code")
    pin_hash = u.pop("_pin_hash")
    if pin_hash:
        cle = u["code"].lower()
        maintenant = datetime.now(timezone.utc)
        with _verrou_pin:
            recents = [t for t in _echecs_pin.get(cle, []) if maintenant - t < FENETRE_ESSAIS]
            _echecs_pin[cle] = recents
        if len(recents) >= ESSAIS_MAX:
            minutes = max(1, math.ceil((recents[0] + FENETRE_ESSAIS - maintenant).total_seconds() / 60))
            raise HTTPException(status_code=429, detail=f"Trop d'essais : réessaie dans {minutes} min")
        if not d.pin:
            raise HTTPException(status_code=403, detail="PIN requis")
        if not database.pin_valide(pin_hash, d.pin):
            with _verrou_pin:
                _echecs_pin.setdefault(cle, []).append(maintenant)
            raise HTTPException(status_code=403, detail="PIN incorrect")
        with _verrou_pin:
            _echecs_pin.pop(cle, None)
    return u


@app.put("/api/utilisateurs/moi/pin")
def definir_pin(d: DemandePin, x_utilisateur: Optional[str] = Header(None)):
    """Active, change ou retire (pin: null) le PIN qui protège la reprise du profil sur un autre appareil."""
    u = utilisateur_requis(x_utilisateur)
    return database.definir_pin(u["id"], d.pin)


@app.get("/api/utilisateurs/profils")
def profils(q: str = Query("", max_length=40)):
    """Liste publique des profils enregistrés (prénom, code, ville, avatar ; jamais le jeton)."""
    return database.lister_profils(q)


@app.put("/api/utilisateurs/moi/avatar")
def changer_avatar(a: Avatar, x_utilisateur: Optional[str] = Header(None)):
    u = utilisateur_requis(x_utilisateur)
    return database.changer_avatar(u["id"], a.model_dump(exclude_none=True))


@app.put("/api/utilisateurs/moi/dispo")
def changer_dispo(d: Dispo, x_utilisateur: Optional[str] = Header(None)):
    """Statut du moment visible par ses amis (expire au bout de 12 h)."""
    u = utilisateur_requis(x_utilisateur)
    return database.changer_dispo(u["id"], d.statut)


# ------------------------------------------------------------------ #
# Routes : amis (le code public « Prénom#123 » sert d'identifiant ;    #
# le jeton du compte n'est jamais exposé aux autres)                   #
# ------------------------------------------------------------------ #

@app.get("/api/amis")
def lister_amis(x_utilisateur: Optional[str] = Header(None)):
    u = utilisateur_requis(x_utilisateur)
    return {"amis": database.amis(u["id"]), "suggestions": database.suggestions(u["id"])}


@app.get("/api/amis/recherche")
def rechercher_amis(q: str = Query(..., min_length=2, max_length=40), x_utilisateur: Optional[str] = Header(None)):
    u = utilisateur_requis(x_utilisateur)
    return database.rechercher_profils(u["id"], q)


@app.post("/api/amis")
def ajouter_ami(d: DemandeAmi, x_utilisateur: Optional[str] = Header(None)):
    u = utilisateur_requis(x_utilisateur)
    ami = database.ajouter_ami(u["id"], d.code)
    if not ami:
        raise HTTPException(status_code=404, detail="Aucun profil avec ce code")
    return ami


@app.post("/api/amis/retirer")
def retirer_ami(d: DemandeAmi, x_utilisateur: Optional[str] = Header(None)):
    u = utilisateur_requis(x_utilisateur)
    if not database.retirer_ami(u["id"], d.code):
        raise HTTPException(status_code=404, detail="Aucun profil avec ce code")
    return {"ok": True}


@app.put("/api/utilisateurs/moi")
def modifier_moi(p: Profil, taches: BackgroundTasks, x_utilisateur: Optional[str] = Header(None)):
    u = utilisateur_requis(x_utilisateur)
    if p.ville and (u["ville"] or {}).get("nom") != p.ville.nom:
        taches.add_task(synchro.ajouter_ville, p.ville.nom, p.ville.lat, p.ville.lon)
    return database.mettre_a_jour_utilisateur(u["id"], p.prenom, p.ville.model_dump() if p.ville else None, p.prefs)


# ------------------------------------------------------------------ #
# Routes : plans collaboratifs                                         #
# ------------------------------------------------------------------ #

@app.get("/api/plans")
def plans(oeuvre_id: str, x_utilisateur: Optional[str] = Header(None)):
    return database.plans_detail(oeuvre_id, x_utilisateur)


@app.post("/api/plans")
def creer_plan(p: DemandePlan, x_utilisateur: Optional[str] = Header(None)):
    u = utilisateur_requis(x_utilisateur)
    m = Catalogue.moteur
    if p.oeuvre_id not in m.index_par_id:
        raise HTTPException(status_code=404, detail="Œuvre inconnue")
    debut = lire_date(p.debut)
    maintenant = datetime.now(timezone.utc)
    if debut < maintenant - timedelta(minutes=5):
        raise HTTPException(status_code=422, detail="Ce créneau est déjà passé")
    if debut > maintenant + timedelta(days=60):
        raise HTTPException(status_code=422, detail="Créneau trop lointain (60 jours maximum)")
    noeud = m.noeuds[m.index_par_id[p.oeuvre_id]]
    plan_id = database.creer_plan(u["id"], noeud, debut.isoformat(), p.rendez_vous.strip(), p.message.strip())
    return {"id": plan_id, "plans": database.plans_detail(p.oeuvre_id, u["id"])}


@app.post("/api/plans/{plan_id}/participation")
def participation(plan_id: int, p: Participation, x_utilisateur: Optional[str] = Header(None)):
    u = utilisateur_requis(x_utilisateur)
    if not database.rejoindre(plan_id, u["id"], p.actif):
        raise HTTPException(status_code=404, detail="Plan introuvable")
    return {"ok": True}


@app.post("/api/plans/{plan_id}/messages")
def message(plan_id: int, msg: Message, x_utilisateur: Optional[str] = Header(None)):
    u = utilisateur_requis(x_utilisateur)
    if not database.ajouter_message(plan_id, u["id"], msg.texte.strip()):
        raise HTTPException(status_code=404, detail="Plan introuvable")
    return {"ok": True}


@app.get("/api/plans/a-venir")
def plans_a_venir(limite: int = Query(12, ge=1, le=40), x_utilisateur: Optional[str] = Header(None)):
    """Watch-parties, sessions et sorties à plusieurs à venir (toutes œuvres), avec le visuel de l'œuvre."""
    return avec_visuel(database.plans_a_venir(limite, x_utilisateur))


def avec_visuel(plans: List[dict]) -> List[dict]:
    m = Catalogue.moteur
    out = []
    for p in plans:
        i = m.index_par_id.get(p["oeuvre_id"])
        noeud = m.noeuds[i] if i is not None else {}
        out.append({**p, "affiche": noeud.get("affiche"), "categorie": noeud.get("categorie"), "ville": noeud.get("ville")})
    return out


@app.get("/api/sync")
def synchroniser_client(v: Optional[str] = Query(None, max_length=40), x_utilisateur: Optional[str] = Header(None)):
    """Synchronisation légère (appelée toutes les 12 s par l'appli visible) : humeurs et avatars des amis,
    plans à venir de moi et de mes amis (participants inscrits). Si la version `v` du client est à jour,
    la réponse ne contient que {v, inchange} (quelques octets)."""
    u = utilisateur_requis(x_utilisateur)
    donnees = {"amis": database.amis(u["id"]), "plans": avec_visuel(database.plans_entourage(u["id"])),
               "dispo": database.lire_utilisateur(u["id"])["dispo"]}
    version = hashlib.sha1(json.dumps(donnees, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    if v == version:
        return {"v": version, "inchange": True}
    return {"v": version, "inchange": False, **donnees}


@app.get("/api/mes-plans")
def mes_plans(x_utilisateur: Optional[str] = Header(None)):
    return database.mes_plans(utilisateur_requis(x_utilisateur)["id"])


# ------------------------------------------------------------------ #
# Routes : sorties publiées par les utilisateurs                       #
# ------------------------------------------------------------------ #

@app.post("/api/sorties")
async def publier_sortie(s: DemandeSortie, x_utilisateur: Optional[str] = Header(None)):
    """Publie une soirée / sortie étudiante : enregistrée en SQLite et ajoutée au graphe (~1 s)."""
    u = utilisateur_requis(x_utilisateur)
    if s.categorie not in GROUPES_SORTIES:
        raise HTTPException(status_code=422, detail="Catégorie inconnue")
    debut = lire_date(s.debut)
    maintenant = datetime.now(timezone.utc)
    if not maintenant - timedelta(minutes=5) <= debut <= maintenant + timedelta(days=60):
        raise HTTPException(status_code=422, detail="La date doit être dans les 60 prochains jours")
    fin = debut + timedelta(hours=s.duree_h)
    sortie_id = database.creer_sortie(u["id"], " ".join(s.titre.split()), s.categorie, s.lieu.strip(),
                                      s.ville.model_dump(), debut.isoformat(), fin.isoformat(), s.prix,
                                      s.description.strip())
    await synchro.reconstruire()
    return {"id": f"sortie:co-{sortie_id}"}


# ------------------------------------------------------------------ #
# Routes : agenda                                                      #
# ------------------------------------------------------------------ #

@app.get("/api/agenda")
def agenda():
    return synchro.etat()


@app.post("/api/agenda/synchroniser")
async def synchroniser():
    """Lance une mise à jour en arrière-plan et rend la main tout de suite."""
    import asyncio
    if not synchro.en_cours:
        asyncio.create_task(synchro.synchroniser(manuel=True))
        await asyncio.sleep(0)  # laisse la tâche passer « en_cours »
    return synchro.etat()


if __name__ == "__main__":
    # Lancement direct : écoute sur toutes les interfaces (téléphone sur le même Wi-Fi, conteneur, hébergeur).
    # PORT est fourni par les hébergeurs (Render, Railway, Fly…).
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
