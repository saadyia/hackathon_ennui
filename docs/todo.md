# Tâches et avancement

## À faire
- [ ] **Affiches de films** : fournir une clé TMDB (`.env`), ou relancer `enrich_affiches.py` avec `ENNUI_CONTACT` (Wikimedia limite à environ 100 films sans contact)
- [ ] Relancer `enrich_affiches.py` (en pause pendant l'import des jeux, il reprend depuis son cache)
- [ ] Résumés français des livres : Google Books renvoie 429 sans clé (option `--google-books` prête)
- [ ] Vraie authentification si l'application sort du cadre de la démo
- [ ] Modération des sorties publiées (signalement, suppression par l'auteur)
- [ ] Choisir et répéter le parcours de démo, avec 2 ou 3 comptes

## Fait
- [x] Rendu final : typographie sans empattement (Plus Jakarta Sans / Inter / JetBrains Mono), logo vectoriel « ofk? » (splash, en-tête, icônes PWA), splash animé, accent unique champagne, pilule glissante et fondu 220 ms dans Chez soi, filtres contextuels, Co-op fusionné dans Multijoueur, « Mes envies », états vides avec « Réinitialiser les filtres », 6 905 synopsis FR de films
- [x] Budget corrigé (prix_num, coût marginal : plus jamais de liste vide), filtre « Temps disponible », « Choisir à ma place », nom « ofk ? »
- [x] Curseur continu 1 à 10, transitions glissées / en fondu, synopsis FR obligatoire (films, séries), extraits sur les cartes
- [x] PWA installable (manifest, service worker, icônes, balises Apple) ; Dockerfile + render.yaml ; écoute 0.0.0.0
- [x] Finitions : questionnaire réduit au profil durable, fiche détaillée (synopsis FR, adresse, badges), survol des cartes, fond bleu nuit, contrôle segmenté à 4 paliers, carte Leaflet des sorties, plus de message « disponibilités en vérification », zéro émoji garanti
- [x] Refonte design : Lucide, noUiSlider, Swiper, GSAP en local ; Inter / Plus Jakarta Sans / JetBrains Mono ; verre dépoli, halo, ratios stricts, bottom sheet détaillé
- [x] Catégories nettoyées (2 univers, 6 envies), thèmes de lecture avec curseur Confort ↔ Découverte, filtre machine et mode de jeu
- [x] Jeux vidéo : 3 279 jeux (2015+), consoles, genres et modes traduits, titres FR, résumés FR et jaquettes (Wikimedia), « Déjà joué », « Lancer une session », filtre Solo / Multijoueur
- [x] Livres : 2 500 livres GoodReads, genres traduits, éditions françaises (OpenLibrary), 100 % de couvertures, onglet Chez soi, « Déjà lu », club de lecture
- [x] Soirées & Concerts : catégorie dédiée, collecte nocturne par ville, villes des utilisateurs collectées à la demande
- [x] « Proposer une sortie » : publication par les utilisateurs, intégrée au graphe en ~1 s
- [x] Affiches : mode strict (≥ 90 %) ou prioritaire par type ; affiches de films sans clé via Wikidata + Wikipédia
- [x] Découverte niche + dépaysement, budget, comptes, plans collaboratifs, agenda synchronisé toutes les 6 h
- [x] Moteur < 20 ms avec 11 367 nœuds
