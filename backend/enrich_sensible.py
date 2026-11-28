"""
Contenus sensibles (hors ligne, clé TMDB) : repère les films et séries au contenu adulte ou suggestif,
pour qu'ils ne soient jamais recommandés (application présentée en public, devant un jury).

Critères, tous lus chez TMDB (rien n'est deviné) :
  - drapeau `adult` ;
  - mots-clés TMDB explicites (nudité, érotisme, comédie sexy, striptease…) ;
  Les classifications par âge ne sont PAS utilisées : chez TMDB, « FR:16 » couvre Le Parrain, Piège de cristal ou
  Matrix Reloaded (diffusions TV) ; elles excluaient des centaines de classiques sans rapport.

    python3 backend/enrich_sensible.py      # lit tmdb.json -> data/sensibles.json (~4 min)
    python3 backend/build_graph.py ...      # ou reconstruire_externes() : le moteur les exclut
"""

import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from enrich_tmdb import Client, lire_cle  # noqa: E402

RACINE = Path(__file__).resolve().parent
TMDB = RACINE / "data" / "tmdb.json"
SORTIE = RACINE / "data" / "sensibles.json"

# Mots-clés TMDB (nom exact) qui disent un contenu sexuel explicite. Volontairement étroit : « prostitution »,
# « voyeurisme », « séduction », « strip club », « lust »… décrivent souvent une scène ou un thème (Pretty Woman,
# Fenêtre sur cour, Le Flic de Beverly Hills) et excluaient des classiques sans affiche gênante.
MOTS_CLES = re.compile(
    r"(nudity|female nudity|male nudity|full frontal nudity|nude|naked|nudism|nudist|nudist colony|nudist camp|topless|"
    r"erotic|erotica|eroticism|erotic movie|erotic thriller|erotic film|sex comedy|teen sex comedy|sexploitation|softcore|"
    r"sex scene|striptease|strip tease|porn actor|porn actress|porn star|porn industry|pornographer|porn film|"
    r"pornographic film|orgy|bdsm|sexual fantasy|sexual awakening|sexual obsession|sex tape|swinger|swingers|"
    r"sex with a minor|pedophilia|underage sex)", re.I)
def mots_explicites(d: dict) -> list:
    kw = d.get("keywords") or {}
    liste = kw.get("keywords") or kw.get("results") or []  # films : keywords ; séries : results
    return sorted({k["name"] for k in liste if MOTS_CLES.fullmatch(k.get("name", "").strip())})


def analyser(client, genre, cle, tmdb_id):
    chemin = f"/movie/{tmdb_id}" if genre == "films" else f"/tv/{tmdb_id}"
    d = client.get(chemin, {"append_to_response": "keywords"})
    return genre, cle, (["adulte"] if d.get("adult") else []) + [f"mot-clé : {m}" for m in mots_explicites(d)]


def main():
    cle = lire_cle()
    if not cle:
        sys.exit("Clé TMDB absente (TMDB_API_KEY dans l'environnement ou dans .env).")
    tmdb = json.loads(TMDB.read_text(encoding="utf-8"))
    taches = [(g, k, v["tmdb_id"]) for g in ("films", "series") for k, v in tmdb.get(g, {}).items()
              if v and v.get("tmdb_id")]
    client = Client(cle)
    resultat = {"films": {}, "series": {}}
    erreurs = 0
    with ThreadPoolExecutor(8) as ex:
        futurs = [ex.submit(analyser, client, *t) for t in taches]
        for i, f in enumerate(as_completed(futurs), 1):
            try:
                genre, k, raisons = f.result()
            except Exception:
                erreurs += 1  # erreur réseau isolée : le titre reste non marqué (comptée, affichée)
                continue
            if raisons:
                resultat[genre][k] = raisons
            if i % 1000 == 0:
                print(f"  {i}/{len(taches)}")
    if erreurs > len(taches) * 0.05:  # jamais écraser un bon fichier par un résultat incomplet
        sys.exit(f"{erreurs} erreurs sur {len(taches)} : {SORTIE.name} conservé tel quel.")
    resultat["genere_le"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    tmp = SORTIE.with_suffix(".tmp")
    tmp.write_text(json.dumps(resultat, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, SORTIE)
    print(f"Sensibles : {len(resultat['films'])} films, {len(resultat['series'])} séries sur {len(taches)} titres analysés, {erreurs} erreur(s) réseau.")


if __name__ == "__main__":
    main()
