"""
Récupère des événements culturels À VENIR dans les grandes villes universitaires françaises.

Source ouverte, sans clé : OpenAgenda (événements publics) via l'API Opendatasoft
https://public.opendatasoft.com/explore/dataset/evenements-publics-openagenda
Coordonnées des villes : API Adresse (https://api-adresse.data.gouv.fr), repli sur une table locale.

Garanties sur les dates :
    - on ne garde que les occurrences (timings) qui commencent dans [maintenant, maintenant + HORIZON]
    - un événement sans occurrence future est écarté
    - date_debut / date_fin au format YYYY-MM-DD (fuseau Europe/Paris)
    - les occurrences [début, fin] réelles (ISO avec fuseau) sont stockées : l'API recalcule la prochaine
      occurrence à chaque requête, donc rien de passé ne s'affiche même si ce fichier vieillit

Sortie : backend/data/france.json (versionné : repli si le réseau tombe).

Usage :
    python3 backend/fetch_france.py [--jours 35]
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

SORTIE = Path(__file__).resolve().parent / "data" / "france.json"
UA = "hackathon-ennui/0.1 (projet etudiant)"
OPENAGENDA = ("https://public.opendatasoft.com/api/explore/v2.1/catalog/datasets/"
              "evenements-publics-openagenda/records")
API_ADRESSE = "https://api-adresse.data.gouv.fr/search/"
PARIS = ZoneInfo("Europe/Paris")
RAYON_KM = 15          # rayon de collecte autour de chaque ville
PAGES_MAX = 3          # 100 événements bruts par page

# ville -> (lat, lon approximatifs de repli, quota d'événements retenus)
VILLES = {
    "Paris": (48.8566, 2.3522, 120), "Lyon": (45.7640, 4.8357, 80), "Marseille": (43.2965, 5.3698, 70),
    "Toulouse": (43.6045, 1.4440, 70), "Lille": (50.6292, 3.0573, 70), "Bordeaux": (44.8378, -0.5792, 70),
    "Nantes": (47.2184, -1.5536, 70), "Rennes": (48.1173, -1.6778, 70), "Strasbourg": (48.5734, 7.7521, 70),
    "Montpellier": (43.6108, 3.8767, 70), "Grenoble": (45.1885, 5.7245, 60), "Nice": (43.7102, 7.2620, 50),
    "Clermont-Ferrand": (45.7772, 3.0870, 50), "Dijon": (47.3220, 5.0415, 50), "Tours": (47.3941, 0.6848, 50),
    "Angers": (47.4784, -0.5632, 50), "Caen": (49.1829, -0.3707, 50), "Rouen": (49.4432, 1.0999, 50),
    "Nancy": (48.6921, 6.1844, 50), "Metz": (49.1193, 6.1757, 40), "Reims": (49.2583, 4.0317, 40),
    "Poitiers": (46.5802, 0.3404, 40), "Limoges": (45.8336, 1.2611, 40), "Besançon": (47.2378, 6.0241, 40),
    "Orléans": (47.9030, 1.9093, 40), "Brest": (48.3904, -4.4861, 40), "Saint-Étienne": (45.4397, 4.3872, 40),
    "Amiens": (49.8941, 2.2958, 40), "Le Mans": (48.0061, 0.1996, 40), "Pau": (43.2951, -0.3708, 35),
    "Perpignan": (42.6887, 2.8948, 35), "La Rochelle": (46.1603, -1.1511, 35), "Avignon": (43.9493, 4.8055, 35),
    "Toulon": (43.1242, 5.9280, 35), "Vannes": (47.6582, -2.7608, 30), "Quimper": (47.9960, -4.1024, 30),
    "Lorient": (47.7483, -3.3700, 30), "Saint-Malo": (48.6493, -2.0257, 30), "Bayonne": (43.4929, -1.4748, 30),
    "Annecy": (45.8992, 6.1294, 30),
}

CATEGORIES = {
    "cinema": "Cinéma",
    "expo": "Expositions & Musées",
    "scene": "Concerts & Scène",
    "nature": "Nature & Balades",
    "rencontres": "Rencontres & Soirées",
}

MOTS_CATEGORIE = {
    "cinema": r"cin[ée]ma|cin[ée]-|projection|court[- ]m[ée]trage|long[- ]m[ée]trage|\bfilms?\b|cin[ée]club",
    "scene": r"concert|spectacle|th[ée][aâ]tre|danse|op[ée]ra|cirque|humour|stand[- ]up|musique|jazz|rock|"
             r"chorale|r[ée]cital|orchestre|chanson|\brap\b|electro|festival",
    "expo": r"exposition|\bexpo\b|mus[ée]e|vernissage|galerie|visite guid[ée]e|patrimoine|photograph|peinture|"
            r"sculpture|\bart\b|arts plastiques",
    "nature": r"balade|randonn[ée]e|\brando\b|nature|jardin|marais|for[êe]t|littoral|oiseaux|botanique|"
              r"\bv[ée]lo\b|sentier|plage|estran|\bparcs?\b",
    "rencontres": r"conf[ée]rence|rencontre|d[ée]bat|atelier|soir[ée]e|quiz|\bjeux?\b|lecture|d[ée]dicace|"
                  r"\bclub\b|ap[ée]ro|\bbal\b|caf[ée]|discussion|table ronde",
}

MOTS_GENRES = [
    (r"science|astronom|espace|robot|num[ée]rique|futur", ["Sci-Fi"]),
    (r"polar|enqu[êe]te|crime|meurtre|policier", ["Crime", "Mystery"]),
    (r"horreur|halloween|frisson|zombie|vampire", ["Horror"]),
    (r"fantastique|f[ée]e|l[ée]gende|conte|magie|dragon", ["Fantasy"]),
    (r"guerre|r[ée]sistance|m[ée]moire|14-18|1939|1944|militaire", ["War"]),
    (r"western|cowboy|country", ["Western"]),
    (r"amour|romantique|saint-valentin", ["Romance"]),
    (r"manga|\bbd\b|bande dessin[ée]e|anim[ée]|animation", ["Animation"]),
    (r"jazz|chant|musique|concert|op[ée]ra|danse", ["Musical"]),
    (r"humour|com[ée]die|rire|impro", ["Comedy"]),
    (r"aventure|exploration|voyage|mer|marin|bateau|voile", ["Adventure"]),
    (r"myst[èe]re|secret|[ée]nigme|escape", ["Mystery"]),
    (r"thriller|suspense", ["Thriller"]),
    (r"documentaire|histoire|patrimoine|t[ée]moignage", ["Documentary"]),
    (r"drame|trag[ée]die", ["Drama"]),
]

GENRES_CATEGORIE = {
    "cinema": ["Drama"],
    "expo": ["Documentary", "Drama"],
    "scene": ["Musical", "Comedy"],
    "nature": ["Documentary", "Adventure"],
    "rencontres": ["Documentary", "Comedy"],
}

EXCLUSIONS = (r"annul|report[ée]|complet|b[ée]b[ée]|tout-petits|0-3 ans|3-6 ans|maternelle|ehpad|r[ée]serv[ée] aux|"
              r"emploi|int[ée]rim|recrut|employeur|\bjob|permanence|formation|\bcv\b|entreprise|"
              r"insertion|france travail|alternance|candidat|m[ée]tiers?\b|coach|"
              r"p[èe]re no[ëe]l|lutin|jeune public|d[èe]s \d ans|[àa] partir de [1-9] ans|pour les enfants|"
              r"en famille|petite enfance|go[ûu]ter|messe|c[ée]l[ée]bration|catéchisme")


# ------------------------------------------------------------------ #
# Utilitaires                                                          #
# ------------------------------------------------------------------ #

def http_json(url: str, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for essai in range(5):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 502, 503, 504) and essai < 4:
                time.sleep(5 * (essai + 1))
                continue
            raise


def geocoder(ville, repli):
    """Coordonnées exactes de la commune via l'API Adresse (repli : table locale)."""
    try:
        q = urllib.parse.urlencode({"q": ville, "type": "municipality", "limit": 1})
        f = http_json(f"{API_ADRESSE}?{q}", timeout=15)["features"][0]
        lon, lat = f["geometry"]["coordinates"]
        return round(lat, 5), round(lon, 5)
    except Exception:  # réseau, format : la table locale suffit
        return repli


def categoriser(texte: str):
    t = texte.lower()
    scores = {c: len(re.findall(m, t)) for c, m in MOTS_CATEGORIE.items()}
    meilleur = max(scores, key=lambda c: scores[c])
    return meilleur if scores[meilleur] > 0 else None


def genres_pour(categorie: str, texte: str):
    t = texte.lower()
    genres = list(GENRES_CATEGORIE[categorie])
    for motif, gs in MOTS_GENRES:
        if re.search(motif, t):
            genres += [g for g in gs if g not in genres]
    return genres[:3]


def tarif(conditions: str):
    """-> (prix_min en euros ou None, libellé). Ne déduit rien qui n'est pas écrit."""
    if not conditions:
        return None, None
    t = conditions.lower()
    montants = lambda s: [float(x.replace(",", ".")) for x in
                          re.findall(r"(\d+(?:[.,]\d{1,2})?)\s*(?:€|euros?)", s)]
    if re.search(r"gratuit|entr[ée]e libre|acc[eè]s libre", t) and not montants(t):
        return 0.0, "Gratuit"
    for segment in re.split(r"[;\n/|]|\. ", t):
        if re.search(r"[ée]tudiant|r[ée]duit|-\s*26|moins de 2[56]", segment) and montants(segment):
            p = min(montants(segment))
            return p, ("Gratuit étudiant" if p == 0 else f"{p:g} € tarif réduit".replace(".", ","))
    if montants(t):
        p = min(montants(t))
        return p, ("Gratuit" if p == 0 else f"Dès {p:g} €".replace(".", ","))
    if "gratuit" in t:
        return 0.0, "Gratuit"
    return None, None


def occurrences_futures(timings_json, maintenant, limite):
    """[début, fin] réels (ISO, fuseau conservé) des occurrences pas encore terminées et
    commençant avant `limite`. Une occurrence en cours garde son vrai début."""
    try:
        timings = json.loads(timings_json or "[]")
    except ValueError:
        return []
    occ = []
    for t in timings:
        try:
            debut = datetime.fromisoformat(t["begin"])
            fin = datetime.fromisoformat(t["end"])
        except (KeyError, ValueError):
            continue
        if fin >= maintenant and debut <= limite:
            occ.append((debut, fin))
    occ.sort()
    return [[d.isoformat(), f.isoformat()] for d, f in occ[:40]]


# ------------------------------------------------------------------ #
# Collecte                                                             #
# ------------------------------------------------------------------ #

CHAMPS = ("uid,title_fr,description_fr,conditions_fr,keywords_fr,image,imagecredits,"
          "firstdate_begin,lastdate_end,timings,location_name,location_address,location_city,"
          "location_coordinates,location_access_fr,canonicalurl,age_max,status")


def evenements_ville(ville, lat, lon, jours, maintenant):
    where = (f"within_distance(location_coordinates, geom'POINT({lon} {lat})', {RAYON_KM}km) "
             f"and lastdate_end>=now() and firstdate_begin<=now(days={jours})")
    bruts = []
    for page in range(PAGES_MAX):
        params = urllib.parse.urlencode({"where": where, "select": CHAMPS, "limit": 100,
                                         "offset": page * 100, "order_by": "lastdate_end"})
        lot = http_json(f"{OPENAGENDA}?{params}")["results"]
        bruts += lot
        if len(lot) < 100:
            break

    limite = maintenant + timedelta(days=jours)
    retenus = []
    for e in bruts:
        titre = (e.get("title_fr") or "").strip()
        desc = (e.get("description_fr") or "").strip()
        texte = f"{titre} {desc} {' '.join(e.get('keywords_fr') or [])}"
        if (not titre or re.search(EXCLUSIONS, texte.lower()) or "Annul" in (e.get("status") or "")
                or (e.get("age_max") or 99) <= 14):
            continue
        c = e.get("location_coordinates") or {}
        if not c.get("lat"):
            continue
        categorie = categoriser(texte)
        occ = occurrences_futures(e.get("timings"), maintenant, limite)
        if not categorie or not occ:
            continue  # strict : jamais d'événement sans occurrence future
        fin = datetime.fromisoformat(e["lastdate_end"]).astimezone(PARIS)
        premiere = max(datetime.fromisoformat(occ[0][0]), maintenant).astimezone(PARIS)
        prix, libelle = tarif(e.get("conditions_fr"))
        retenus.append({
            "id": f"oa-{e['uid']}",
            "titre": titre,
            "description": desc or None,
            "categorie": categorie,
            "genres": genres_pour(categorie, texte),
            "ville": e.get("location_city"),
            "ville_reference": ville,
            "lieu": e.get("location_name"),
            "adresse": e.get("location_address"),
            "lat": c["lat"],
            "lon": c["lon"],
            "acces": e.get("location_access_fr"),
            "prix": prix,
            "tarif": libelle,
            "date_debut": premiere.date().isoformat(),
            "date_fin": fin.date().isoformat(),
            "occurrences": occ,
            "image": e.get("image"),
            "credit_image": e.get("imagecredits"),
            "url": e.get("canonicalurl"),
        })
    return retenus, len(bruts)


def selection(evenements, quota):
    """Quota réparti à tour de rôle entre catégories ; photo et date proche d'abord ; sans doublon de titre."""
    par_cat, titres = defaultdict(list), set()
    for ev in sorted(evenements, key=lambda x: (x["image"] is None, x["occurrences"][0][0])):
        cle = ev["titre"].lower()
        if cle not in titres:
            titres.add(cle)
            par_cat[ev["categorie"]].append(ev)
    pris = []
    while len(pris) < quota and any(par_cat.values()):
        for cat in CATEGORIES:
            if par_cat[cat] and len(pris) < quota:
                pris.append(par_cat[cat].pop(0))
    return pris


def main():
    parser = argparse.ArgumentParser(description="Événements culturels à venir en France (OpenAgenda)")
    parser.add_argument("--jours", type=int, default=35, help="horizon de collecte (>= 30 pour le filtre « mois »)")
    args = parser.parse_args()
    maintenant = datetime.now(timezone.utc)

    tous, vus = [], set()
    try:
        for ville, (lat0, lon0, quota) in VILLES.items():
            lat, lon = geocoder(ville, (lat0, lon0))
            evs, n_bruts = evenements_ville(ville, lat, lon, args.jours, maintenant)
            evs = [e for e in evs if e["id"] not in vus]  # zones qui se chevauchent
            pris = selection(evs, quota)
            vus.update(e["id"] for e in pris)
            tous += pris
            print(f"  {ville:17s} {n_bruts:4d} bruts -> {len(evs):4d} valides -> {len(pris):3d} retenus")
            time.sleep(0.3)
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as e:
        if SORTIE.exists():
            print(f"Source injoignable ({e}) : on garde {SORTIE.name} existant.")
            sys.exit(0)
        sys.exit(f"Source injoignable ({e}) et aucun fichier de repli.")

    SORTIE.write_text(json.dumps({
        "genere_le": maintenant.isoformat(timespec="seconds"),
        "horizon_jours": args.jours,
        "source": "OpenAgenda via Opendatasoft (evenements-publics-openagenda)",
        "categories": CATEGORIES,
        "villes": {v: geocoder(v, (la, lo)) for v, (la, lo, _) in VILLES.items()},
        "sorties": tous,
    }, ensure_ascii=False), encoding="utf-8")
    par_cat = defaultdict(int)
    for s in tous:
        par_cat[s["categorie"]] += 1
    print(f"Écrit {len(tous)} sorties dans {SORTIE} : {dict(par_cat)} ; "
          f"{sum(1 for s in tous if s['image'])} avec photo")


if __name__ == "__main__":
    main()
