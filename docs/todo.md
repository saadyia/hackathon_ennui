# Tâches et avancement

## À faire
- [ ] **Clé TMDB** dans `.env`, puis `enrich_tmdb.py` et `build_graph.py` : affiches des films et plateformes vérifiées (jamais testé contre la vraie API)
- [ ] Relancer `fetch_france.py` la veille de la démo (les événements vieillissent)
- [ ] Étendre la couverture des sorties (plus de villes, ou collecte à la demande autour de la ville choisie)
- [ ] Mettre en cache local les images si la démo doit tourner sans réseau
- [ ] Choisir et répéter le parcours de démo (docs/specs.md)
- [ ] Persister les « Intéressé » (SQLite) ; covoiturage / watch-party (P2)

## Fait
- [x] Moteur : PageRank personnalisé + restart biaisé, curseur par quota, < 20 ms (float32, itérations adaptatives)
- [x] Design mobile sobre, zéro émoji, 100 % local, 4 onglets
- [x] Ville libre (API Adresse) + rayon 5–50 km + filtre Haversine + distance sur chaque carte
- [x] 1 123 événements à venir dans 40 villes (OpenAgenda), occurrences réelles, horizons court / semaine / mois
- [x] Films et séries (Tout / Films / Séries), badge Film / Série
- [x] Plateformes strictement FR.flatrate via TMDB, aucune simulation ; « Disponibilité non vérifiée » sinon
- [x] « Déjà vu » qui affine en direct ; « Intéressé · X étudiants »

## Bloquants / questions ouvertes
- Clé TMDB à fournir (gratuite sur themoviedb.org).
