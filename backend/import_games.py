"""
Import et francisation des jeux vidéo (hors ligne).

Entrée : export Wikidata en CSV (Game, Game_ID, Type, Release_Date, Release_Year, Series, Platforms,
         Genres, Developer, Publisher, Game_Modes, Game_URL) ; listes séparées par « ; ».
Sortie : backend/data/jeux.json (versionné).

1. Filtre : Type == "video game", Release_Year >= 2015, et Game, Platforms, Genres, Developer,
   Publisher, Game_URL renseignés (~3 300 jeux).
2. Francisation : plateformes regroupées (PC, Mac, PlayStation, Xbox, Nintendo Switch, Mobile),
   genres et modes de jeu traduits par règles. Un genre sans traduction est IGNORÉ : aucun tag
   anglais ne doit apparaître dans l'interface.
3. Titre français, résumé français et jaquette, sans clé, par lots (équivalent groupé de l'API REST
   page/summary, que Wikimedia limiterait à ~100 appels sans contact) :
     - Wikidata wbgetentities (50 jeux / requête) : libellé FR, articles fr et en ;
     - fr.wikipedia : extrait d'introduction (2 phrases) ;
     - en.wikipedia (repli) : image principale de l'article = jaquette (pilicense=any).
   Reprise possible (cache) ; arrêt propre si Wikimedia limite le débit (définir ENNUI_CONTACT
   pour un débit normal, voir enrich_affiches.py).

Usage :
    python3 backend/import_games.py --csv ~/Downloads/video_games.csv
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

SORTIE = Path(__file__).resolve().parent / "data" / "jeux.json"
CONTACT = os.environ.get("ENNUI_CONTACT", "").strip()
UA = f"hackathon-ennui/0.1 ({CONTACT})" if CONTACT else "hackathon-ennui/0.1 (projet etudiant)"
PAUSE = 0.5 if CONTACT else 2.0
ANNEE_MIN = 2015
GENRES_EXCLUS = r"eroge|bish[oō]jo|hentai|adult video game|pornograph"  # appli étudiante : contenu adulte exclu

# ------------------------------------------------------------------ #
# Francisation                                                         #
# ------------------------------------------------------------------ #

CONSOLES = {  # id -> libellé affiché
    "pc": "PC (Windows)", "mac": "Mac", "playstation": "PlayStation",
    "xbox": "Xbox", "switch": "Nintendo Switch", "mobile": "Mobile (iOS/Android)",
}
REGLES_CONSOLES = [
    (r"^(microsoft windows|personal computer|pc|computer|steam|universal windows platform|linux|steamos)$", "pc"),
    (r"^(macos|mac|classic mac os|mac operating system)$", "mac"),
    (r"^playstation", "playstation"),
    (r"^xbox", "xbox"),
    (r"^nintendo switch", "switch"),
    (r"^(ios|ipados|android|mobile phone|fire os|harmonyos)", "mobile"),
]

# (motif sur le genre anglais, libellé français, genres de l'application pour le graphe).
# L'ordre compte : le premier motif qui correspond l'emporte (du plus spécifique au plus général).
REGLES_GENRES = [
    (r"massively multiplayer online role", "MMORPG", ["Fantasy", "Adventure"]),
    (r"massively multiplayer|multiplayer online battle arena", "Multijoueur en ligne", ["Action"]),
    (r"soulslike|dungeon crawl", "Action-RPG", ["Action", "Fantasy"]),
    (r"real-time tactics", "Tactique en temps réel", ["War"]),
    (r"vehicular combat", "Combat de véhicules", ["Action"]),
    (r"bullet hell", "Tir", ["Action"]),
    (r"otome", "Roman visuel", ["Romance", "Drama"]),
    (r"board video game|board game", "Jeu de société", ["Comedy"]),
    (r"endless runner", "Détente", ["Comedy"]),
    (r"art game", "Narratif", ["Drama"]),
    (r"historical", "Historique", ["Documentary", "War"]),
    (r"side-scroll", "Plateforme", ["Adventure", "Children"]),
    (r"^arcade", "Arcade", ["Action"]),
    (r"tactical role|strategy role", "RPG tactique", ["War", "Fantasy"]),
    (r"action role", "Action-RPG", ["Action", "Fantasy"]),
    (r"role-playing|\brpg\b", "RPG", ["Fantasy", "Adventure"]),
    (r"first-person shooter", "Tir à la première personne", ["Action", "Thriller"]),
    (r"third-person shooter", "Tir à la troisième personne", ["Action", "Thriller"]),
    (r"shoot 'em up|shooter|shooting", "Tir", ["Action"]),
    (r"battle royale", "Battle royale", ["Action", "Thriller"]),
    (r"real-time strategy", "Stratégie en temps réel", ["War"]),
    (r"turn-based (strategy|tactics)", "Stratégie au tour par tour", ["War"]),
    (r"tower defense", "Défense de tours", ["War"]),
    (r"4x|grand strategy|strategy", "Stratégie", ["War"]),
    (r"city-building|business simulation|management|tycoon|construction", "Gestion", ["Documentary"]),
    (r"life simulation|social simulation", "Simulation de vie", ["Comedy", "Drama"]),
    (r"dating sim", "Romance", ["Romance"]),
    (r"farming|vehicle simulation|flight simulat|simulation", "Simulation", ["Documentary"]),
    (r"survival horror", "Survival horror", ["Horror", "Thriller"]),
    (r"horror", "Horreur", ["Horror"]),
    (r"survival", "Survie", ["Thriller", "Adventure"]),
    (r"metroidvania", "Metroidvania", ["Action", "Adventure"]),
    (r"rogue", "Roguelike", ["Action", "Fantasy"]),
    (r"hack and slash|beat 'em up|fighting|brawler", "Combat", ["Action"]),
    (r"stealth", "Infiltration", ["Thriller"]),
    (r"platform", "Plateforme", ["Adventure", "Children"]),
    (r"racing|driving|kart", "Course", ["Action"]),
    (r"sports|football|soccer|basketball|golf|tennis|fitness|skateboard|baseball|hockey|wrestling|boxing", "Sport", ["Action"]),
    (r"rhythm|music video game|dance", "Rythme", ["Musical"]),
    (r"visual novel", "Roman visuel", ["Romance", "Drama"]),
    (r"interactive (film|movie|fiction)|walking simulator|narrative", "Narratif", ["Drama"]),
    (r"point-and-click|graphic adventure|text adventure", "Point & click", ["Mystery", "Adventure"]),
    (r"detective|mystery|investigation", "Enquête", ["Mystery", "Crime"]),
    (r"puzzle|logic", "Réflexion", ["Mystery"]),
    (r"party|social deduction", "Jeu d'ambiance", ["Comedy"]),
    (r"card|deck-building|collectible", "Cartes", ["Fantasy"]),
    (r"casual|idle|clicker|cozy", "Détente", ["Comedy"]),
    (r"sandbox|open world", "Monde ouvert", ["Adventure"]),
    (r"educational", "Éducatif", ["Documentary", "Children"]),
    (r"cyberpunk", "Cyberpunk", ["Sci-Fi"]),
    (r"post-apocalyptic", "Post-apocalyptique", ["Sci-Fi", "Thriller"]),
    (r"science fiction|space", "Science-fiction", ["Sci-Fi"]),
    (r"fantasy", "Fantasy", ["Fantasy"]),
    (r"war game|military|world war", "Guerre", ["War"]),
    (r"western", "Western", ["Western"]),
    (r"comedy|humor", "Humour", ["Comedy"]),
    (r"action-adventure", "Action-aventure", ["Action", "Adventure"]),
    (r"adventure", "Aventure", ["Adventure"]),
    (r"action", "Action", ["Action"]),
]

MODES = [  # (motif, mode)
    (r"single-player", "solo"),
    (r"co-op|cooperative|versus environment", "coop"),
    (r"multiplay|versus player|online game|deathmatch|two-player|hotseat|lan", "multi"),
]
LIBELLES_MODES = {"solo": "Solo", "coop": "Co-op", "multi": "Multijoueur"}


def liste(texte) -> list:
    if not isinstance(texte, str) or texte.strip() in ("", "NA"):
        return []
    return [x.strip() for x in texte.split(";") if x.strip()]


def consoles(texte) -> list:
    ids = []
    for p in liste(texte):
        for motif, cid in REGLES_CONSOLES:
            if re.search(motif, p.lower()) and cid not in ids:
                ids.append(cid)
                break
    return [c for c in CONSOLES if c in ids]  # ordre fixe


def genres(texte):
    """-> (libellés français, max 3 ; genres de l'application pour le graphe, max 3)."""
    fr, graphe = [], []
    for g in liste(texte):
        for motif, libelle, gg in REGLES_GENRES:
            if re.search(motif, g.lower()):
                if libelle not in fr:
                    fr.append(libelle)
                graphe += [x for x in gg if x not in graphe]
                break
    return fr[:3], graphe[:3] or ["Adventure"]


def modes(texte) -> list:
    out = []
    for m in liste(texte):
        for motif, mode in MODES:
            if re.search(motif, m.lower()) and mode not in out:
                out.append(mode)
                break
    return out or ["solo"]


# ------------------------------------------------------------------ #
# Wikidata / Wikipédia                                                 #
# ------------------------------------------------------------------ #

class Bloque(Exception):
    pass


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
        except (urllib.error.URLError, TimeoutError, OSError):  # socket.timeout (Python 3.9) inclus
            time.sleep(10)
    raise RuntimeError(url)


def sans_suffixe(titre):
    """« Hades (jeu vidéo) » -> « Hades »."""
    return re.sub(r"\s*\((jeu vidéo|jeu|video game)[^)]*\)\s*$", "", titre).strip()


def premieres_phrases(texte, n=2, maxi=320):
    if not texte:
        return None
    phrases = re.split(r"(?<=[.!?])\s+", texte.strip())
    r = " ".join(phrases[:n]).strip()
    return (r[:maxi].rsplit(" ", 1)[0] + "…") if len(r) > maxi else r or None


def verifier(reponse):
    if "query" not in reponse and "entities" not in reponse:  # réponse d'erreur : lot repris plus tard
        raise RuntimeError(json.dumps(reponse.get("error", reponse))[:200])
    return reponse


def alias_titres(reponse):
    q = verifier(reponse).get("query", {})
    return {x["from"]: x["to"] for x in q.get("normalized", []) + q.get("redirects", [])}


def enrichir_lot(jeux):
    """Complète en place titre_fr, resume, jaquette pour un lot (<= 50 jeux)."""
    r = get("https://www.wikidata.org/w/api.php", {
        "action": "wbgetentities", "ids": "|".join(j["wikidata"] for j in jeux), "props": "labels|sitelinks",
        "languages": "fr", "sitefilter": "frwiki|enwiki", "format": "json"})
    ent = verifier(r).get("entities", {})
    for j in jeux:
        e = ent.get(j["wikidata"], {})
        sl = e.get("sitelinks", {})
        j["_fr"] = sl.get("frwiki", {}).get("title")
        j["_en"] = sl.get("enwiki", {}).get("title") or urllib.parse.unquote(j["url"].rsplit("/", 1)[-1]).replace("_", " ")
        j["titre"] = sans_suffixe(j["_fr"]) if j["_fr"] else (e.get("labels", {}).get("fr", {}).get("value") or j["titre_original"])

    # résumés français (20 extraits max par requête)
    avec_fr = [j for j in jeux if j["_fr"]]
    for i in range(0, len(avec_fr), 20):
        lot = avec_fr[i:i + 20]
        r = get("https://fr.wikipedia.org/w/api.php", {
            "action": "query", "titles": "|".join(j["_fr"] for j in lot), "prop": "extracts",
            "exintro": 1, "explaintext": 1, "exlimit": 20, "redirects": 1, "format": "json"})
        alias = alias_titres(r)
        textes = {p["title"]: p.get("extract") for p in r["query"]["pages"].values()}
        for j in lot:
            cible = alias.get(alias.get(j["_fr"], j["_fr"]), alias.get(j["_fr"], j["_fr"]))
            j["resume"] = premieres_phrases(textes.get(cible))

    # jaquettes : image principale de l'article anglais (non libre, hébergée par en.wikipedia)
    r = get("https://en.wikipedia.org/w/api.php", {
        "action": "query", "titles": "|".join(j["_en"] for j in jeux), "prop": "pageimages",
        "piprop": "original", "pilicense": "any", "redirects": 1, "format": "json"})
    alias = alias_titres(r)
    images = {p["title"]: p["original"]["source"].split("?")[0]
              for p in r["query"]["pages"].values() if p.get("original")}
    for j in jeux:
        cible = alias.get(alias.get(j["_en"], j["_en"]), alias.get(j["_en"], j["_en"]))
        img = images.get(cible)
        nom = urllib.parse.unquote(img.rsplit("/", 1)[-1]) if img else ""
        logo = re.search(r"(^|[_\W])(logo|wordmark|title|icon|banner)([_\W]|$)", nom, re.I)
        j["jaquette"] = img if img and re.search(r"\.(jpe?g|png|webp)$", img, re.I) and not logo else None
        j["enrichi"] = True
        del j["_fr"], j["_en"]


def main():
    parser = argparse.ArgumentParser(description="Import et francisation des jeux vidéo")
    parser.add_argument("--csv", type=Path, required=True)
    args = parser.parse_args()

    df = pd.read_csv(args.csv, low_memory=False, encoding="utf-8-sig")
    df["Release_Year"] = pd.to_numeric(df["Release_Year"], errors="coerce")
    df = df[(df["Type"] == "video game") & (df["Release_Year"] >= ANNEE_MIN)]
    df = df.dropna(subset=["Game", "Platforms", "Genres", "Developer", "Publisher", "Game_URL"])
    df = df.drop_duplicates("Game_ID")
    adultes = df["Genres"].str.lower().str.contains(GENRES_EXCLUS, regex=True)
    df = df[~adultes]
    print(f"Retenus : {len(df)} jeux (vidéo, {ANNEE_MIN}+, fiches complètes ; {int(adultes.sum())} jeux adultes exclus)")

    cache = {}
    if SORTIE.exists():
        cache = {j["wikidata"]: j for j in json.loads(SORTIE.read_text(encoding="utf-8"))["jeux"]}

    jeux = []
    for r in df.itertuples():
        if r.Game_ID in cache:
            jeux.append(cache[r.Game_ID])
            continue
        fr, graphe = genres(r.Genres)
        jeux.append({
            "id": r.Game_ID, "wikidata": r.Game_ID, "url": r.Game_URL,
            "titre_original": r.Game.strip(), "titre": r.Game.strip(),
            "annee": int(r.Release_Year), "date_sortie": str(r.Release_Date)[:10],
            "consoles": consoles(r.Platforms),
            "genres_fr": fr, "genres": graphe,
            "modes": modes(r.Game_Modes),
            "studio": liste(r.Developer)[0], "editeur": liste(r.Publisher)[0],
            "serie": r.Series if isinstance(r.Series, str) and r.Series != "NA" else None,
            "resume": None, "jaquette": None, "enrichi": False,
        })

    a_faire = [j for j in jeux if not j["enrichi"]]
    print(f"Enrichissement FR (Wikidata + Wikipédia) : {len(a_faire)} jeux à traiter")
    for i in range(0, len(a_faire), 50):
        try:
            enrichir_lot(a_faire[i:i + 50])
        except Bloque:
            print("Wikimedia limite le débit (429) : arrêt propre, relancer plus tard (ou définir ENNUI_CONTACT).")
            break
        except RuntimeError as e:
            print(f"  lot {i} ignoré ({e})")
        if (i // 50) % 5 == 0:
            SORTIE.write_text(json.dumps({"jeux": jeux}, ensure_ascii=False), encoding="utf-8")
            print(f"  {min(i + 50, len(a_faire))}/{len(a_faire)}", flush=True)

    SORTIE.write_text(json.dumps({
        "source": "Wikidata (CSV local) + Wikipédia FR/EN", "consoles": CONSOLES, "modes": LIBELLES_MODES,
        "jeux": jeux}, ensure_ascii=False), encoding="utf-8")
    n = len(jeux)
    print(f"Écrit {n} jeux : {sum(1 for j in jeux if j['titre'] != j['titre_original'])} titres FR différents, "
          f"{sum(1 for j in jeux if j['resume'])} résumés FR, {sum(1 for j in jeux if j['jaquette'])} jaquettes, "
          f"{sum(1 for j in jeux if not j['genres_fr'])} sans genre traduit")


if __name__ == "__main__":
    main()
