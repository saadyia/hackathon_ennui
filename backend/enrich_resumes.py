"""
Résumés EN FRANÇAIS pour la fiche détaillée (hors ligne, sans clé) : introduction de l'article
Wikipédia francophone de chaque œuvre.

  films  : identifiant Wikidata déjà connu (affiches.json) -> article fr.wikipedia -> introduction
  séries : identifiant IMDb (series.json) -> Wikidata (haswbstatement:P345) -> article fr -> introduction
  livres : livres dont l'édition française est connue (titre FR) -> article fr.wikipedia du même titre,
           retenu seulement si l'introduction cite le nom de l'auteur (évite les homonymes)

Aucun texte n'est traduit : une œuvre sans article français n'a pas de résumé (jamais d'anglais).
Par lots (Wikidata 50 / requête, extraits 20 / requête), lent exprès sans contact (Wikimedia
limite les scripts) ; reprise possible ; arrêt propre en cas de blocage. ENNUI_CONTACT accélère.

Sortie : backend/data/resumes.json {"films": {movieId: texte}, "series": {tvmazeId: texte}, "livres": {id: texte}}
Usage : python3 backend/enrich_resumes.py
"""

import json
import os
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DONNEES = Path(__file__).resolve().parent / "data"
SORTIE = DONNEES / "resumes.json"
CONTACT = os.environ.get("ENNUI_CONTACT", "").strip()
UA = f"hackathon-ennui/0.1 ({CONTACT})" if CONTACT else "hackathon-ennui/0.1 (projet etudiant)"
PAUSE = 0.5 if CONTACT else 2.0
LONGUEUR_MAX = 900  # caractères : l'introduction complète, coupée proprement à la phrase


class Bloque(Exception):
    pass


def get(url, params):
    u = url + "?" + urllib.parse.urlencode(params)
    for essai in range(3):
        time.sleep(PAUSE)
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=60) as r:
                d = json.load(r)
                if "error" in d:
                    raise RuntimeError(str(d["error"])[:200])
                return d
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
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(10)
    raise RuntimeError(url)


def couper(texte):
    if not texte:
        return None
    texte = re.sub(r"\s+", " ", texte).strip()
    if len(texte) <= LONGUEUR_MAX:
        return texte or None
    coupe = texte[:LONGUEUR_MAX]
    fin = max(coupe.rfind(". "), coupe.rfind("! "), coupe.rfind("? "))
    return (coupe[:fin + 1] if fin > 200 else coupe.rsplit(" ", 1)[0] + "…")


def sans_accents(t):
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


def articles_fr(qids):
    """{QID: titre de l'article fr.wikipedia} (50 par requête)."""
    out = {}
    for i in range(0, len(qids), 50):
        try:
            r = get("https://www.wikidata.org/w/api.php", {"action": "wbgetentities", "ids": "|".join(qids[i:i + 50]),
                                                           "props": "sitelinks", "sitefilter": "frwiki", "format": "json"})
        except RuntimeError:  # lot ignoré (réseau) : repris au prochain lancement
            continue
        for q, e in r.get("entities", {}).items():
            t = e.get("sitelinks", {}).get("frwiki", {}).get("title")
            if t:
                out[q] = t
    return out


def introductions(titres):
    """{titre demandé: introduction en texte brut} (20 par requête, redirections suivies)."""
    out = {}
    for i in range(0, len(titres), 20):
        lot = titres[i:i + 20]
        try:
            r = get("https://fr.wikipedia.org/w/api.php", {"action": "query", "titles": "|".join(lot), "prop": "extracts",
                                                          "exintro": 1, "explaintext": 1, "exlimit": 20, "redirects": 1,
                                                          "format": "json"})
        except RuntimeError:
            continue
        q = r.get("query", {})
        alias = {x["from"]: x["to"] for x in q.get("normalized", []) + q.get("redirects", [])}
        textes = {p["title"]: p.get("extract") for p in q.get("pages", {}).values()}
        for t in lot:
            cible = alias.get(alias.get(t, t), alias.get(t, t))
            if textes.get(cible):
                out[t] = textes[cible]
    return out


def sauver(cache):
    tmp = SORTIE.with_name(SORTIE.name + ".tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    tmp.replace(SORTIE)


def main():
    cache = json.loads(SORTIE.read_text(encoding="utf-8")) if SORTIE.exists() else {}
    for cle in ("films", "series", "livres", "_faits"):
        cache.setdefault(cle, {} if cle != "_faits" else [])
    faits = set(cache["_faits"])

    try:
        # ---------- séries : IMDb -> Wikidata -> fr.wikipedia ----------
        if "series" not in faits:
            series = json.loads((DONNEES / "series.json").read_text(encoding="utf-8"))["series"]
            par_imdb = {s["imdb"]: s["tvmaze_id"] for s in series if s.get("imdb")}
            imdb = list(par_imdb)
            qid_par_imdb = {}
            for i in range(0, len(imdb), 50):
                lot = imdb[i:i + 50]
                r = get("https://www.wikidata.org/w/api.php", {"action": "query", "list": "search", "srlimit": 50,
                                                               "srsearch": "haswbstatement:" + "|".join(f"P345={x}" for x in lot),
                                                               "format": "json"})
                qids = [x["title"] for x in r["query"]["search"]]
                if qids:
                    e = get("https://www.wikidata.org/w/api.php", {"action": "wbgetentities", "ids": "|".join(qids),
                                                                   "props": "claims", "format": "json"})
                    for q, ent in e.get("entities", {}).items():
                        for c in ent.get("claims", {}).get("P345", []):
                            v = c["mainsnak"].get("datavalue", {}).get("value")
                            if v in par_imdb:
                                qid_par_imdb[v] = q
            titres = articles_fr(list(set(qid_par_imdb.values())))
            intros = introductions(list(set(titres.values())))
            for v, q in qid_par_imdb.items():
                texte = couper(intros.get(titres.get(q)))
                if texte:
                    cache["series"][str(par_imdb[v])] = texte
            faits.add("series")
            cache["_faits"] = sorted(faits)
            sauver(cache)
            print(f"Séries : {len(cache['series'])} résumés FR", flush=True)

        # ---------- livres : titre FR connu, article homonyme qui cite l'auteur ----------
        if "livres" not in faits:
            livres = [l for l in json.loads((DONNEES / "livres.json").read_text(encoding="utf-8"))["livres"] if l.get("francais")]
            intros = introductions(sorted({l["titre"] for l in livres}))
            for l in livres:
                texte = intros.get(l["titre"])
                nom = sans_accents(l["auteur"].split()[-1])
                if texte and nom in sans_accents(texte):
                    cache["livres"][l["id"]] = couper(texte)
            faits.add("livres")
            cache["_faits"] = sorted(faits)
            sauver(cache)
            print(f"Livres : {len(cache['livres'])} résumés FR", flush=True)

        # ---------- films : QID connu -> fr.wikipedia (par tranches, reprise possible) ----------
        affiches = json.loads((DONNEES / "affiches.json").read_text(encoding="utf-8"))["films"]
        a_faire = [(mid, v["wikidata"]) for mid, v in affiches.items()
                   if v.get("wikidata") and mid not in cache["films"] and mid not in set(cache.get("_films_sans", []))]
        print(f"Films : {len(cache['films'])} déjà faits, {len(a_faire)} à traiter", flush=True)
        sans = set(cache.get("_films_sans", []))
        for i in range(0, len(a_faire), 200):
            tranche = a_faire[i:i + 200]
            titres = articles_fr([q for _, q in tranche])
            intros = introductions(sorted(set(titres.values())))
            for mid, q in tranche:
                texte = couper(intros.get(titres.get(q)))
                if texte:
                    cache["films"][mid] = texte
                else:
                    sans.add(mid)
            cache["_films_sans"] = sorted(sans)
            sauver(cache)
            print(f"  films {min(i + 200, len(a_faire))}/{len(a_faire)} — {len(cache['films'])} résumés", flush=True)
    except Bloque:
        print("Wikimedia limite le débit (429) : arrêt propre, relancer plus tard (ou définir ENNUI_CONTACT).")
    sauver(cache)
    print(f"Terminé : {len(cache['films'])} films, {len(cache['series'])} séries, {len(cache['livres'])} livres avec résumé FR")


if __name__ == "__main__":
    main()
