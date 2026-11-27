"""
Persistance SQLite (bibliothèque standard) : utilisateurs, plans collaboratifs, participants, messages.

Connexion express : un utilisateur = un prénom + une ville + ses préférences, identifié par un
jeton aléatoire stocké dans le navigateur. Pas de mot de passe : c'est un outil de démo pour
organiser des sorties entre étudiants, pas un système d'authentification.

Fichier : backend/data/ennui.sqlite3 (ignoré par git : données des utilisateurs).
Une connexion par opération (thread-safe avec FastAPI), mode WAL pour les lectures concurrentes.
"""

import json
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

CHEMIN = Path(__file__).resolve().parent / "data" / "ennui.sqlite3"
GRACE_PASSE = timedelta(hours=6)  # un plan reste visible 6 h après son début

SCHEMA = """
CREATE TABLE IF NOT EXISTS utilisateurs (
    id          TEXT PRIMARY KEY,
    prenom      TEXT NOT NULL,
    ville       TEXT,               -- JSON {nom, contexte, lat, lon} ou NULL
    prefs       TEXT NOT NULL,      -- JSON
    cree_le     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS plans (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    oeuvre_id     TEXT NOT NULL,     -- "film:…", "serie:…", "sortie:…"
    oeuvre_titre  TEXT NOT NULL,     -- copie : le plan reste lisible si l'événement sort du catalogue
    oeuvre_type   TEXT NOT NULL,
    auteur_id     TEXT NOT NULL REFERENCES utilisateurs(id),
    debut         TEXT NOT NULL,     -- ISO 8601 avec fuseau
    rendez_vous   TEXT,              -- point de rendez-vous ou lien de watch-party
    message       TEXT,
    cree_le       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS plans_oeuvre ON plans(oeuvre_id, debut);
CREATE TABLE IF NOT EXISTS participants (
    plan_id         INTEGER NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    utilisateur_id  TEXT NOT NULL REFERENCES utilisateurs(id),
    rejoint_le      TEXT NOT NULL,
    PRIMARY KEY (plan_id, utilisateur_id)
);
CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id         INTEGER NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    utilisateur_id  TEXT NOT NULL REFERENCES utilisateurs(id),
    texte           TEXT NOT NULL,
    cree_le         TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (cle TEXT PRIMARY KEY, valeur TEXT);
CREATE TABLE IF NOT EXISTS sorties_communaute (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    auteur_id    TEXT NOT NULL REFERENCES utilisateurs(id),
    titre        TEXT NOT NULL,
    categorie    TEXT NOT NULL,
    lieu         TEXT NOT NULL,
    ville        TEXT NOT NULL,
    lat          REAL NOT NULL,
    lon          REAL NOT NULL,
    debut        TEXT NOT NULL,     -- ISO 8601 avec fuseau
    fin          TEXT NOT NULL,
    prix         REAL,              -- euros ; 0 = gratuit ; NULL = non précisé
    description  TEXT,
    cree_le      TEXT NOT NULL
);
"""


def maintenant_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connexion(chemin: Path = None):
    con = sqlite3.connect(chemin or CHEMIN, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def initialiser(chemin: Path = None):
    (chemin or CHEMIN).parent.mkdir(parents=True, exist_ok=True)
    with connexion(chemin) as con:
        con.execute("PRAGMA journal_mode = WAL")
        con.executescript(SCHEMA)


# ------------------------------------------------------------------ #
# Utilisateurs                                                         #
# ------------------------------------------------------------------ #

def _utilisateur(row) -> dict:
    return {"id": row["id"], "prenom": row["prenom"], "ville": json.loads(row["ville"] or "null"),
            "prefs": json.loads(row["prefs"]), "cree_le": row["cree_le"]}


def creer_utilisateur(prenom: str, ville: Optional[dict], prefs: dict) -> dict:
    uid = secrets.token_urlsafe(16)
    with connexion() as con:
        con.execute("INSERT INTO utilisateurs VALUES (?, ?, ?, ?, ?)",
                    (uid, prenom, json.dumps(ville), json.dumps(prefs), maintenant_iso()))
    return lire_utilisateur(uid)


def lire_utilisateur(uid: str) -> Optional[dict]:
    with connexion() as con:
        row = con.execute("SELECT * FROM utilisateurs WHERE id = ?", (uid,)).fetchone()
    return _utilisateur(row) if row else None


def mettre_a_jour_utilisateur(uid: str, prenom: str, ville: Optional[dict], prefs: dict) -> Optional[dict]:
    with connexion() as con:
        con.execute("UPDATE utilisateurs SET prenom = ?, ville = ?, prefs = ? WHERE id = ?",
                    (prenom, json.dumps(ville), json.dumps(prefs), uid))
    return lire_utilisateur(uid)


# ------------------------------------------------------------------ #
# Plans                                                                #
# ------------------------------------------------------------------ #

def _limite_passe() -> str:
    return (datetime.now(timezone.utc) - GRACE_PASSE).isoformat(timespec="seconds")


def creer_plan(auteur_id: str, oeuvre: dict, debut: str, rendez_vous: str, message: str) -> int:
    with connexion() as con:
        cur = con.execute(
            "INSERT INTO plans (oeuvre_id, oeuvre_titre, oeuvre_type, auteur_id, debut, rendez_vous, message, cree_le)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (oeuvre["id"], oeuvre["titre"], oeuvre["type"], auteur_id, debut, rendez_vous, message, maintenant_iso()))
        plan_id = cur.lastrowid
        con.execute("INSERT INTO participants VALUES (?, ?, ?)", (plan_id, auteur_id, maintenant_iso()))
    return plan_id


def rejoindre(plan_id: int, uid: str, actif: bool = True) -> bool:
    with connexion() as con:
        if not con.execute("SELECT 1 FROM plans WHERE id = ?", (plan_id,)).fetchone():
            return False
        if actif:
            con.execute("INSERT OR IGNORE INTO participants VALUES (?, ?, ?)", (plan_id, uid, maintenant_iso()))
        else:
            con.execute("DELETE FROM participants WHERE plan_id = ? AND utilisateur_id = ?", (plan_id, uid))
            # un plan sans plus aucun participant disparaît
            if not con.execute("SELECT 1 FROM participants WHERE plan_id = ?", (plan_id,)).fetchone():
                con.execute("DELETE FROM plans WHERE id = ?", (plan_id,))
    return True


def ajouter_message(plan_id: int, uid: str, texte: str) -> bool:
    with connexion() as con:
        if not con.execute("SELECT 1 FROM plans WHERE id = ?", (plan_id,)).fetchone():
            return False
        con.execute("INSERT INTO messages (plan_id, utilisateur_id, texte, cree_le) VALUES (?, ?, ?, ?)",
                    (plan_id, uid, texte, maintenant_iso()))
    return True


def _plans(con, where: str, params: Iterable, uid: Optional[str], avec_messages: bool) -> List[dict]:
    rows = con.execute(f"""
        SELECT p.*, u.prenom AS auteur_prenom FROM plans p JOIN utilisateurs u ON u.id = p.auteur_id
        WHERE {where} AND p.debut >= ? ORDER BY p.debut""", (*params, _limite_passe())).fetchall()
    plans = []
    for r in rows:
        parts = con.execute("""SELECT u.id, u.prenom FROM participants pa JOIN utilisateurs u ON u.id = pa.utilisateur_id
                               WHERE pa.plan_id = ? ORDER BY pa.rowid""", (r["id"],)).fetchall()
        plan = {
            "id": r["id"], "oeuvre_id": r["oeuvre_id"], "oeuvre_titre": r["oeuvre_titre"],
            "oeuvre_type": r["oeuvre_type"], "debut": r["debut"], "rendez_vous": r["rendez_vous"],
            "message": r["message"], "auteur": r["auteur_prenom"], "est_auteur": r["auteur_id"] == uid,
            "participants": [p["prenom"] for p in parts],
            "je_participe": any(p["id"] == uid for p in parts),
        }
        if avec_messages:
            plan["messages"] = [dict(m) for m in con.execute(
                """SELECT u.prenom, m.texte, m.cree_le FROM messages m JOIN utilisateurs u ON u.id = m.utilisateur_id
                   WHERE m.plan_id = ? ORDER BY m.id""", (r["id"],)).fetchall()]
        plans.append(plan)
    return plans


def plans_par_oeuvre(oeuvre_ids: List[str], uid: Optional[str]) -> Dict[str, List[dict]]:
    """Plans à venir pour une liste d'œuvres (une requête par lot de résultats)."""
    if not oeuvre_ids:
        return {}
    marques = ",".join("?" * len(oeuvre_ids))
    with connexion() as con:
        plans = _plans(con, f"p.oeuvre_id IN ({marques})", oeuvre_ids, uid, avec_messages=False)
    out: Dict[str, List[dict]] = {}
    for p in plans:
        out.setdefault(p["oeuvre_id"], []).append(p)
    return out


def plans_detail(oeuvre_id: str, uid: Optional[str]) -> List[dict]:
    with connexion() as con:
        return _plans(con, "p.oeuvre_id = ?", (oeuvre_id,), uid, avec_messages=True)


def mes_plans(uid: str) -> List[dict]:
    with connexion() as con:
        return _plans(con, "p.id IN (SELECT plan_id FROM participants WHERE utilisateur_id = ?)",
                      (uid,), uid, avec_messages=False)


# ------------------------------------------------------------------ #
# Méta (dernière synchronisation de l'agenda, etc.)                    #
# ------------------------------------------------------------------ #

def lire_meta(cle: str) -> Optional[str]:
    with connexion() as con:
        row = con.execute("SELECT valeur FROM meta WHERE cle = ?", (cle,)).fetchone()
    return row["valeur"] if row else None


def ecrire_meta(cle: str, valeur: str):
    with connexion() as con:
        con.execute("INSERT INTO meta VALUES (?, ?) ON CONFLICT(cle) DO UPDATE SET valeur = excluded.valeur",
                    (cle, valeur))


# ------------------------------------------------------------------ #
# Sorties publiées par les utilisateurs                                #
# ------------------------------------------------------------------ #

def creer_sortie(auteur_id: str, titre: str, categorie: str, lieu: str, ville: dict,
                 debut: str, fin: str, prix: Optional[float], description: str) -> int:
    with connexion() as con:
        cur = con.execute(
            "INSERT INTO sorties_communaute (auteur_id, titre, categorie, lieu, ville, lat, lon, debut, fin, prix,"
            " description, cree_le) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (auteur_id, titre, categorie, lieu, ville["nom"], ville["lat"], ville["lon"], debut, fin, prix,
             description, maintenant_iso()))
        return cur.lastrowid


def sorties_communaute() -> List[dict]:
    """Sorties publiées encore à venir, au format de france.json (pour le graphe)."""
    try:  # mêmes règles de genres que les sorties OpenAgenda (mots-clés + catégorie)
        from .fetch_france import genres_pour
    except ImportError:
        from fetch_france import genres_pour
    maintenant = maintenant_iso()
    with connexion() as con:
        rows = con.execute("""SELECT s.*, u.prenom FROM sorties_communaute s JOIN utilisateurs u ON u.id = s.auteur_id
                              WHERE s.fin >= ? ORDER BY s.debut""", (maintenant,)).fetchall()
    out = []
    for r in rows:
        prix = r["prix"]
        out.append({
            "id": f"co-{r['id']}", "titre": r["titre"], "description": r["description"] or None,
            "categorie": r["categorie"], "genres": genres_pour(r["categorie"], f"{r['titre']} {r['description'] or ''}"),
            "ville": r["ville"], "ville_reference": r["ville"],
            "lieu": r["lieu"], "adresse": None, "lat": r["lat"], "lon": r["lon"], "acces": None,
            "prix": prix, "tarif": None if prix is None else ("Gratuit" if prix == 0 else f"{prix:g} €".replace(".", ",")),
            "date_debut": r["debut"][:10], "date_fin": r["fin"][:10], "occurrences": [[r["debut"], r["fin"]]],
            "image": None, "credit_image": None, "url": None,
            "source": "communaute", "propose_par": r["prenom"],
        })
    return out


def purger_sorties_passees() -> int:
    with connexion() as con:
        return con.execute("DELETE FROM sorties_communaute WHERE fin < ?", (maintenant_iso(),)).rowcount


def villes_utilisateurs() -> Dict[str, List[float]]:
    """{nom: [lat, lon]} des villes choisies par les utilisateurs."""
    with connexion() as con:
        rows = con.execute("SELECT ville FROM utilisateurs WHERE ville IS NOT NULL AND ville != 'null'").fetchall()
    out = {}
    for r in rows:
        v = json.loads(r["ville"])
        if v and v.get("nom"):
            out[v["nom"]] = [v["lat"], v["lon"]]
    return out
