# Contrat d'API

- **URL de base :** même origine que le frontend
- **Format d'erreur :** `{"detail": "..."}` ; 422 si la validation échoue ; 401 si une route exige un compte
- **Compte :** en-tête `X-Utilisateur: <id>` (jeton renvoyé par `POST /api/utilisateurs`)
- **Doc interactive :** `/docs` · **Statiques :** `/assets/*`

## `GET /api/sante`
`{"statut": "ok", "noeuds": 8706, "par_type": {...}, "plateformes_verifiees": false}`

## `GET /api/config`
`categories` (sorties, dont `soirees`), `envies` (catégories + `livres` + `jeux`), `consoles`, `modes_jeu`, `genres` (`id` = genre MovieLens), `plateformes` (abonnements uniquement : Netflix 8, Prime Video 119,
Disney+ 337, Canal+ 381, Arte 234, Apple TV+ 350), `plateformes_verifiees` (au moins un titre vérifié par TMDB),
`horizons` (`maintenant`, `aujourdhui`, `weekend`, `semaine`, `mois`), `ambiances` (`festif`, `calme`, `drole`, `insolite`, `competitif`, `artistique`), `categories[].sorties` (faux pour `series` : envie d'écran, ignorée par le filtre des sorties), `rayon` (`min` 5, `max` 50, `defaut` 15), `villes_couvertes`.

## `GET /api/communes?q=<texte>`
Proxy de `https://api-adresse.data.gouv.fr/search/?type=municipality&limit=5`, avec timeout de 3 s et cache.
`{"source": "api-adresse" | "local", "communes": [{"nom", "code_postal", "contexte", "lat", "lon"}]}`.
Hors ligne : préfixe parmi les villes couvertes.

## `GET /api/couverture?lat=&lon=`
Ville couverte la plus proche : `{"ville", "lat", "lon", "distance_km"}`. Utilisé quand une recherche de sorties est vide.

## `GET /api/oeuvre?id=<identifiant>`
Fiche complète d'un seul nœud (même format qu'une recommandation). 404 si l'œuvre n'est plus au catalogue (sortie passée).
Sert à rouvrir un élément de « Mes envies » ou de « Mes plans » qui n'est pas dans la liste affichée.

## `GET /api/oeuvres?q=<texte>`
Recherche de films et de séries (ajout de « Déjà vu » depuis le profil).

## `POST /api/recommandations`
```json
{ "type": "sortie", "genres": ["Sci-Fi"], "deja_vus": ["film:2571"], "decouverte": 0.3,
  "plateformes": [8, 119], "lat": 45.7772, "lon": 3.087, "rayon_km": 15,
  "horizon": "semaine", "categories": ["scene"], "k": 10 }
```
- `type` : `film` | `serie` | `livre` | `jeu` | `tout` | `sortie`
- `consoles` (jeux) : `pc`, `mac`, `playstation`, `xbox`, `switch`, `mobile` ; `mode_jeu` : `tous` | `solo` | `multi` (`coop` = alias de `multi`)
- `duree` : `tout` | `express` | `soiree` | `long` ; `budget` : coût marginal (voir architecture)
- `themes` (livres) : `roman`, `polar`, `sff`, `essais`, `bd`, `bio`
- `categories` : envies de sorties `culture` | `soirees` | `nature` (les envies Chez soi sont ignorées pour les sorties)
- `ecrans` (type `tout`) : composition, par défaut `["film", "serie"]` ; ajouter `"livre"` (2 films, 1 série, 1 livre…)
- `plateformes` : présence confirmée par TMDB (FR.flatrate) ; ignoré si `plateformes_verifiees` est faux
- `lat` / `lon` (optionnels) + `rayon_km` (5–50) : filtre Haversine des sorties
- `horizon` : `maintenant` (+3 h) | `aujourdhui` | `weekend` | `semaine` | `mois` | `court` (aujourd'hui + week-end, anciens profils)
- `genres` : genres MovieLens et ambiances ; les ambiances ne servent qu'aux sorties
- `budget` : `tous` | `gratuit` | `moins10` | `moins25` (sorties : tarif connu ≤ plafond ; écrans : inclus sans surcoût)

Réponse : objets avec `id`, `type`, `titre`, `genres`, `affiche`, `resume`, `plateformes`, `plateformes_verifiees`,
`score`, `origine` (`confort` | `decouverte`), `etiquette` (`pepite` | `hors-piste` | `null`), `plans` (créneaux à venir), plus :
- **film / serie** : `annee` (+ `annee_fin`, `note`, `chaine`, `affiche_mini` pour les séries ; `source_affiche` pour les films)
- **livre** : `auteur`, `annee`, `pages`, `note`, `titre_original`, `francais` (édition française trouvée)
- **jeu** : `studio`, `editeur`, `annee`, `consoles`, `modes`, `genres_fr` (libellés français), `titre_original`
- **sortie** : `categorie`, `categorie_libelle`, `ville`, `lieu`, `adresse`, `lat`, `lon`, `acces`, `prix`, `tarif`,
  `date_debut` / `date_fin` (`YYYY-MM-DD`), `prochaine` (`{"debut", "fin"}` ISO Paris, dans la fenêtre demandée),
  `distance_km` (si `lat` / `lon`), `credit_image`, `url`

## Comptes
- `POST /api/utilisateurs` `{prenom, ville, prefs}` → `{id, prenom, ville, prefs, cree_le}`
- `GET /api/utilisateurs/moi` · `PUT /api/utilisateurs/moi` `{prenom, ville, prefs}` (compte requis) ; la réponse inclut `code`
  (« Prénom#123 », change avec le prénom) et `dispo` (statut actuel)
- `POST /api/utilisateurs/reprendre` `{code}` → compte complet (jeton compris) d'après le code « Prénom#123 » ;
  404 si inconnu ou profil de démo. Sert à « Reprendre un profil existant » (nouvel appareil, nouvelle adresse).
- `GET /api/utilisateurs/profils?q=` → profils réels (vue publique, sans jeton), les plus récents d'abord.
- `PUT /api/utilisateurs/moi/dispo` `{statut: indispo | sortir | distance}` : humeur du moment (Mode ermite, Partant pour bouger,
  Chill à distance), revient à `indispo` après 12 h
- `PUT /api/utilisateurs/moi/avatar` `{style: lorelei | micah, seed, bg: 1e293b | 27294a | 422b18 | 13382e | 351f47 | 293548,
  hair?, glasses?, mouth?, eyes?}` (valeurs DiceBear ; `glasses: "aucune"` pour forcer sans lunettes) ;
  `POST /api/utilisateurs` accepte aussi `avatar`. `avatar: null` = avatar déduit du prénom côté client.

## Synchronisation temps réel
- `GET /api/sync?v=<version>` (compte requis) : `{v, inchange: false, amis: [...], plans: [...], dispo}` ;
  si `v` est la version courante : `{v, inchange: true}` (~40 octets). Appelé toutes les 12 s par l'appli visible
  et au retour sur l'appli. `plans` = plans à venir où je suis inscrit ou un de mes amis (créés ou rejoints).
- Chaque plan (partout) contient aussi `cree_le` et `membres: [{prenom, avatar, moi}]` (jamais d'identifiant).

## Amis (compte requis ; un profil public = `{code, prenom, ville, dispo, demo, ami, avatar}`, jamais l'`id`)
- `GET /api/amis` → `{amis: [...], suggestions: [...]}` (amis triés : dispo pour sortir, à distance, indisponibles ; suggestions = profils de démo non ajoutés)
- `GET /api/amis/recherche?q=` : code exact (`Camille#101`, sans casse ni accents) ou début de prénom ; soi-même exclu ; 10 au plus
- `POST /api/amis` `{code}` : amitié immédiate et réciproque (404 si code inconnu) · `POST /api/amis/retirer` `{code}`

## Plans collaboratifs
Objet plan : `{id, oeuvre_id, oeuvre_titre, oeuvre_type, debut, rendez_vous, message, auteur, est_auteur, participants: [prénoms], je_participe, messages?}`
- `GET /api/plans?oeuvre_id=…` → plans à venir de l'œuvre, avec `messages: [{prenom, texte, cree_le}]`
- `POST /api/plans` `{oeuvre_id, debut, rendez_vous, message}` (compte requis ; `debut` sans fuseau = heure de Paris ; futur, ≤ 60 jours)
- `POST /api/plans/{id}/participation` `{actif: true|false}` (rejoindre / quitter)
- `POST /api/plans/{id}/messages` `{texte}` (≤ 280 caractères)
- `GET /api/mes-plans` → plans rejoints ou créés

## Sorties publiées par les utilisateurs
`POST /api/sorties` (compte requis) `{titre, categorie, lieu, ville: {nom, lat, lon}, debut, duree_h, prix, description}`
→ `{"id": "sortie:co-<id>"}`. `prix` : euros, 0 = gratuit, `null` = non précisé. Date dans les 60 jours.
La sortie apparaît dans les recommandations avec `source: "communaute"` et `propose_par` (prénom).

## `GET /api/plans/a-venir?limite=12`
Watch-parties, sessions et sorties à plusieurs à venir (toutes œuvres), avec `affiche` de l'œuvre : rangée « Watch-parties & sessions » de Pour vous.

## Agenda
- `GET /api/agenda` → `{derniere_sync, prochaine_sync, en_cours, statut: ok|erreur|jamais, message, automatique}`
- `POST /api/agenda/synchroniser` → lance une synchro en arrière-plan (ignoré si une synchro tourne ou date de moins de 2 min)
