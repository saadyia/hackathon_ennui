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
import math
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
    "soirees": "Soirées & Concerts",
    "cinema": "Cinéma",
    "expo": "Expositions & Musées",
    "scene": "Spectacles & Scène",
    "nature": "Nature & Balades",
    "rencontres": "Rencontres & Ateliers",
    "jeux": "Jeux vidéo (solo ou coop)",
    "cuisine": "Cuisine & pâtisserie",
    "creatif": "Créatif",
    "lecture": "Lecture",
    "cafe": "Café & salon de thé",
    "sport": "Sport chill",
}
QUOTA_SOIREES = 25  # soirées & concerts supplémentaires par ville (requête nocturne dédiée)
MOTS_NOCTURNES = ["concert", "soirée", "DJ", "festival", "club", "fête", "live", "étudiant",
                  "électro", "karaoké", "afterwork", "open mic", "blind test"]

MOTS_CATEGORIE = {
    "soirees": r"concert|soir[ée]e|\bdj\b|dj set|club|clubbing|[ée]lectro|festival|\blive\b|f[êe]te|karaok[ée]|"
               r"afterwork|open mic|blind test|\bbal\b|jazz|rock|\brap\b|hip[- ]hop|chanson|musique",
    "cinema": r"cin[ée]ma|cin[ée]-|projection|court[- ]m[ée]trage|long[- ]m[ée]trage|\bfilms?\b|cin[ée]club",
    "scene": r"spectacle|th[ée][aâ]tre|danse|op[ée]ra|cirque|humour|stand[- ]up|chorale|r[ée]cital|orchestre|"
             r"marionnette|com[ée]die musicale|one[- ]man",
    "expo": r"exposition|\bexpo\b|mus[ée]e|vernissage|galerie|visite guid[ée]e|patrimoine|photograph|peinture|"
            r"sculpture|\bart\b|arts plastiques",
    "nature": r"balade|randonn[ée]e|\brando\b|nature|jardin|marais|for[êe]t|littoral|oiseaux|botanique|"
              r"\bv[ée]lo\b|sentier|plage|estran|\bparcs?\b|plein air|trail|kayak|cano[ëe]|paddle|"
              r"espaces? naturels?|r[ée]serve naturelle|cueillette|astronomie|nuit des [ée]toiles",
    "rencontres": r"conf[ée]rence|rencontre|d[ée]bat|atelier|quiz|\bjeux?\b|"
                  r"ap[ée]ro|discussion|table ronde",
    "jeux": r"jeux? vid[ée]o|gaming|gamers?\b|e-?sport|r[ée]tro-?gaming|\blan party\b|consoles?\b|"
            r"nintendo|playstation|\bxbox\b|minecraft|mario kart",
    "cuisine": r"cuisine|culinaire|p[âa]tisserie|p[âa]tissier|recettes?\b|d[ée]gustation|gastronom|"
               r"chef cuisinier|boulangerie|fabrication du pain|chocolat|\bbrunch\b",
    "creatif": r"atelier cr[ée]atif|loisirs cr[ée]atifs|cr[ée]ation manuelle|\bdiy\b|fait main|couture|poterie|"
               r"c[ée]ramique|tricot|broderie|crochet|origami|gravure|s[ée]rigraphie|scrapbooking|upcycling|"
               r"customis|modelage|aquarelle|atelier (de )?(dessin|peinture|collage|[ée]criture)",
    # « livre » seul est exclu (« il livre un concert »), comme « auteur-compositeur »
    "lecture": r"lecture|\blivres\b|\b(un|le|son|leur|du) livre\b|auteur(?!-compositeur)|autrice(?!-compositrice)|"
               r"[ée]crivain|biblioth[èe]que|m[ée]diath[èe]que|d[ée]dicace|po[ée]sie|po[èe]mes?\b|\bromans?\b|"
               r"librairie|salon du livre|club de lecture|litt[ée]ra",
    # « café » seul désigne souvent une salle de concert : seulement les formats café explicites
    "cafe": r"salon de th[ée]|coffee shop|torr[ée]fact|barista|tea[- ]time|d[ée]gustation de (caf[ée]|th[ée])|"
            r"caf[ée][- ](philo|des langues|langues|litt[ée]raire|tricot|couture|r[ée]paration|jeux|lecture|"
            r"psycho|histoire|sciences?|d[ée]bat|rencontre|discussion|cr[ée]atif)",
    "sport": r"yoga|pilates|m[ée]ditation|tai[- ]chi|qi[- ]?gong|sophrologie|stretching|marche nordique|"
             r"\bsports?\b|sportive|escalade|natation|course [àa] pied|running|footing|badminton|ping[- ]pong|"
             r"p[ée]tanque|roller|skate|zumba|fitness|gym douce",
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

# Ambiances (transversales) : repérées dans le texte, plus une valeur par défaut selon la catégorie.
MOTS_AMBIANCE = {
    "calme": r"yoga|m[ée]ditation|relaxation|sophrologie|\bzen\b|calme|d[ée]tente|contemplat|bien-[êe]tre|"
             r"douceur|apaisant|s[ée]r[ée]nit|sieste|tisane|salon de th[ée]",
    "insolite": r"insolite|[ée]trange|surprenant|surprise|myst[èe]re|secret|escape|cach[ée]s?\b|in[ée]dit|"
                r"nocturne|bizarre|curiosit[ée]s?\b|immersi|enqu[êe]te|murder|[ée]nigme|d[ée]cal[ée]",
    "drole": r"humour|com[ée]die|\brire\b|impro|stand[- ]up|dr[ôo]le|burlesque|clown|karaok[ée]|"
             r"blind test|loufoque",
    "festif": r"\bdj\b|dj set|clubbing|\bclub\b|bo[îi]te de nuit|nightclub|\btechno\b|\bhouse\b|[ée]lectro|"
              r"dancefloor|\brave\b|\bparty\b|soir[ée]e dansante|\bf[êe]te\b|festif|festive|\bbal\b|"
              r"after\b|open air|warehouse|guinguette|disco|ambiance de folie",
    "competitif": r"tournoi|comp[ée]tition|concours|d[ée]fi|challenge|quiz|blind test|battle|championnat|"
                  r"\bmatch|troph[ée]e|e-?sport|escape game",
    "artistique": r"\bart\b|\barts\b|artiste|peinture|sculpture|photograph|dessin|cr[ée]ation|po[ée]sie|"
                  r"vernissage|th[ée][aâ]tre|chor[ée]graph|illustration|street art|graff|design|[ée]criture",
}
AMBIANCES_CATEGORIE = {"nature": ["calme"], "lecture": ["calme"], "cafe": ["calme"],
                       "expo": ["artistique"], "creatif": ["artistique"]}

GENRES_CATEGORIE = {
    "culture": ["Documentary", "Drama"],   # sorties publiées par les utilisateurs (catégorie regroupée)
    "soirees": ["Musical", "Comedy"],
    "cinema": ["Drama"],
    "expo": ["Documentary", "Drama"],
    "scene": ["Drama", "Comedy"],
    "nature": ["Documentary", "Adventure"],
    "rencontres": ["Documentary", "Comedy"],
    "jeux": ["Action", "Adventure"],
    "cuisine": ["Documentary", "Comedy"],
    "creatif": ["Documentary", "Animation"],
    "lecture": ["Drama", "Documentary"],
    "cafe": ["Comedy", "Documentary"],
    "sport": ["Adventure", "Documentary"],
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


# Affinage vers les trois sous-catégories de l'onglet Sorties (culture, soirées, nature) : on rattache les
# « rencontres » et le « sport » quand le texte le dit clairement ; le reste garde sa catégorie (non proposée).
AFFINAGE = [
    ("rencontres", r"conf[ée]rence|d[ée]bat|table ronde|visite|patrimoine|histoire|arch[ée]o|science|astronom|"
                   r"projection|philo|mus[ée]e|exposition|lecture", "culture"),
    ("rencontres", r"ap[ée]ro|quiz|blind test|soir[ée]e|karaok[ée]|afterwork|bar\b|danse", "soirees"),
    ("sport", r"plein air|ext[ée]rieur|randonn|\brando|marche nordique|trail|course nature|v[ée]lo|kayak|cano[ëe]|"
              r"paddle|parc\b|jardin|for[êe]t|plage|\bnature\b", "nature"),
    ("rencontres", r"plein air|randonn|balade|\bnature\b|jardin|for[êe]t|sortie nature|observation", "nature"),
]


def affiner(categorie, texte: str, titre: str = ""):
    """Nature : seulement si le titre le dit (une description cite vite un jardin ou une forêt au passage)."""
    if not categorie:
        return categorie
    for source, motif, cible in AFFINAGE:
        t = (titre if cible == "nature" and titre else texte).lower()
        if categorie == source and re.search(motif, t):
            return cible
    return categorie


def genres_pour(categorie: str, texte: str):
    t = texte.lower()
    genres = list(GENRES_CATEGORIE[categorie])
    for motif, gs in MOTS_GENRES:
        if re.search(motif, t):
            genres += [g for g in gs if g not in genres]
    return genres[:3]


def ambiances_pour(categorie: str, texte: str):
    """Ambiances écrites dans le texte (mots-clés), plus celle qui va de soi pour la catégorie."""
    t = texte.lower()
    ambiances = list(AMBIANCES_CATEGORIE.get(categorie, []))
    ambiances += [a for a, motif in MOTS_AMBIANCE.items() if a not in ambiances and re.search(motif, t)]
    return ambiances


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


def texte_long(html, maxi=1200):
    """Description longue OpenAgenda (HTML) -> texte brut, paragraphes conservés, coupé à la phrase."""
    if not html:
        return None
    t = re.sub(r"<\s*(br|/p|/li|/h\d)\s*/?>", "\n", html, flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)
    for ent, car in (("&nbsp;", " "), ("&amp;", "&"), ("&quot;", '"'), ("&#39;", "'"), ("&lt;", "<"), ("&gt;", ">")):
        t = t.replace(ent, car)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n\n", t).strip()
    if len(t) > maxi:
        coupe = t[:maxi]
        fin = max(coupe.rfind(". "), coupe.rfind(".\n"))
        t = coupe[:fin + 1] if fin > 300 else coupe.rsplit(" ", 1)[0] + "…"
    return t or None


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

CHAMPS = ("uid,title_fr,description_fr,longdescription_fr,conditions_fr,keywords_fr,image,imagecredits,"
          "firstdate_begin,lastdate_end,timings,location_name,location_address,location_city,"
          "location_coordinates,location_access_fr,canonicalurl,age_max,status,registration")


# ------------------------------------------------------------------ #
# Billetterie : uniquement ce que l'organisateur a publié              #
# ------------------------------------------------------------------ #
LIBRE = re.compile(r"entr[ée]e\s+libre|acc[eè]s\s+libre|libre\s+acc[eè]s|entr[ée]e\s+gratuite\s+sans|sans\s+r[ée]servation|sans\s+inscription")
RESERVATION = re.compile(r"r[ée]servation|r[ée]server|sur\s+inscription|inscription\s+(obligatoire|conseill[ée]e|requise|gratuite|pr[ée]alable)"
                         r"|billetterie|places?\s+limit[ée]es|nombre\s+de\s+places")


def _json(valeur):
    if isinstance(valeur, str):
        try:
            return json.loads(valeur)
        except ValueError:
            return None
    return valeur


def billetterie(e: dict):
    """(etat, url, tel) avec etat = « complet » (statut OpenAgenda 5), « libre » (conditions explicites),
    « reservation » (lien ou contact d'inscription publié, ou conditions qui le disent), sinon None.
    Rien n'est déduit du prix : un événement gratuit peut être sur réservation."""
    statut = _json(e.get("status")) or {}
    inscription = _json(e.get("registration")) or []
    url = next((r.get("value") for r in inscription if isinstance(r, dict) and r.get("type") == "link"
                and str(r.get("value", "")).startswith("https://")), None)
    tel = next((r.get("value") for r in inscription if isinstance(r, dict) and r.get("type") == "phone"), None)
    conditions = (e.get("conditions_fr") or "").lower()
    if isinstance(statut, dict) and statut.get("id") == 5:
        etat = "complet"
    elif LIBRE.search(conditions) and not re.search(r"r[ée]servation\s+(obligatoire|indispensable|requise)", conditions):
        etat = "libre"
    elif url or tel or RESERVATION.search(conditions):
        etat = "reservation"
    else:
        etat = None
    return etat, url, (str(tel)[:30] if tel else None)


def evenements_ville(ville, lat, lon, jours, maintenant):
    base = (f"within_distance(location_coordinates, geom'POINT({lon} {lat})', {RAYON_KM}km) "
            f"and lastdate_end>=now() and firstdate_begin<=now(days={jours})")
    nocturne = " or ".join(f'search(title_fr, "{m}") or search(keywords_fr, "{m}")' for m in MOTS_NOCTURNES)
    requetes = [(base, PAGES_MAX), (f"{base} and ({nocturne})", 1)]  # générale + soirées / concerts
    bruts, uids = [], set()
    for where, pages in requetes:
        for page in range(pages):
            params = urllib.parse.urlencode({"where": where, "select": CHAMPS, "limit": 100,
                                             "offset": page * 100, "order_by": "lastdate_end"})
            lot = http_json(f"{OPENAGENDA}?{params}")["results"]
            bruts += [e for e in lot if e["uid"] not in uids]
            uids.update(e["uid"] for e in lot)
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
        categorie = affiner(categoriser(texte), texte, titre)
        occ = occurrences_futures(e.get("timings"), maintenant, limite)
        if not categorie or not occ:
            continue  # strict : jamais d'événement sans occurrence future
        fin = datetime.fromisoformat(e["lastdate_end"]).astimezone(PARIS)
        premiere = max(datetime.fromisoformat(occ[0][0]), maintenant).astimezone(PARIS)
        prix, libelle = tarif(e.get("conditions_fr"))
        billet, url_resa, tel_resa = billetterie(e)
        retenus.append({
            "id": f"oa-{e['uid']}",
            "titre": titre,
            "description": desc or None,
            "description_longue": texte_long(e.get("longdescription_fr")),
            "categorie": categorie,
            "genres": genres_pour(categorie, texte),
            "ambiances": ambiances_pour(categorie, texte),
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
            "conditions": (e.get("conditions_fr") or "").strip()[:300] or None,  # aussi pour prix_num (build_graph)
            "billetterie": billet,          # complet | libre | reservation | None
            "reservation_url": url_resa,    # lien publié par l'organisateur (https uniquement)
            "reservation_tel": tel_resa,
        })
    return retenus, len(bruts)


def selection(evenements, quota):
    """Quota réparti à tour de rôle entre catégories ; photo et date proche d'abord ; sans doublon de titre.
    Les soirées & concerts ont en plus leur propre quota (QUOTA_SOIREES)."""
    par_cat, titres = defaultdict(list), set()
    for ev in sorted(evenements, key=lambda x: (x["image"] is None, x["occurrences"][0][0])):
        cle = ev["titre"].lower()
        if cle not in titres:
            titres.add(cle)
            par_cat[ev["categorie"]].append(ev)
    pris = par_cat["soirees"][:QUOTA_SOIREES]
    par_cat["soirees"] = par_cat["soirees"][QUOTA_SOIREES:]
    limite = quota + len(pris)
    while len(pris) < limite and any(par_cat.values()):
        for cat in CATEGORIES:
            if par_cat[cat] and len(pris) < limite:
                pris.append(par_cat[cat].pop(0))
    return pris


def couverte(lat: float, lon: float, villes: dict, rayon_km: float = 20.0) -> bool:
    """Vrai si un point est à moins de rayon_km d'une ville déjà collectée."""
    p = math.pi / 180
    for la, lo in villes.values():
        a = math.sin((la - lat) * p / 2) ** 2 + math.cos(lat * p) * math.cos(la * p) * math.sin((lo - lon) * p / 2) ** 2
        if 12742 * math.asin(math.sqrt(a)) <= rayon_km:
            return True
    return False


def collecter(jours: int = 35, journal=print, villes_utilisateurs: dict = None, seulement: bool = False) -> dict:
    """
    Interroge OpenAgenda pour toutes les villes universitaires, plus les villes des utilisateurs
    qui n'en sont pas proches (villes_utilisateurs : {nom: [lat, lon]}). Lève une exception réseau
    en cas d'échec.
    """
    maintenant = datetime.now(timezone.utc)
    tous, vus, villes = [], set(), {}
    cibles = {} if seulement else {v: (la, lo, q, True) for v, (la, lo, q) in VILLES.items()}
    for v, (la, lo) in (villes_utilisateurs or {}).items():
        cibles.setdefault(v, (la, lo, 40, False))
    for ville, (lat0, lon0, quota, geocodable) in cibles.items():
        lat, lon = geocoder(ville, (lat0, lon0)) if geocodable else (lat0, lon0)
        villes[ville] = [lat, lon]
        evs, n_bruts = evenements_ville(ville, lat, lon, jours, maintenant)
        evs = [e for e in evs if e["id"] not in vus]  # zones qui se chevauchent
        pris = selection(evs, quota)
        vus.update(e["id"] for e in pris)
        tous += pris
        journal(f"  {ville:17s} {n_bruts:4d} bruts -> {len(evs):4d} valides -> {len(pris):3d} retenus")
        time.sleep(0.3)
    return {
        "genere_le": maintenant.isoformat(timespec="seconds"),
        "horizon_jours": jours,
        "source": "OpenAgenda via Opendatasoft (evenements-publics-openagenda)",
        "categories": CATEGORIES,
        "villes": villes,
        "sorties": tous,
    }


def retirer_passes(donnees: dict) -> int:
    """Supprime les occurrences terminées et les événements qui n'en ont plus. Renvoie le nb retiré."""
    maintenant = datetime.now(timezone.utc)
    gardes = []
    for s in donnees["sorties"]:
        s["occurrences"] = [o for o in s["occurrences"] if datetime.fromisoformat(o[1]) >= maintenant]
        if s["occurrences"]:
            s["date_debut"] = max(datetime.fromisoformat(s["occurrences"][0][0]), maintenant).astimezone(PARIS).date().isoformat()
            gardes.append(s)
    retires = len(donnees["sorties"]) - len(gardes)
    donnees["sorties"] = gardes
    return retires


def ecrire(donnees: dict):
    tmp = SORTIE.with_name(SORTIE.name + ".tmp")
    tmp.write_text(json.dumps(donnees, ensure_ascii=False), encoding="utf-8")
    tmp.replace(SORTIE)  # atomique : jamais de fichier à moitié écrit


def main():
    parser = argparse.ArgumentParser(description="Événements culturels à venir en France (OpenAgenda)")
    parser.add_argument("--jours", type=int, default=35, help="horizon de collecte (>= 30 pour le filtre « mois »)")
    args = parser.parse_args()
    try:
        donnees = collecter(args.jours)
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as e:
        if SORTIE.exists():
            print(f"Source injoignable ({e}) : on garde {SORTIE.name} existant.")
            sys.exit(0)
        sys.exit(f"Source injoignable ({e}) et aucun fichier de repli.")
    ecrire(donnees)
    par_cat = defaultdict(int)
    for s in donnees["sorties"]:
        par_cat[s["categorie"]] += 1
    print(f"Écrit {len(donnees['sorties'])} sorties dans {SORTIE} : {dict(par_cat)} ; "
          f"{sum(1 for s in donnees['sorties'] if s['image'])} avec photo")


if __name__ == "__main__":
    main()
