# Architecture technique

## Vue d'ensemble
```mermaid
flowchart LR
  ML[(MovieLens CSV)] --> B[build_graph.py]
  TV[(TVmaze)] --> FS[fetch_series.py] --> SJ[(data/series.json)] --> B
  OA[(OpenAgenda via Opendatasoft)] --> FF[fetch_france.py] --> FJ[(data/france.json)] --> B
  TMDB[(TMDB, clé)] --> ET[enrich_tmdb.py] --> TJ[(data/tmdb.json)] --> B
  GR[(GoodReads CSV)] --> IB[import_books.py] --> LJ[(data/livres.json)] --> B
  OL[(OpenLibrary)] --> IB
  WM[(Wikidata + Wikipédia)] --> EA[enrich_affiches.py] --> AJ[(data/affiches.json)] --> B
  VG[(CSV jeux Wikidata)] --> IG[import_games.py] --> JJ[(data/jeux.json)] --> B
  WM --> IG
  B --> D[(data/processed : P.npz, pi_star.npy, noeuds.json)]
  D --> M[moteur.py] --> A[main.py FastAPI] --> F[frontend]
  AD[(API Adresse)] -. autocomplétion ville .-> A
  SC[scheduler.py : toutes les 6 h] -->|fetch_france.collecter + reconstruire_externes| D
  A <--> DB[(SQLite : comptes, plans, messages)]
```

## Composants
| Fichier | Rôle |
|---|---|
| `backend/fetch_france.py` | Événements **à venir** autour de 40 villes universitaires (rayon 15 km, 35 jours). Occurrences réelles `[début, fin]`, `date_debut` / `date_fin` en `YYYY-MM-DD` (Paris). Catégorisation, genres et tarif à partir des mots-clés du texte. |
| `backend/fetch_series.py` | 220 séries populaires (TVmaze) avec leurs identifiants IMDb et TVDB, pour TMDB. Aucune plateforme déduite. |
| `backend/enrich_tmdb.py` | Films (`/movie/{id}`) et séries (`/find` puis `/tv/{id}`) avec `append_to_response=watch/providers`. Lit **uniquement** `results.FR.flatrate`. Récupère aussi l'affiche, le titre FR et le résumé. Clé lue dans `TMDB_API_KEY` ou dans `.env`. |
| `backend/import_books.py` | 2 500 livres les plus lus (note ≥ 3,7, une édition par titre) du CSV GoodReads. Genres traduits. Édition française cherchée sur OpenLibrary (titre FR + couverture), sinon couverture GoodReads. |
| `backend/enrich_affiches.py` | Affiches de films sans clé : IMDb (MovieLens) → Wikidata (titre FR, article) → image principale Wikipédia (`pilicense=any`, ~250 px). |
| `backend/build_graph.py` | P (films + séries + sorties), π\*, `noeuds.json`. `plateformes_verifiees` vaut `true` seulement pour les titres présents dans `tmdb.json`. |
| `backend/moteur.py` | Vecteur de départ, marches, affinité, quota, masques (plateformes vérifiées, Haversine, fenêtres temporelles). |
| `backend/main.py` | Routes, proxy API Adresse, couverture, comptes, plans, agenda, service du frontend. Le moteur courant est dans `Catalogue.moteur` (remplacé d'un bloc après une synchro). |
| `backend/database.py` | SQLite (stdlib) : `utilisateurs`, `plans`, `participants`, `messages`, `meta`. Une connexion par opération, WAL. |
| `backend/scheduler.py` | `Synchroniseur` : boucle asyncio (6 h) + déclenchement manuel. Collecte OpenAgenda dans un thread, retire le passé, reconstruit le graphe, recharge le moteur. |

## Sorties (`france.json`)
- Requête OpenAgenda par ville : `within_distance(location_coordinates, POINT(lon lat), 15km)`, `lastdate_end >= now()`, `firstdate_begin <= now(days=35)`.
- On ne garde un événement que s'il a **au moins une occurrence non terminée** dans l'horizon. Exclus : annulés, emploi, petite enfance, culte, `age_max ≤ 14`.
- Sélection par ville : quota (120 pour Paris, 30 à 80 ailleurs), réparti à tour de rôle entre les 5 catégories (photo et date proche d'abord).
- Au total : **1 123 événements, dont 1 116 avec photo**. Il faut relancer `fetch_france.py` régulièrement, car les événements vieillissent.

## Filtres à l'exécution (`Moteur.autorises`)
- **Plateformes** (films, séries) : présence confirmée par TMDB sur au moins un abonnement de l'utilisateur. Sans aucune donnée TMDB, le filtre est **désactivé** et l'interface l'annonce.
  Ce n'est pas une supposition : sans données, on ne peut ni inclure ni exclure.
- **Distance** (sorties) : Haversine vectorisée `≤ rayon_km` autour de la ville choisie. La distance arrondie est renvoyée sur chaque carte.
- **Temps** (sorties) : au moins une occurrence intersecte la fenêtre de l'horizon, avec `fin ≥ maintenant`.
  - `court` : reste d'aujourd'hui + samedi 0h → lundi 0h (le week-end en cours si l'on est samedi ou dimanche)
  - `semaine` : maintenant → +7 jours ; `mois` : maintenant → +30 jours
- `prochaine_occurrence` : la première occurrence non terminée **dans la fenêtre**, avec ses vraies heures de début et de fin, ce qui permet d'afficher « En cours ».

## Affiches : sources et garanties
| Type | Source | Couverture |
|---|---|---|
| Films | TMDB w342 (clé) > Wikipédia (~250 px) | 1,3 % sans clé : **Wikimedia limite les scripts sans contact (429)**. iTunes Search renvoie 0 résultat pour les films (vérifié). |
| Séries | TMDB > TVmaze (~680 px) | 100 % |
| Livres | Édition FR OpenLibrary (L) > GoodReads | 100 % |
| Sorties | Photo OpenAgenda, sinon visuel sobre avec icône | 99 % |

Règle dans `Moteur` : si un type a au moins 90 % d'affiches, les œuvres sans affiche sont **exclues**. Sinon, leur score est ×0,3 (mise en avant des œuvres illustrées).
Avec une clé TMDB, ou une fois `enrich_affiches.py` terminé, les films passeront automatiquement en mode strict.

## Livres
- 2 500 nœuds `livre`, reliés comme les séries (15 films les plus proches par genres). Lift en confort, comme pour les autres nœuds externes.
- Genres GoodReads → genres de l'application (ex. « Science Fiction », « Dystopia » → SF ; « Nonfiction », « Biography » → Documentaire).
- Budget : un livre n'a pas de prix connu, il est donc exclu dès qu'un budget est demandé.
- Pas de traduction automatique : sans édition française trouvée, le titre reste en VO et aucun résumé n'est affiché.

## Jeux vidéo
- Filtre : `Type == "video game"`, sortie en 2015 ou après, fiche complète (plateformes, genres, studio, éditeur, URL) ;
  16 jeux à contenu adulte (eroge, bishōjo) exclus, soit **3 279 jeux**.
- Consoles regroupées : PC (Windows et Linux), Mac, PlayStation, Xbox, Nintendo Switch, Mobile (iOS et Android).
  Les consoles anciennes (3DS, Wii U…) sont ignorées.
- Genres : 309 genres anglais, traduits par environ 60 règles ordonnées vers une quarantaine de libellés français (RPG, Action-RPG,
  Tir à la première personne, Stratégie au tour par tour, Réflexion, Roman visuel…). Un genre non couvert est **ignoré**
  (119 jeux n'ont aucun genre affiché). Les termes d'usage dans la presse française sont conservés (RPG, Metroidvania, Roguelike, Battle royale).
- Modes : `solo` / `coop` / `multi` → badge « Solo » ou « Co-op / Multi » ; filtre `mode_jeu`.
- Données françaises, par lots : Wikidata `wbgetentities` (libellé FR, articles), extrait d'introduction de fr.wikipedia
  (2 phrases), jaquette = image principale de l'article anglais (`pilicense=any`).
- Graphe : chaque genre français est aussi associé à des genres de l'application (ex. RPG → Fantasy + Adventure) pour relier les jeux aux films.
- Budget : prix inconnu, donc exclus dès qu'un budget est demandé (comme les livres).

## Soirées & Concerts
- Catégorie `soirees` (concert, soirée, DJ, club, électro, festival, live, fête, karaoké, afterwork, open mic, blind test, jazz, rock, rap…).
  « Spectacles & Scène » regroupe désormais théâtre, danse, cirque et humour.
- Collecte : pour chaque ville, en plus de la requête générale, une requête OpenAgenda dédiée (`search(title_fr | keywords_fr, …)`), avec un quota de 25 soirées.
- Villes des utilisateurs hors couverture (> 20 km d'une ville connue) : collecte ciblée dès l'inscription, puis à chaque synchro.
- Sorties publiées par les utilisateurs (SQLite `sorties_communaute`) : intégrées au graphe (genres déduits du titre et de la catégorie), reconstruction à chaud en ~1 s.

## Découverte : niche et dépaysement
```
confort    = π_confort × aff                      aff = 0.15 + cos(genres, profil)
découverte = π_découverte / π* × q × (1 − 0.9 · s · m)
```
- `π_découverte / π*` : lift, ce qui est sur-représenté autour de l'utilisateur (**niche**).
- `m` = part des genres de l'œuvre qui sont des genres **cochés** (à défaut : genres des « Déjà vu »).
  `s` = position du curseur : à 10/10, une œuvre 100 % dans les genres cochés perd 90 % (**dépaysement**).
- `q` : plancher de qualité (films aimés par au moins 5 personnes) ; la marche garantit la cohérence avec les goûts.
- L'affinité ne s'applique **pas** à la découverte (elle annulerait le dépaysement).
- Étiquette : `pepite` si `m ≥ 0.5` (niche dans ses genres), sinon `hors-piste`.
- Mesuré (SF + Thriller) : à 0/10 Matrix et Star Wars ; à 10/10 Quest for Fire, Shadowlands, Forget Paris, tous « hors piste ».

## Budget
- Sorties : tarif publié inférieur ou égal au plafond (0, 10, 25 €). **Prix inconnu : exclu** (527 sorties sur 1 123 ont un tarif publié).
- Films et séries : un abonnement ne coûte rien de plus, donc tout budget autre que « Tous les prix » = inclus **sans surcoût**,
  c'est-à-dire confirmé par TMDB sur un abonnement coché ou sur Arte. Sans données TMDB : aucun résultat, et l'interface explique pourquoi.

## Espace collaboratif
- Plan = créneau (`debut`, heure de Paris) + point de rendez-vous ou lien + message, sur une œuvre. Le créateur est inscrit d'office.
- Le titre et le type de l'œuvre sont copiés dans le plan : il reste lisible si l'événement sort du catalogue.
- Plans visibles jusqu'à 6 h après leur début. Un plan sans plus aucun participant est supprimé.
- Chaque recommandation inclut `plans` (une requête SQL par lot) : « Ce soir · 22h00 · Avec Malo et toi ».
- Validation : créneau dans le futur (≤ 60 jours), rendez-vous ≤ 200 caractères, message ≤ 280. Un lien n'est cliquable que s'il commence par `https://`.

## Synchronisation de l'agenda
- Démarrage : tâche asyncio. Prochaine synchro = dernière + 6 h (date en SQLite `meta`, ou `genere_le` de `france.json`).
- Synchro : `collecter()` (~40 s), puis `retirer_passes()`, `ecrire()` (atomique), `reconstruire_externes()` (< 1 s, à partir de `S_films.npz`, sans MovieLens),
  puis `Catalogue.charger()`. Si le réseau échoue : nettoyage du passé et rechargement quand même ; le statut passe à « erreur ».
- Mesuré : 43 s au total, 0 coupure, 69 ms de latence au pire pendant la reconstruction. Bouton manuel limité à un clic toutes les 2 minutes.

## Graphe et moteur
- Films : co-occurrences MovieLens, élagage hybride (25 voisins par comptage + 25 par cosinus).
- Séries et sorties : reliées aux 30 films les plus proches selon `cos(genres) · log(1 + likes)`. Chaque film consacre au plus 15 % de sa ligne aux nœuds externes.
- 14 646 nœuds (7 363 films, 220 séries, 2 500 livres, 3 279 jeux, ~1 280 sorties), environ 364 k arêtes. Latence ~17 ms.
- Réglages de taille : 20 + 20 voisins par film (comptage + cosinus), 10 films par nœud externe, tolérance de la marche de 5 %.
  Mesuré : top 10 films stable (8 à 10 sur 10) par rapport aux réglages précédents.
- `v_u` : 25 films de référence par genre favori, plus les « Déjà vu » (60 % de la masse).
- Deux marches (Confort α = 0.10, Découverte α = 0.50 avec un restart biaisé π\*^-2 limité aux films du voisinage).
  Nombre d'itérations adaptatif, tel que (1-α)^n ≤ 4 %. Calcul en float32, comme P.
- Score × affinité de genres ; lift (÷ π\*) pour les séries et sorties ; curseur par quota ; dédoublonnage des titres.
- Type `tout` : les marches sont calculées une fois et partagées entre le classement des films et celui des séries (2 films pour 1 série).

## Décisions techniques
- **Pas de lieux permanents (OSM)** : la consigne impose des sorties datées. Un musée sans date ne rentre pas dans les horizons temporels.
- **Occurrences stockées avec leurs vraies heures** : une première version remplaçait le début d'une occurrence en cours par « maintenant ». On affichait alors « Ce soir · 20h28 » pour un concert commencé à 20h.
- **float32 + itérations adaptatives** : la latence était passée à 38 ms avec 1 123 sorties. Le mélange float32/float64 forçait une conversion à chaque produit.
- **Gratuit retiré des plateformes** : ce n'est pas un abonnement `flatrate`. Le tarif « Gratuit » des sorties reste affiché.

## Limites connues
- **Sans clé TMDB** : affiches typographiques pour les films, affiches TVmaze pour les séries, « Disponibilité non vérifiée » partout.
- **Couverture des sorties** : 40 villes. Ailleurs, l'application propose la ville couverte la plus proche (ex. Bourges → Orléans, 95 km).
- **Plafond de collecte** : 300 événements bruts par ville (Paris en a davantage). Le rayon de 50 km ne voit que ce qui a été collecté à 15 km des villes.
- **Comptes sans mot de passe** : n'importe qui connaissant un jeton peut agir en son nom. Acceptable pour une démo, pas pour une mise en production.
- **Découverte des séries et sorties à 10/10** : les résultats « hors piste » se ressemblent d'un profil à l'autre (petit catalogue).
