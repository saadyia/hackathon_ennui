# Spécifications fonctionnelles

## Contexte / problème
Campus excentrés, week-ends vides, isolement. Les étudiants ont souvent déjà des abonnements de streaming
mais tournent en rond (bulle de filtre), ou ignorent l'offre culturelle locale.

## Personas
- _à compléter (ex. étudiant·e en 1re année à Brest, sans voiture, qui a Netflix et rien de prévu samedi)_

## Écrans
1. **Accueil** (première ouverture) : « Qu'est-ce qu'on fait aujourd'hui ? »
   - Ville : n'importe quelle commune française (autocomplétion API Adresse), rayon 5–50 km (15 par défaut)
   - Types d'activités : Cinéma, Expositions & Musées, Concerts & Scène, Nature & Balades, Rencontres & Soirées
   - Genres favoris : Science-Fiction, Thriller, Drame, Comédie, Animation, Documentaire, Horreur, Action
   - Plateformes (abonnements) : Netflix, Prime Video, Disney+, Canal+, Arte, Apple TV+
   - Bouton « Découvrir ma sélection » (aucun choix n'est obligatoire)
2. **Pour vous** : carrousel « À l'écran ce soir » (films et séries), puis « Sortir · ville · rayon » avec sélecteur d'horizon
3. **Films & Séries** : bascule Tout / Films / Séries, grille d'affiches, badge Film / Série
4. **Sorties** : ville + rayon, horizon (Aujourd'hui / Ce week-end · Dans la semaine · Dans le mois), types, cartes avec distance et date exacte
5. **Profil** : mêmes préférences que l'accueil, liste des « Déjà vus » (retirer, ajouter par recherche), réinitialisation, sources

## User stories
- [P0] Je choisis mes préférences en moins de 20 s, puis je vois tout de suite une sélection.
- [P0] Le curseur fait évoluer la sélection en temps réel, des valeurs sûres aux pépites.
- [P0] « Déjà vu » retire l'œuvre et affine les recommandations suivantes.
- [P0] Je vois des sorties réelles à venir autour de ma ville (distance exacte), avec une date lisible et juste (« Ce soir · 20h30 », « En cours »), le lieu et le tarif.
- [P0] Je ne vois jamais un événement passé, ni un film annoncé sur une plateforme où il n'est pas.
- [P1] « Intéressé · X étudiants » me montre que d'autres étudiants y vont.
- [P2] Proposer covoiturage / watch-party aux étudiants intéressés.

## Parcours de démo
1. _à compléter_

## Hors périmètre
- Comptes utilisateurs et synchronisation entre appareils (l'état est dans le navigateur).
- Appels API externes à l'exécution (tout est pré-téléchargé).
