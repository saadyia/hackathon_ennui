"""
Persistance SQLite (bibliothèque standard) : utilisateurs, amis, plans collaboratifs, participants, messages.

Connexion express : un utilisateur = un prénom + une ville + ses préférences, identifié par un
jeton aléatoire stocké dans le navigateur. Pas de mot de passe : c'est un outil de démo pour
organiser des sorties entre étudiants, pas un système d'authentification.

Fichier : backend/data/ennui.sqlite3 (ignoré par git : données des utilisateurs).
Une connexion par opération (thread-safe avec FastAPI), mode WAL pour les lectures concurrentes.
"""

import json
import random
import secrets
import sqlite3
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

CHEMIN = Path(__file__).resolve().parent / "data" / "ennui.sqlite3"
GRACE_PASSE = timedelta(hours=6)  # un plan reste visible 6 h après son début
DUREE_DISPO = timedelta(hours=12)  # un statut « Dispo » expire au bout de 12 h (c'est un statut du moment)
STATUTS_DISPO = ("indispo", "sortir", "distance")

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
-- Amitié symétrique, stockée dans les deux sens (a -> b et b -> a) pour des lectures simples
CREATE TABLE IF NOT EXISTS amities (
    utilisateur_id  TEXT NOT NULL REFERENCES utilisateurs(id) ON DELETE CASCADE,
    ami_id          TEXT NOT NULL REFERENCES utilisateurs(id) ON DELETE CASCADE,
    cree_le         TEXT NOT NULL,
    PRIMARY KEY (utilisateur_id, ami_id)
);
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


# Colonnes ajoutées après coup (migration douce des bases existantes)
COLONNES_UTILISATEURS = {
    "code": "TEXT",                      # identifiant public court, ex. « Sadia#402 » (le jeton id reste secret)
    "dispo": "TEXT NOT NULL DEFAULT 'indispo'",
    "dispo_le": "TEXT",
    "demo": "INTEGER NOT NULL DEFAULT 0",  # profil de démonstration (fictif, signalé comme tel)
    "avatar": "TEXT",                    # JSON DiceBear {style, seed, bg, hair?, glasses?, mouth?, eyes?} ; NULL = dérivé du prénom
}

# Profils fictifs pour tester les interactions sociales tout de suite. Ils sont marqués « Démo »
# dans l'interface et ne rejoignent aucun plan : on n'invente ni participants ni activité.
PROFILS_DEMO = [
    ("demo-camille", "Camille", "Camille#101", "Rennes", 48.1113, -1.6800, "sortir",
     {"style": "lorelei", "seed": "Camille", "bg": "351f47", "glasses": "variant04", "mouth": "happy03"}),
    ("demo-lucas", "Lucas", "Lucas#214", "Rennes", 48.1113, -1.6800, "distance",
     {"style": "micah", "seed": "Lucas", "bg": "13382e", "hair": "dougFunny", "mouth": "smile", "eyes": "smiling", "glasses": "aucune"}),
    ("demo-ines", "Inès", "Inès#327", "Nantes", 47.2184, -1.5536, "sortir",
     {"style": "lorelei", "seed": "Inès", "bg": "422b18", "mouth": "happy08", "glasses": "aucune"}),
    ("demo-thomas", "Thomas", "Thomas#438", "Lyon", 45.7640, 4.8357, "distance",
     {"style": "lorelei", "seed": "Thomas", "bg": "293548", "hair": "variant05", "glasses": "variant02", "mouth": "happy01"}),
]
DEMO_RETIRES = ("demo-yasmine",)  # anciens profils de démo (la liste en compte désormais 4)


def initialiser(chemin: Path = None):
    (chemin or CHEMIN).parent.mkdir(parents=True, exist_ok=True)
    with connexion(chemin) as con:
        con.execute("PRAGMA journal_mode = WAL")
        con.executescript(SCHEMA)
        existantes = {r["name"] for r in con.execute("PRAGMA table_info(utilisateurs)")}
        for nom, definition in COLONNES_UTILISATEURS.items():
            if nom not in existantes:
                con.execute(f"ALTER TABLE utilisateurs ADD COLUMN {nom} {definition}")
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS utilisateurs_code ON utilisateurs(code COLLATE NOCASE)")
        for (uid, prenom) in con.execute("SELECT id, prenom FROM utilisateurs WHERE code IS NULL").fetchall():
            con.execute("UPDATE utilisateurs SET code = ? WHERE id = ?", (_nouveau_code(con, prenom), uid))
        for uid, prenom, code, ville, lat, lon, dispo, avatar in PROFILS_DEMO:
            con.execute("""INSERT INTO utilisateurs (id, prenom, ville, prefs, cree_le, code, dispo, dispo_le, demo, avatar)
                           VALUES (?, ?, ?, '{}', ?, ?, ?, NULL, 1, ?)
                           ON CONFLICT(id) DO UPDATE SET dispo = excluded.dispo, avatar = excluded.avatar, demo = 1""",
                        (uid, prenom, json.dumps({"nom": ville, "lat": lat, "lon": lon}), maintenant_iso(), code, dispo,
                         json.dumps(avatar)))
        for uid in DEMO_RETIRES:  # amitiés supprimées en cascade
            con.execute("DELETE FROM utilisateurs WHERE id = ?", (uid,))


def _nouveau_code(con, prenom: str) -> str:
    """Code court unique « Prénom#123 » (insensible à la casse)."""
    base = "".join(prenom.split())[:20] or "Étudiant"
    for _ in range(200):
        code = f"{base}#{random.randint(100, 999)}"
        if not con.execute("SELECT 1 FROM utilisateurs WHERE code = ? COLLATE NOCASE", (code,)).fetchone():
            return code
    return f"{base}#{secrets.randbelow(900000) + 100000}"


def sans_accents(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


# ------------------------------------------------------------------ #
# Utilisateurs                                                         #
# ------------------------------------------------------------------ #

def dispo_actuelle(row) -> str:
    """Statut du moment : revient à « indispo » 12 h après avoir été choisi (sauf profils de démo)."""
    if row["demo"]:
        return row["dispo"]
    if row["dispo"] == "indispo" or not row["dispo_le"]:
        return "indispo"
    choisi = datetime.fromisoformat(row["dispo_le"])
    return row["dispo"] if datetime.now(timezone.utc) - choisi < DUREE_DISPO else "indispo"


def _utilisateur(row) -> dict:
    return {"id": row["id"], "prenom": row["prenom"], "ville": json.loads(row["ville"] or "null"),
            "prefs": json.loads(row["prefs"]), "cree_le": row["cree_le"],
            "code": row["code"], "dispo": dispo_actuelle(row), "avatar": json.loads(row["avatar"] or "null")}


def _public(row, ami: bool = False) -> dict:
    """Ce que les autres voient d'un profil : jamais le jeton id (il vaut authentification)."""
    ville = json.loads(row["ville"] or "null") or {}
    return {"code": row["code"], "prenom": row["prenom"], "ville": ville.get("nom"),
            "dispo": dispo_actuelle(row), "demo": bool(row["demo"]), "ami": ami,
            "avatar": json.loads(row["avatar"] or "null")}


def creer_utilisateur(prenom: str, ville: Optional[dict], prefs: dict, avatar: Optional[dict] = None) -> dict:
    uid = secrets.token_urlsafe(16)
    with connexion() as con:
        con.execute("INSERT INTO utilisateurs (id, prenom, ville, prefs, cree_le, code, avatar) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (uid, prenom, json.dumps(ville), json.dumps(prefs), maintenant_iso(), _nouveau_code(con, prenom),
                     json.dumps(avatar) if avatar else None))
    return lire_utilisateur(uid)


def lire_utilisateur(uid: str) -> Optional[dict]:
    with connexion() as con:
        row = con.execute("SELECT * FROM utilisateurs WHERE id = ?", (uid,)).fetchone()
    return _utilisateur(row) if row else None


def mettre_a_jour_utilisateur(uid: str, prenom: str, ville: Optional[dict], prefs: dict) -> Optional[dict]:
    with connexion() as con:
        ancien = con.execute("SELECT prenom FROM utilisateurs WHERE id = ?", (uid,)).fetchone()
        con.execute("UPDATE utilisateurs SET prenom = ?, ville = ?, prefs = ? WHERE id = ?",
                    (prenom, json.dumps(ville), json.dumps(prefs), uid))
        if ancien and ancien["prenom"] != prenom:  # le code suit le prénom
            con.execute("UPDATE utilisateurs SET code = ? WHERE id = ?", (_nouveau_code(con, prenom), uid))
    return lire_utilisateur(uid)


def changer_avatar(uid: str, avatar: dict) -> Optional[dict]:
    with connexion() as con:
        con.execute("UPDATE utilisateurs SET avatar = ? WHERE id = ?", (json.dumps(avatar), uid))
    return lire_utilisateur(uid)


def changer_dispo(uid: str, statut: str) -> Optional[dict]:
    with connexion() as con:
        con.execute("UPDATE utilisateurs SET dispo = ?, dispo_le = ? WHERE id = ?", (statut, maintenant_iso(), uid))
    return lire_utilisateur(uid)


# ------------------------------------------------------------------ #
# Amis                                                                 #
# ------------------------------------------------------------------ #

ORDRE_DISPO = {"sortir": 0, "distance": 1, "indispo": 2}


def amis(uid: str) -> List[dict]:
    """Amis de l'utilisateur, les disponibles d'abord."""
    with connexion() as con:
        rows = con.execute("""SELECT u.* FROM amities a JOIN utilisateurs u ON u.id = a.ami_id
                              WHERE a.utilisateur_id = ? ORDER BY a.cree_le DESC""", (uid,)).fetchall()
    out = [_public(r, ami=True) for r in rows]
    return sorted(out, key=lambda a: ORDRE_DISPO.get(a["dispo"], 3))


def suggestions(uid: str) -> List[dict]:
    """Profils de démonstration pas encore ajoutés (pour tester sans attendre de vrais amis)."""
    with connexion() as con:
        rows = con.execute("""SELECT * FROM utilisateurs WHERE demo = 1 AND id != ?
                              AND id NOT IN (SELECT ami_id FROM amities WHERE utilisateur_id = ?)
                              ORDER BY prenom""", (uid, uid)).fetchall()
    return [_public(r) for r in rows]


def rechercher_profils(uid: str, q: str, limite: int = 10) -> List[dict]:
    """Par code exact (« Sadia#402 ») ou début de prénom, sans accents ni casse ; soi-même exclu."""
    q = q.strip()
    cible = sans_accents(q)
    with connexion() as con:
        deja = {r["ami_id"] for r in con.execute("SELECT ami_id FROM amities WHERE utilisateur_id = ?", (uid,))}
        rows = con.execute("SELECT * FROM utilisateurs WHERE id != ?", (uid,)).fetchall()
    if "#" in cible:
        trouves = [r for r in rows if r["code"] and sans_accents(r["code"]) == cible]
    else:
        trouves = [r for r in rows if sans_accents(r["prenom"]).startswith(cible)]
    trouves.sort(key=lambda r: (r["id"] not in deja, not r["demo"], r["prenom"]))
    return [_public(r, ami=r["id"] in deja) for r in trouves[:limite]]


def ajouter_ami(uid: str, code: str) -> Optional[dict]:
    with connexion() as con:
        row = con.execute("SELECT * FROM utilisateurs WHERE code = ? COLLATE NOCASE", (code.strip(),)).fetchone()
        if not row or row["id"] == uid:
            return None
        quand = maintenant_iso()
        con.execute("INSERT OR IGNORE INTO amities VALUES (?, ?, ?)", (uid, row["id"], quand))
        con.execute("INSERT OR IGNORE INTO amities VALUES (?, ?, ?)", (row["id"], uid, quand))
    return _public(row, ami=True)


def retirer_ami(uid: str, code: str) -> bool:
    with connexion() as con:
        row = con.execute("SELECT id FROM utilisateurs WHERE code = ? COLLATE NOCASE", (code.strip(),)).fetchone()
        if not row:
            return False
        con.execute("DELETE FROM amities WHERE (utilisateur_id = ? AND ami_id = ?) OR (utilisateur_id = ? AND ami_id = ?)",
                    (uid, row["id"], row["id"], uid))
    return True


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


def plans_a_venir(limite: int, uid: Optional[str]) -> List[dict]:
    with connexion() as con:
        return _plans(con, "p.debut >= ? AND 1 = 1", (maintenant_iso(),), uid, avec_messages=False)[:limite]


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
