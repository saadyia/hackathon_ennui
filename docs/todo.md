# Tâches et avancement

## À faire
- [ ] **Affiches de films** : fournir une clé TMDB (`.env`), ou relancer `enrich_affiches.py` avec `ENNUI_CONTACT` (Wikimedia limite à environ 100 films sans contact)
- [ ] Résumés français des livres : Google Books renvoie 429 sans clé (option `--google-books` prête)
- [ ] Vraie authentification si l'application sort du cadre de la démo
- [ ] Modération des sorties publiées (signalement, suppression par l'auteur)
- [ ] Choisir et répéter le parcours de démo, avec 2 ou 3 comptes

## Fait
- [x] Livres : 2 500 livres GoodReads, genres traduits, éditions françaises (OpenLibrary), 100 % de couvertures, onglet Chez soi, « Déjà lu », club de lecture
- [x] Soirées & Concerts : catégorie dédiée, collecte nocturne par ville, villes des utilisateurs collectées à la demande
- [x] « Proposer une sortie » : publication par les utilisateurs, intégrée au graphe en ~1 s
- [x] Affiches : mode strict (≥ 90 %) ou prioritaire par type ; affiches de films sans clé via Wikidata + Wikipédia
- [x] Découverte niche + dépaysement, budget, comptes, plans collaboratifs, agenda synchronisé toutes les 6 h
- [x] Moteur < 20 ms avec 11 367 nœuds
