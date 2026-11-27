"""
API FastAPI : expose le moteur et sert le frontend (100 % local, aucun CDN).

Lancement (depuis la racine du dépôt) :
    uvicorn backend.main:app --reload
"""

import json
import math
import unicodedata
import urllib.parse
import urllib.request
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Literal, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

try:  # lancé comme paquet (uvicorn backend.main:app)
    from .moteur import HORIZONS, Moteur
    from .plateformes import PLATEFORMES
except ImportError:  # lancé depuis backend/ (uvicorn main:app)
    from moteur import HORIZONS, Moteur
    from plateformes import PLATEFORMES

RACINE = Path(__file__).resolve().parent
FRONTEND = RACINE.parent / "frontend"
API_ADRESSE = "https://api-adresse.data.gouv.fr/search/"

app = FastAPI(title="hackathon_ennui")
app.mount("/assets", StaticFiles(directory=FRONTEND / "assets"), name="assets")
moteur = Moteur()  # chargé une fois au démarrage : aucune I/O par requête
VILLES_COUVERTES: Dict[str, List[float]] = json.loads(
    (RACINE / "data" / "france.json").read_text(encoding="utf-8"))["villes"]

# « Intéressé » : en mémoire, remis à zéro au redémarrage (suffisant pour la démo)
interets_ajoutes: Dict[str, int] = defaultdict(int)

CATEGORIES = {
    "cinema": "Cinéma",
    "expo": "Expositions & Musées",
    "scene": "Concerts & Scène",
    "nature": "Nature & Balades",
    "rencontres": "Rencontres & Soirées",
}
GENRES = {  # libellé affiché -> genre MovieLens
    "Science-Fiction": "Sci-Fi", "Thriller": "Thriller", "Drame": "Drama", "Comédie": "Comedy",
    "Animation": "Animation", "Documentaire": "Documentary", "Horreur": "Horror", "Action": "Action",
}
HORIZONS_LIBELLES = {"court": "Aujourd'hui / Ce week-end", "semaine": "Dans la semaine", "mois": "Dans le mois"}
PLATEFORMES_PROPOSEES = [8, 119, 337, 381, 234, 350]  # abonnements (FR.flatrate) uniquement


class DemandeRecommandation(BaseModel):
    type: Literal["film", "serie", "tout", "sortie"] = "film"
    genres: List[str] = Field(default_factory=list, description="genres MovieLens (ex. Sci-Fi)")
    deja_vus: List[str] = Field(default_factory=list, max_length=300,
                                description='œuvres marquées « Déjà vu », ex. "film:2571"')
    decouverte: float = Field(0.0, ge=0.0, le=1.0, description="0 = zone de confort, 1 = découverte")
    plateformes: List[int] = Field(default_factory=list, description="abonnements (films, séries)")
    lat: Optional[float] = Field(None, ge=-90, le=90, description="sorties : centre de recherche")
    lon: Optional[float] = Field(None, ge=-180, le=180)
    rayon_km: float = Field(15.0, ge=5.0, le=50.0)
    horizon: Literal["court", "semaine", "mois"] = "semaine"
    categories: List[str] = Field(default_factory=list, description="sorties : types d'activités")
    k: int = Field(10, ge=1, le=40)


class DemandeInteret(BaseModel):
    id: str
    actif: bool = True


CHAMPS_INTERNES = {"index", "occurrences"}


def exposer(noeud: dict) -> dict:
    """Nœud interne -> objet public, avec le compteur d'intérêts à jour."""
    public = {k: v for k, v in noeud.items() if k not in CHAMPS_INTERNES}
    public["interesses"] = max(0, noeud.get("interesses", 0) + interets_ajoutes[noeud["id"]])
    if noeud.get("categorie"):
        public["categorie_libelle"] = CATEGORIES.get(noeud["categorie"])
    return public


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(FRONTEND / "index.html")


@app.get("/api/sante")
def sante():
    return {"statut": "ok", "noeuds": moteur.n,
            "par_type": {t: int(m.sum()) for t, m in moteur.masque_type.items()},
            "plateformes_verifiees": moteur.plateformes_verifiees}


@app.get("/api/config")
def config():
    """Listes de choix de l'accueil et du profil (source unique : le backend)."""
    return {
        "categories": [{"id": k, "nom": v} for k, v in CATEGORIES.items()],
        "genres": [{"id": v, "nom": k} for k, v in GENRES.items()],
        "plateformes": [{"id": i, "nom": PLATEFORMES[i]} for i in PLATEFORMES_PROPOSEES],
        "plateformes_verifiees": moteur.plateformes_verifiees,
        "horizons": [{"id": h, "nom": HORIZONS_LIBELLES[h]} for h in HORIZONS],
        "rayon": {"min": 5, "max": 50, "defaut": 15},
        "villes_couvertes": sorted(VILLES_COUVERTES),
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
            "nom": f["properties"]["name"],
            "code_postal": f["properties"].get("postcode"),
            "contexte": f["properties"].get("context"),
            "lat": f["geometry"]["coordinates"][1],
            "lon": f["geometry"]["coordinates"][0],
        } for f in feats), "api-adresse"
    except Exception:
        cible = _sans_accents(q)
        return tuple({"nom": v, "code_postal": None, "contexte": "Hors ligne : villes couvertes",
                      "lat": c[0], "lon": c[1]}
                     for v, c in VILLES_COUVERTES.items() if _sans_accents(v).startswith(cible))[:5], "local"


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
    ville, coords = min(VILLES_COUVERTES.items(), key=lambda kv: dist(kv[1]))
    return {"ville": ville, "lat": coords[0], "lon": coords[1], "distance_km": round(dist(coords), 1)}


@app.get("/api/oeuvres")
def rechercher(q: str = Query(..., min_length=2), limite: int = Query(10, ge=1, le=30)):
    """Recherche de films et séries (pour ajouter des « Déjà vu » depuis le profil)."""
    return [exposer(nd) for nd in moteur.rechercher(q, limite)]


def _entrelacer(films, series, k):
    """2 films, 1 série, 2 films, 1 série…"""
    out = []
    while (films or series) and len(out) < k:
        out += films[:2]
        films = films[2:]
        out += series[:1]
        series = series[1:]
    return out[:k]


@app.post("/api/recommandations")
def recommander(d: DemandeRecommandation):
    centre = (d.lat, d.lon) if d.lat is not None and d.lon is not None else None
    cache: dict = {}  # marches partagées entre films et séries

    def classer(type_, k):
        autorises = moteur.autorises([type_], d.plateformes, centre, d.rayon_km, d.categories, d.horizon)
        return moteur.recommander(d.deja_vus, d.genres, d.decouverte, k, autorises,
                                  lift_confort=type_ in ("serie", "sortie"), cache=cache)

    if d.type == "tout":
        n_series = max(1, d.k // 3)
        recos = _entrelacer(classer("film", d.k - n_series), classer("serie", n_series), d.k)
    else:
        recos = classer(d.type, d.k)

    sortie = []
    distances = moteur.distances(centre, [r.index for r in recos]) if centre and d.type == "sortie" else []
    for i, r in enumerate(recos):
        o = {**exposer(r.noeud), "score": r.score, "origine": r.origine}
        if r.noeud["type"] == "sortie":
            prochaine = moteur.prochaine_occurrence(r.index, d.horizon)
            o["prochaine"] = {"debut": prochaine[0], "fin": prochaine[1]} if prochaine else None
            if distances:
                o["distance_km"] = round(distances[i], 1)
        sortie.append(o)
    return sortie


@app.post("/api/interets")
def interet(d: DemandeInteret):
    """« Intéressé » : +1 (actif) ou -1 (retrait) sur le compteur de l'œuvre."""
    if d.id not in moteur.index_par_id:
        raise HTTPException(status_code=404, detail="Œuvre inconnue")
    interets_ajoutes[d.id] += 1 if d.actif else -1
    noeud = moteur.noeuds[moteur.index_par_id[d.id]]
    return {"id": d.id, "interesses": exposer(noeud)["interesses"]}
