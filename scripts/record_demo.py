"""
Vidéo de démonstration de « ofk? » (format iPhone 390 x 844, rendu x2), environ 2 minutes.

    python3 -m pip install --user playwright imageio-ffmpeg   # une fois (Chrome du Mac utilisé, rien à télécharger)
    python3 scripts/record_demo.py                            # -> demo_output/ofk_demo.mp4

- Lance son propre serveur FastAPI (port 8010) sur une base SQLite JETABLE (ENNUI_DB) et sans synchro de
  l'agenda : aucun compte de test ne reste dans la vraie base.
- Un point tactile translucide suit chaque déplacement, clic et défilement.
- Un second compte réel (« Malo ») rejoint en direct le créneau proposé : la synchro temps réel de
  l'application (toast, avatars des participants) est filmée telle quelle, rien n'est simulé à l'écran.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

RACINE = Path(__file__).resolve().parent.parent
SORTIE = RACINE / "demo_output"
PORT = 8010
URL = f"http://127.0.0.1:{PORT}"
LARGEUR, HAUTEUR, ECHELLE = 390, 844, 2
VITESSE = 0.62  # < 1 : pauses raccourcies (durée totale visée : ~2 min)

# Point tactile : suit la souris, s'agrandit au clic. pointer-events:none, au-dessus de tout.
SCRIPT_POINT = """
(() => {
  const css = `#__doigt{position:fixed;left:0;top:0;width:34px;height:34px;margin:-17px 0 0 -17px;border-radius:50%;
    background:rgba(255,255,255,.28);border:1.5px solid rgba(255,255,255,.75);box-shadow:0 0 18px rgba(255,255,255,.25);
    pointer-events:none;z-index:2147483647;transition:transform .18s cubic-bezier(.2,.9,.3,1.4),opacity .25s;opacity:0}
    #__doigt.appui{transform:scale(.72);background:rgba(232,217,181,.45)}`;
  const go = () => {
    if (document.getElementById("__doigt")) return;
    const st = document.createElement("style"); st.textContent = css; document.head.appendChild(st);
    const d = document.createElement("div"); d.id = "__doigt"; document.body.appendChild(d);
    addEventListener("mousemove", (e) => { d.style.left = e.clientX + "px"; d.style.top = e.clientY + "px"; d.style.opacity = 1; }, true);
    addEventListener("mousedown", () => d.classList.add("appui"), true);
    addEventListener("mouseup", () => d.classList.remove("appui"), true);
  };
  document.readyState === "loading" ? addEventListener("DOMContentLoaded", go) : go();
})();
"""


# ------------------------------------------------------------------ #
# Serveur jetable                                                      #
# ------------------------------------------------------------------ #
def port_libre(port):
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def api(chemin, corps=None, jeton=None, methode=None):
    req = urllib.request.Request(URL + chemin, data=json.dumps(corps).encode() if corps is not None else None,
                                 method=methode or ("POST" if corps is not None else "GET"),
                                 headers={"Content-Type": "application/json", **({"X-Utilisateur": jeton} if jeton else {})})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def lancer_serveur(base):
    if not port_libre(PORT):
        sys.exit(f"Le port {PORT} est déjà pris : arrête l'autre serveur ou change PORT.")
    env = {**os.environ, "ENNUI_SYNC": "0", "ENNUI_DB": str(base)}
    env.pop("DATABASE_URL", None)  # jamais la base de production
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.main:app", "--port", str(PORT)],
                            cwd=RACINE, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            api("/api/config")
            return proc
        except Exception:
            time.sleep(0.5)
    proc.kill()
    sys.exit("Le serveur n'a pas démarré.")


# ------------------------------------------------------------------ #
# Gestes lissés                                                        #
# ------------------------------------------------------------------ #
class Geste:
    def __init__(self, page):
        self.p = page
        self.x, self.y = LARGEUR / 2, HAUTEUR * 0.7

    def pause(self, s):
        self.p.wait_for_timeout(int(s * 1000 * VITESSE))

    def aller(self, x, y, duree=0.32):
        pas = max(8, int(duree * 60))
        for i in range(1, pas + 1):
            t = i / pas
            t = t * t * (3 - 2 * t)  # ease in-out
            self.p.mouse.move(self.x + (x - self.x) * t, self.y + (y - self.y) * t)
            self.p.wait_for_timeout(int(duree * 1000 / pas))
        self.x, self.y = x, y

    def boite(self, sel, visible=True):
        el = self.p.locator(sel).first
        el.wait_for(state="visible", timeout=15000)
        if visible:
            el.scroll_into_view_if_needed()
            self.p.wait_for_timeout(150)
        return el.bounding_box()

    def toucher(self, sel, pause=0.35, dx=0.5, dy=0.5):
        b = self.boite(sel)
        self.aller(b["x"] + b["width"] * dx, b["y"] + b["height"] * dy)
        self.pause(0.12)
        self.p.mouse.down(); self.pause(0.09); self.p.mouse.up()
        self.pause(pause)

    def taper(self, sel, texte, delai=55):
        self.toucher(sel, 0.2)
        self.p.keyboard.type(texte, delay=delai)

    def glisser(self, x0, y, x1, duree=1.0):
        self.aller(x0, y, 0.4)
        self.p.mouse.down()
        self.aller(x1, y, duree)
        self.p.mouse.up()

    def defiler(self, dy, duree=1.5, conteneur=None):
        """Défilement lissé (fenêtre ou panneau ouvert), le point tactile glisse avec."""
        self.p.evaluate("""([dy, ms, sel]) => new Promise((ok) => {
            const el = sel ? document.querySelector(sel) : null;
            const lire = () => el ? el.scrollTop : scrollY;
            const ecrire = (v) => el ? (el.scrollTop = v) : scrollTo(0, v);
            const y0 = lire(), t0 = performance.now();
            const pas = (t) => { const k = Math.min(1, (t - t0) / ms), e = k < .5 ? 2*k*k : 1 - Math.pow(-2*k + 2, 2) / 2;
              ecrire(y0 + dy * e); k < 1 ? requestAnimationFrame(pas) : ok(); };
            requestAnimationFrame(pas); })""", [dy, int(duree * 1000), conteneur])
        # le doigt « pousse » la page : petit trajet vertical pendant le défilement
        self.aller(self.x, min(HAUTEUR - 120, max(160, self.y + (-60 if dy > 0 else 60))), 0.25)

    def curseur(self, cran_depart, cran_arrivee, duree=2.4, sel="#curseur-ui"):
        """Glisse la poignée du curseur Confort ↔ Découverte (noUiSlider, crans 1 à 10)."""
        b = self.boite(sel)
        pos = lambda c: b["x"] + b["width"] * (c - 1) / 9
        poignee = self.boite(f"{sel} .noUi-handle", visible=False)
        self.aller(poignee["x"] + poignee["width"] / 2, poignee["y"] + poignee["height"] / 2, 0.5)
        y = poignee["y"] + poignee["height"] / 2
        self.p.mouse.down()
        if cran_depart is not None:
            self.aller(pos(cran_depart), y, 0.6)
            self.pause(0.5)
        self.aller(pos(cran_arrivee), y, duree)
        self.p.mouse.up()
        self.pause(0.4)

    def fermer_feuille(self):
        self.toucher(".feuille-panneau .feuille-fermer", 0.7)


# ------------------------------------------------------------------ #
# Scénario                                                             #
# ------------------------------------------------------------------ #
def scenario(page, g):
    # 1. 0:00 – 0:15 · Splash, inscription, studio d'avatar
    page.goto(URL + "/")
    g.pause(2.2)                                       # splash animé « ofk? »
    g.toucher('[data-action="c-est-parti"]', 0.8)
    g.taper("#champ-prenom", "Sadia")
    g.pause(0.3)
    g.toucher('[data-action="ouvrir-studio"]', 0.7)
    g.toucher('[data-action="studio-onglet"][data-valeur="bg"]', 0.4)
    g.toucher('#studio-options [data-action="studio-choix"]:nth-child(4)', 0.4)
    g.toucher('[data-action="studio-aleatoire"]', 0.6)
    g.toucher('[data-action="studio-enregistrer"]', 0.6)
    g.taper("#mdp-inscription", "demo-ofk-2026", delai=45)
    g.taper("#champ-ville", "Rennes")
    g.toucher('#suggestions-ville [data-action="choisir-ville"]', 0.5)
    b = g.boite("#rayon")
    g.glisser(b["x"] + b["width"] * 0.22, b["y"] + b["height"] / 2, b["x"] + b["width"] * 0.45, 0.8)
    for genre in ("Sci-Fi", "Animation", "Adventure"):
        sel = f'[data-action="pref"][data-groupe="genres"][data-valeur=\'"{genre}"\']'
        if page.locator(sel).count():
            g.toucher(sel, 0.15)
    for pf in (8, 119):  # Netflix, Prime Video
        sel = f'[data-action="pref"][data-groupe="plateformes"][data-valeur="{pf}"]'
        if page.locator(sel).count():
            g.toucher(sel, 0.15)
    g.toucher('[data-action="commencer"]', 2.2)

    # 2. 0:15 – 0:25 · Pour vous + curseur 2 -> 8 + défilement
    page.locator(".rangee-affiches .carte-oeuvre").first.wait_for(timeout=20000)
    g.pause(1.2)
    g.curseur(2, 8, duree=2.6)
    g.pause(1.2)
    g.defiler(1100, 2.6)
    g.pause(0.6)
    g.defiler(-1100, 1.2)

    # 3. 0:25 – 0:45 · Chez soi (Ce soir, au chaud)
    g.toucher('#onglets [data-onglet="ecrans"]', 1.6)
    for seg in ("ecrans", "livre", "jeu"):
        g.toucher(f'[data-action="segment"][data-valeur="{seg}"]', 1.8)
        g.defiler(380, 0.8); g.pause(0.4); g.defiler(-380, 0.5)
    g.toucher('[data-action="mode-jeu"][data-valeur="multi"]', 1.4)
    g.toucher('[data-action="mode-jeu"][data-valeur="solo"]', 1.4)
    g.toucher('.grille-affiches .carte-oeuvre [data-action="ouvrir-plans"]', 1.6)
    g.defiler(420, 1.4, ".feuille-corps"); g.pause(1.0)
    g.fermer_feuille()

    # 4. 0:45 – 1:08 · Hors écran
    g.toucher('#onglets [data-onglet="hors-ecran"]', 3.6)
    for seg in ("creatif", "cuisine", "mouvement"):
        g.toucher(f'[data-action="segment-hors"][data-valeur="{seg}"]', 1.6)
        g.defiler(330, 0.8); g.pause(0.3); g.defiler(-330, 0.5)
    g.toucher('[data-action="segment-hors"][data-valeur="cuisine"]', 1.2)
    g.curseur(None, 9, duree=1.8)
    g.pause(1.4)
    g.toucher(".grille-activites .carte-activite h3", 1.4)
    g.defiler(520, 1.8, ".feuille-corps"); g.pause(1.4)
    g.defiler(560, 1.8, ".feuille-corps"); g.pause(1.6)
    g.fermer_feuille()

    # 5. 1:08 – 1:28 · Sorties
    g.toucher('#onglets [data-onglet="sorties"]', 1.8)
    for seg in ("culture", "soirees", "nature"):
        g.toucher(f'[data-action="segment-sorties"][data-valeur="{seg}"]', 1.6)
        g.defiler(820, 1.4); g.pause(1.4); g.defiler(-820, 0.7)

    # 6. 1:28 – 2:00 · Choisir à ma place, créneau, un ami qui rejoint en direct
    g.toucher('[data-action="choisir-pour-moi"]', 2.6)  # tirage ~500 ms puis fiche « Sélectionné pour vous »
    g.defiler(700, 1.6, ".feuille-corps"); g.pause(0.6)
    g.taper("#champ-rdv", "Devant l'entrée")
    g.taper('#form-plan [name="message"]', "On y va ensemble ?", delai=60)
    g.toucher('#form-plan button[type="submit"]', 1.8)

    # Malo (vrai second compte, base jetable) devient ami et rejoint le créneau ; l'appli le voit à la synchro
    jeton = json.loads(page.evaluate("localStorage.getItem('ennui.v4.actif')"))
    sadia = api("/api/utilisateurs/moi", jeton=jeton)
    plan = api("/api/mes-plans", jeton=jeton)[0]
    malo = api("/api/utilisateurs", {"prenom": "Malo", "mot_de_passe": "demo-ofk-2026",
                                     "avatar": {"style": "micah", "seed": "malo-demo", "bg": "13382e"}})
    api("/api/amis", {"code": sadia["code"]}, jeton=malo["id"])
    api(f"/api/plans/{plan['id']}/participation", {"actif": True}, jeton=malo["id"])
    page.evaluate("dispatchEvent(new Event('focus'))")  # réveil de la synchro (comme au retour sur l'appli)
    g.pause(3.2)
    g.fermer_feuille()

    # Amis : profils de démo (Camille, Lucas), ajout en un geste
    g.toucher('#onglets [data-onglet="pour-vous"]', 1.8)
    g.toucher('[data-action="ouvrir-amis"]', 1.2)
    for code in ("Camille#101", "Lucas#214"):
        sel = f'[data-action="ajouter-ami"][data-code="{code}"]'
        try:
            page.locator(sel).first.wait_for(timeout=3000)
            g.toucher(sel, 0.9)
        except Exception:
            pass  # profil de démo absent de la liste
    g.pause(1.0)
    g.fermer_feuille()
    # la session apparaît dans « Watch-parties & sessions », avec les avatars réunis
    sessions = page.locator(".carte-session").first
    if sessions.count():
        sessions.scroll_into_view_if_needed()
    g.pause(3.0)


def convertir(webm, mp4):
    try:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("ffmpeg introuvable : la vidéo reste en .webm ->", webm)
        return webm
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(webm), "-c:v", "libx264", "-preset", "slow", "-crf", "17",
                    "-pix_fmt", "yuv420p", "-r", "30", "-movflags", "+faststart", str(mp4)], check=True)
    return mp4


def main():
    SORTIE.mkdir(exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="ofk-demo-"))
    serveur = lancer_serveur(tmp / "demo.sqlite3")
    try:
        with sync_playwright() as pw:
            nav = pw.chromium.launch(channel="chrome", headless=True)
            ctx = nav.new_context(viewport={"width": LARGEUR, "height": HAUTEUR}, device_scale_factor=ECHELLE,
                                  color_scheme="dark", locale="fr-FR", timezone_id="Europe/Paris",
                                  record_video_dir=str(tmp / "video"),
                                  record_video_size={"width": LARGEUR * ECHELLE, "height": HAUTEUR * ECHELLE})
            ctx.add_init_script(SCRIPT_POINT)
            page = ctx.new_page()
            debut = time.time()
            try:
                scenario(page, Geste(page))
            finally:
                video = page.video
                ctx.close()  # finalise le .webm
                nav.close()
            print(f"Scénario joué en {time.time() - debut:.0f} s")
            webm = SORTIE / "ofk_demo.webm"
            shutil.move(video.path(), webm)
        mp4 = convertir(webm, SORTIE / "ofk_demo.mp4")
        if mp4 != webm:
            webm.unlink()
        print("Vidéo :", mp4)
    finally:
        serveur.terminate()
        serveur.wait(timeout=10)
        shutil.rmtree(tmp, ignore_errors=True)  # base jetable : aucun compte de test ne reste


if __name__ == "__main__":
    main()
