// Service worker minimal : rend l'application installable (iOS, Android) et garde la coquille hors ligne.
// - page et code de l'appli : réseau d'abord (jamais de version périmée en développement), cache en secours
// - librairies, polices, icônes : cache d'abord (fichiers figés)
// - API : toujours le réseau (données fraîches, comptes, plans)
const VERSION = "ofk-v17";  // bouton « Mettre à jour » masqué quand la synchro est coupée
const COQUILLE = [
  "/", "/assets/app.css", "/assets/app.js", "/assets/avatar.js", "/manifest.json", "/vendor/dicebear/core.js", "/vendor/dicebear/lorelei.js", "/vendor/dicebear/micah.js",
  "/vendor/lucide.min.js", "/vendor/nouislider.min.js", "/vendor/nouislider.min.css",
  "/vendor/swiper-bundle.min.js", "/vendor/swiper-bundle.min.css", "/vendor/gsap.min.js",
  "/vendor/leaflet/leaflet.js", "/vendor/leaflet/leaflet.css",
  "/assets/fonts/plus-jakarta-sans-latin.woff2", "/assets/fonts/inter-latin.woff2", "/assets/fonts/jetbrains-mono-latin.woff2",
  "/icons/icone-192.png", "/icons/icone-512.png", "/icons/apple-touch-icon.png", "/icons/logo-ofk.svg",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(COQUILLE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys()
    .then((cles) => Promise.all(cles.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin || url.pathname.startsWith("/api/")) return;
  const fige = /^\/(vendor|icons)\//.test(url.pathname) || url.pathname.startsWith("/assets/fonts/");
  if (fige) {
    e.respondWith(caches.match(e.request).then((r) => r || fetch(e.request).then((rep) => {
      const copie = rep.clone();
      caches.open(VERSION).then((c) => c.put(e.request, copie));
      return rep;
    })));
    return;
  }
  e.respondWith(fetch(e.request).then((rep) => {
    const copie = rep.clone();
    caches.open(VERSION).then((c) => c.put(e.request, copie));
    return rep;
  }).catch(() => caches.match(e.request).then((r) => r || caches.match("/"))));
});
