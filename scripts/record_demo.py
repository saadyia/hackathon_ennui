"""
Vidéo de démonstration de « ofk? » (format iPhone 390 x 844, rendu x2), environ 2 minutes.

    python3 -m pip install --user playwright imageio-ffmpeg   # une fois (Chrome du Mac utilisé, rien à télécharger)
    python3 scripts/record_demo.py   # -> demo_output/ofk_demo.mp4 (1920 x 1080, iPhone centré, fond studio, 105-110 s)
                                     #    demo_output/ofk_demo_vertical.mp4 (780 x 1688, écran seul)
                                     #    demo_output/check_framing.png (contrôle du cadrage)

- Lance son propre serveur FastAPI (port 8010) sur une base SQLite JETABLE (ENNUI_DB) et sans synchro de
  l'agenda : aucun compte de test ne reste dans la vraie base.
- Un point tactile translucide suit chaque déplacement, clic et défilement.
- Un second compte réel (« Malo ») rejoint en direct le créneau proposé : la synchro temps réel de
  l'application (toast, avatars des participants) est filmée telle quelle, rien n'est simulé à l'écran.
"""

import base64
import json
import os
import re
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
VITESSE = 1.0   # multiplie toutes les pauses
CIBLE_S, MIN_S, MAX_S = 108.0, 105.0, 110.0  # durée finale visée (1 min 48)

# Point tactile : suit la souris, s'agrandit au clic. pointer-events:none, au-dessus de tout.
SCRIPT_POINT = """
(() => {
  const css = `#__doigt{position:fixed;left:0;top:0;width:34px;height:34px;margin:-17px 0 0 -17px;border-radius:50%;
    background:rgba(255,255,255,.28);border:1.5px solid rgba(255,255,255,.75);box-shadow:0 0 18px rgba(255,255,255,.25);
    pointer-events:none;z-index:2147483647;transition:transform .18s cubic-bezier(.2,.9,.3,1.4),opacity .25s;opacity:0}
    #__doigt.appui{transform:scale(.72);background:rgba(232,217,181,.45)}`;
  const go = () => {
    document.documentElement.style.overflowX = "hidden";
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
    # ENNUI_SANS_SENSIBLE : aucune affiche suggestive pendant la vidéo (filtre réservé à la démo)
    env = {**os.environ, "ENNUI_SYNC": "0", "ENNUI_DB": str(base), "ENNUI_SANS_SENSIBLE": "1"}
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

    def aller(self, x, y, duree=0.26):
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
            self.p.wait_for_timeout(60)
        return el.bounding_box()

    def toucher(self, sel, pause=0.35, dx=0.5, dy=0.5, trajet=None):
        b = self.boite(sel)
        self.aller(b["x"] + b["width"] * dx, b["y"] + b["height"] * dy, *( [trajet] if trajet else []))
        self.pause(0.07)
        self.p.mouse.down(); self.pause(0.07); self.p.mouse.up()
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
CHAPITRES = []  # (nom, instant de début) : durée réelle de chaque séquence, affichée à la fin


def chapitre(nom):
    CHAPITRES.append((nom, time.time()))


def scenario(page, g, camera):
    # 1. 0:00 – 0:15 · Splash, inscription, avatar en 2 gestes
    page.goto(URL + "/", wait_until="commit")
    camera.demarrer()
    chapitre("1. Splash et inscription")
    g.pause(1.8)                                       # splash animé « ofk? »
    g.toucher('[data-action="c-est-parti"]', 0.4)
    g.taper("#champ-prenom", "Sadia", delai=45)
    g.toucher('[data-action="avatar-aleatoire"]', 0.45)   # personnage et fond : 2 gestes
    g.toucher('[data-action="avatar-aleatoire"]', 0.45)
    g.taper("#mdp-inscription", "demo-ofk-2026", delai=25)
    g.taper("#champ-ville", "Rennes", delai=45)
    g.toucher('#suggestions-ville [data-action="choisir-ville"]', 0.3)
    b = g.boite("#rayon")
    g.glisser(b["x"] + b["width"] * 0.22, b["y"] + b["height"] / 2, b["x"] + b["width"] * 0.45, 0.5)
    # genres « grand public », aux visuels irréprochables devant un jury
    for genre in ("Sci-Fi", "Adventure", "Thriller", "Animation", "Comedy", "Documentary"):
        sel = f'[data-action="pref"][data-groupe="genres"][data-valeur=\'"{genre}"\']'
        if page.locator(sel).count():
            g.toucher(sel, 0.0, trajet=0.16)
    for pf in (8, 119):  # Netflix, Prime Video
        sel = f'[data-action="pref"][data-groupe="plateformes"][data-valeur="{pf}"]'
        if page.locator(sel).count():
            g.toucher(sel, 0.0, trajet=0.16)
    g.toucher('[data-action="commencer"]', 0.5)

    # 2. 0:15 – 0:25 · Pour vous + curseur 2 -> 8 + défilement 3 s
    page.locator(".rangee-affiches .carte-oeuvre").first.wait_for(timeout=20000)
    chapitre("2. Pour vous et curseur")
    verifier_cadrage(page)
    g.pause(0.8)
    g.curseur(2, 8, duree=2.2)
    g.pause(0.6)
    g.defiler(1100, 3.0)
    g.defiler(-1100, 0.9)

    # 3. 0:25 – 0:42 · Ce soir, au chaud
    chapitre("3. Ce soir au chaud")
    g.toucher('#onglets [data-onglet="ecrans"]', 0.8)
    for seg in ("ecrans", "livre", "jeu"):
        g.toucher(f'[data-action="segment"][data-valeur="{seg}"]', 1.1)
        g.defiler(360, 0.6); g.pause(0.2); g.defiler(-360, 0.35)
    g.toucher('[data-action="mode-jeu"][data-valeur="multi"]', 0.9)
    g.toucher('.grille-affiches .carte-oeuvre [data-action="ouvrir-plans"]', 1.1)
    g.defiler(380, 0.9, ".feuille-corps"); g.pause(0.5)
    g.fermer_feuille()

    # 4. 0:42 – 1:02 · Hors écran : Tout (4 s), Créatif, Cuisine (recette), Mouvement, curseur 9
    chapitre("4. Hors écran")
    g.toucher('#onglets [data-onglet="hors-ecran"]', 3.2)
    g.toucher('[data-action="segment-hors"][data-valeur="creatif"]', 1.3)
    g.toucher('[data-action="segment-hors"][data-valeur="cuisine"]', 0.8)
    g.curseur(None, 9, duree=1.2)
    g.pause(0.6)
    g.toucher(".grille-activites .carte-activite h3", 1.0)
    g.defiler(520, 1.2, ".feuille-corps"); g.pause(0.9)
    g.defiler(560, 1.2, ".feuille-corps"); g.pause(0.9)
    g.fermer_feuille()
    g.toucher('[data-action="segment-hors"][data-valeur="mouvement"]', 1.4)

    # 5. 1:02 – 1:20 · Sorties : culture, soirées, nature (distances, réservation)
    chapitre("5. Sorties")
    g.toucher('#onglets [data-onglet="sorties"]', 1.2)
    for seg in ("culture", "soirees", "nature"):
        g.toucher(f'[data-action="segment-sorties"][data-valeur="{seg}"]', 1.0)
        g.defiler(820, 1.2); g.pause(1.1); g.defiler(-820, 0.5)

    # 6. 1:20 – 1:48 · Choisir à ma place, créneau, un ami qui rejoint en direct, amis de démo
    chapitre("6. Tirage, créneau et amis")
    g.toucher('[data-action="choisir-pour-moi"]', 2.2)  # tirage ~500 ms puis fiche « Sélectionné pour vous »
    g.defiler(700, 1.3, ".feuille-corps"); g.pause(0.3)
    g.taper("#champ-rdv", "Devant l'entrée", delai=40)
    g.taper('#form-plan [name="message"]', "On y va ensemble ?", delai=40)
    g.toucher('#form-plan button[type="submit"]', 1.2)

    # Malo (vrai second compte, base jetable) devient ami et rejoint le créneau ; l'appli le voit à la synchro
    jeton = json.loads(page.evaluate("localStorage.getItem('ennui.v4.actif')"))
    sadia = api("/api/utilisateurs/moi", jeton=jeton)
    plan = api("/api/mes-plans", jeton=jeton)[0]
    malo = api("/api/utilisateurs", {"prenom": "Malo", "mot_de_passe": "demo-ofk-2026",
                                     "avatar": {"style": "micah", "seed": "malo-demo", "bg": "13382e"}})
    api("/api/amis", {"code": sadia["code"]}, jeton=malo["id"])
    api(f"/api/plans/{plan['id']}/participation", {"actif": True}, jeton=malo["id"])
    page.evaluate("dispatchEvent(new Event('focus'))")  # réveil de la synchro (comme au retour sur l'appli)
    g.pause(2.6)
    g.fermer_feuille()

    # Amis : profils de démo (Camille, Lucas), ajout en un geste
    g.toucher('#onglets [data-onglet="pour-vous"]', 1.2)
    g.toucher('[data-action="ouvrir-amis"]', 0.9)
    for code in ("Camille#101", "Lucas#214"):
        sel = f'[data-action="ajouter-ami"][data-code="{code}"]'
        try:
            page.locator(sel).first.wait_for(timeout=2000)
            g.toucher(sel, 0.7)
        except Exception:
            pass  # profil de démo absent de la liste
    g.fermer_feuille()
    # la session apparaît dans « Watch-parties & sessions », avec les avatars réunis
    sessions = page.locator(".carte-session").first
    if sessions.count():
        sessions.scroll_into_view_if_needed()
    g.pause(2.6)
    chapitre("fin")


# ------------------------------------------------------------------ #
# Capture : screencast Chrome (CDP) en pixels réels x2                 #
# ------------------------------------------------------------------ #
# L'enregistreur vidéo de Playwright filme en pixels CSS : avec device_scale_factor=2, la page n'occupait que le
# quart haut-gauche d'une vidéo 780 x 1688 (cadrage coupé). Le screencast CDP renvoie au contraire des images
# 780 x 1688 nettes, horodatées, assemblées ensuite par ffmpeg à 30 i/s.
class Camera:
    def __init__(self, page, dossier: Path):
        self.dossier = dossier
        self.dossier.mkdir(parents=True, exist_ok=True)
        self.images = []  # (horodatage en s, chemin)
        self.cdp = page.context.new_cdp_session(page)
        self.cdp.on("Page.screencastFrame", self._image)

    def _image(self, ev):
        chemin = self.dossier / f"{len(self.images):06d}.jpg"
        chemin.write_bytes(base64.b64decode(ev["data"]))
        self.images.append((ev["metadata"]["timestamp"], chemin))
        self.cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]})

    def demarrer(self):
        self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92, "everyNthFrame": 1,
                                               "maxWidth": LARGEUR * ECHELLE, "maxHeight": HAUTEUR * ECHELLE})

    def arreter(self):
        self.cdp.send("Page.stopScreencast")

    def duree(self, fin=1.5):
        return self.images[-1][0] - self.images[0][0] + fin

    def liste_concat(self, fichier: Path, fin=1.5, facteur=1.0):
        """Fichier concat ffmpeg : chaque image dure jusqu'à la suivante (Chrome n'envoie que les changements).
        facteur < 1 accélère uniformément (calage de la durée totale)."""
        lignes = []
        for (t, chemin), suivant in zip(self.images, self.images[1:] + [(None, None)]):
            duree = ((suivant[0] - t) if suivant[0] else fin) * facteur
            lignes += [f"file '{chemin}'", f"duration {max(duree, 0.001):.4f}"]
        lignes.append(f"file '{self.images[-1][1]}'")  # requis par le démultiplexeur concat
        fichier.write_text("\n".join(lignes) + "\n")


def verifier_cadrage(page):
    """Capture test + contrôle : en-tête « ofk? », contenu et barre d'onglets entièrement dans le cadre, sans débordement."""
    page.screenshot(path=str(SORTIE / "check_framing.png"))
    m = page.evaluate("""() => {
        const r = (s) => { const b = document.querySelector(s)?.getBoundingClientRect(); return b && [b.left, b.top, b.right, b.bottom]; };
        return { vw: innerWidth, vh: innerHeight, sw: document.documentElement.scrollWidth,
                 marque: r('.marque'), contenu: r('#ecran'), onglets: r('#onglets') }; }""")
    dedans = lambda b: b and b[0] >= -0.5 and b[2] <= m["vw"] + 0.5 and b[1] >= -0.5 and b[3] <= m["vh"] + 0.5
    ok = (m["vw"], m["vh"]) == (LARGEUR, HAUTEUR) and m["sw"] <= LARGEUR and dedans(m["marque"]) and dedans(m["onglets"]) \
        and m["contenu"] and m["contenu"][0] >= -0.5 and m["contenu"][2] <= LARGEUR + 0.5
    print(f"Cadrage : viewport {m['vw']}x{m['vh']}, largeur du document {m['sw']} px, en-tête {m['marque']}, "
          f"onglets {m['onglets']} -> {'OK' if ok else 'PROBLÈME'} (demo_output/check_framing.png)")
    if not ok:
        raise SystemExit("Cadrage incorrect : enregistrement interrompu.")


def ffmpeg_exe():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return shutil.which("ffmpeg") or sys.exit("ffmpeg introuvable : python3 -m pip install --user imageio-ffmpeg")


def video_verticale(ffmpeg, concat: Path, mp4: Path):
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(concat),
                    "-vf", f"scale={LARGEUR * ECHELLE}:{HAUTEUR * ECHELLE}:flags=lanczos:out_range=tv,fps=30,format=yuv420p",
                    "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", str(mp4)], check=True)


def decor_16_9(dossier: Path, W=1920, H=1080, ph=960):
    """Fond studio #070A12, téléphone centré (bord vitré, reflet léger), masque d'écran aux coins arrondis."""
    from PIL import Image, ImageDraw, ImageFilter
    pw = round(ph * LARGEUR / HAUTEUR)
    x, y = (W - pw) // 2, (H - ph) // 2
    bord, rayon = 13, 58
    fond = Image.new("RGB", (W, H), "#070A12")
    halo = Image.new("L", (W, H), 0)
    ImageDraw.Draw(halo).ellipse([x - 420, y - 120, x + pw + 420, y + ph + 160], fill=70)
    fond = Image.composite(Image.new("RGB", (W, H), "#141a2a"), fond, halo.filter(ImageFilter.GaussianBlur(170)))
    ombre = Image.new("L", (W, H), 0)
    ImageDraw.Draw(ombre).rounded_rectangle([x - bord, y - bord + 26, x + pw + bord, y + ph + bord + 26], rayon + bord, fill=200)
    fond = Image.composite(Image.new("RGB", (W, H), "#020305"), fond, ombre.filter(ImageFilter.GaussianBlur(38)))
    d = ImageDraw.Draw(fond)
    d.rounded_rectangle([x - bord, y - bord, x + pw + bord, y + ph + bord], rayon + bord, fill="#1a1f2b", outline="#3a4152", width=2)
    d.rounded_rectangle([x - 3, y - 3, x + pw + 3, y + ph + 3], rayon + 3, fill="#000000")
    fond.save(dossier / "fond.png")
    masque = Image.new("L", (pw, ph), 0)
    ImageDraw.Draw(masque).rounded_rectangle([0, 0, pw - 1, ph - 1], rayon, fill=255)
    masque.save(dossier / "masque.png")
    # reflet vitré : bande diagonale très douce sur tout le téléphone
    reflet = Image.new("RGBA", (W, H), (255, 255, 255, 0))
    bande = Image.new("L", (W, H), 0)
    ImageDraw.Draw(bande).polygon([(x - 40, y + ph * 0.05), (x + pw * 0.55, y - 40), (x + pw * 0.78, y - 40), (x - 40, y + ph * 0.38)], fill=16)
    zone = Image.new("L", (W, H), 0)
    ImageDraw.Draw(zone).rounded_rectangle([x - bord, y - bord, x + pw + bord, y + ph + bord], rayon + bord, fill=255)
    from PIL import ImageChops
    reflet.putalpha(ImageChops.multiply(bande.filter(ImageFilter.GaussianBlur(30)), zone))
    reflet.save(dossier / "reflet.png")
    return pw, ph, x, y


def duree_video(ffmpeg, mp4: Path) -> float:
    sortie = subprocess.run([ffmpeg, "-i", str(mp4)], capture_output=True, text=True).stderr
    h, m, s = re.search(r"Duration: (\d+):(\d+):([\d.]+)", sortie).groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


def video_16_9(ffmpeg, verticale: Path, mp4: Path, dossier: Path):
    """Cadre iPhone centré sur 1920 x 1080. Durée bornée (-t) : les images fixes en boucle ne s'arrêtent pas d'elles-mêmes."""
    pw, ph, x, y = decor_16_9(dossier)
    duree = duree_video(ffmpeg, verticale)
    filtre = (f"[1:v]scale={pw}:{ph}:flags=lanczos,format=rgba[ecran];[2:v]format=gray[m];"
              f"[ecran][m]alphamerge[tel];[0:v][tel]overlay={x}:{y}:shortest=1[v1];"
              f"[v1][3:v]overlay=0:0:shortest=1,format=yuv420p[v]")
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-loop", "1", "-i", str(dossier / "fond.png"), "-i", str(verticale),
                    "-loop", "1", "-i", str(dossier / "masque.png"), "-loop", "1", "-i", str(dossier / "reflet.png"),
                    "-filter_complex", filtre, "-map", "[v]", "-t", f"{duree:.2f}", "-r", "30",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "17",
                    "-movflags", "+faststart", str(mp4)], check=True)


def main():
    SORTIE.mkdir(exist_ok=True)
    if "--16x9" in sys.argv:  # refaire seulement la version 16:9 à partir de la verticale
        with tempfile.TemporaryDirectory() as d:
            video_16_9(ffmpeg_exe(), SORTIE / "ofk_demo_vertical.mp4", SORTIE / "ofk_demo.mp4", Path(d))
        return print("Vidéo :", SORTIE / "ofk_demo.mp4")
    tmp = Path(tempfile.mkdtemp(prefix="ofk-demo-"))
    serveur = lancer_serveur(tmp / "demo.sqlite3")
    try:
        with sync_playwright() as pw:
            nav = pw.chromium.launch(channel="chrome", headless=True,
                                     args=[f"--window-size={LARGEUR},{HAUTEUR}", "--hide-scrollbars"])
            ctx = nav.new_context(viewport={"width": LARGEUR, "height": HAUTEUR}, screen={"width": LARGEUR, "height": HAUTEUR},
                                  device_scale_factor=ECHELLE, color_scheme="dark", locale="fr-FR", timezone_id="Europe/Paris")
            ctx.add_init_script(SCRIPT_POINT)
            page = ctx.new_page()
            camera = Camera(page, tmp / "images")
            debut = time.time()
            try:
                scenario(page, Geste(page), camera)
            finally:
                camera.arreter()
                ctx.close()
                nav.close()
            print(f"Scénario joué en {time.time() - debut:.0f} s, {len(camera.images)} images capturées")
        ffmpeg = ffmpeg_exe()
        brute = camera.duree()
        # chronologie réelle de chaque séquence
        for (nom, t0), (_, t1) in zip(CHAPITRES, CHAPITRES[1:]):
            print(f"  {nom:<30} {t1 - t0:5.1f} s")
        # calage : si la prise sort de 105–110 s, accélération ou ralenti uniforme vers 108 s (borné à ±20 %)
        facteur = 1.0 if MIN_S <= brute <= MAX_S else CIBLE_S / brute
        if not 0.8 <= facteur <= 1.2:
            print(f"Attention : prise de {brute:.1f} s, trop loin de {CIBLE_S:.0f} s pour être calée sans se voir.")
            facteur = min(1.2, max(0.8, facteur))
        if facteur != 1.0:
            print(f"Prise brute {brute:.1f} s -> calage x{1 / facteur:.3f}")
        camera.liste_concat(tmp / "images.txt", facteur=facteur)
        verticale = SORTIE / "ofk_demo_vertical.mp4"
        video_verticale(ffmpeg, tmp / "images.txt", verticale)
        finale = SORTIE / "ofk_demo.mp4"
        video_16_9(ffmpeg, verticale, finale, tmp)
        d = duree_video(ffmpeg, finale)
        print(f"Vidéo : {finale} (1920 x 1080) · durée {d:.2f} s -> {'OK' if MIN_S <= d <= MAX_S else 'HORS CIBLE'} "
              f"(cible {MIN_S:.0f}–{MAX_S:.0f} s) ; écran seul : {verticale}")
    finally:
        serveur.terminate()
        serveur.wait(timeout=10)
        shutil.rmtree(tmp, ignore_errors=True)  # base jetable et images : aucun compte de test ne reste


if __name__ == "__main__":
    main()
