# Tâches et avancement

## À faire
- [ ] **Clé TMDB** dans `.env`, puis `enrich_tmdb.py` et `build_graph.py` : affiches des films, plateformes vérifiées, budget « Gratuit » pour les écrans
- [ ] Vraie authentification si l'application sort du cadre de la démo (aujourd'hui : jeton sans mot de passe)
- [ ] Notifications quand quelqu'un rejoint un plan
- [ ] Étendre la couverture des sorties (plus de villes, ou collecte à la demande autour de la ville choisie)
- [ ] Choisir et répéter le parcours de démo (docs/specs.md), avec 2 ou 3 comptes

## Fait
- [x] Moteur : PageRank personnalisé + restart biaisé, curseur par quota, < 20 ms
- [x] Découverte = niche + dépaysement (malus progressif jusqu'à -90 % sur les genres cochés), étiquettes Pépite / Hors piste
- [x] Budget : Tous, Gratuit, < 10 €, < 25 € (sorties : tarif publié ; écrans : inclus sans surcoût, vérifié TMDB)
- [x] Connexion express (prénom + ville), comptes SQLite, changement de compte en 1 clic
- [x] Plans collaboratifs : rejoindre, proposer un créneau, rendez-vous ou lien, messages, « Mes plans »
- [x] Synchronisation OpenAgenda toutes les 6 h + bouton manuel, graphe reconstruit à chaud sans coupure
- [x] Ville libre + rayon + Haversine, horizons temporels, films et séries, plateformes strictement FR.flatrate
- [x] Plus aucune donnée simulée (compteurs remplacés par de vrais participants)

## Bloquants / questions ouvertes
- Clé TMDB à fournir (gratuite sur themoviedb.org).
