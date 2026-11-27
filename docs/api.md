# Contrat d'API

- **URL de base :** même origine que le frontend
- **Format d'erreur :** `{"detail": "..."}` ; 422 si la validation échoue
- **Doc interactive :** `/docs` · **Statiques :** `/assets/*`

## `GET /api/sante`
`{"statut": "ok", "noeuds": 8706, "par_type": {...}, "plateformes_verifiees": false}`

## `GET /api/config`
`categories`, `genres` (`id` = genre MovieLens), `plateformes` (abonnements uniquement : Netflix 8, Prime Video 119,
Disney+ 337, Canal+ 381, Arte 234, Apple TV+ 350), `plateformes_verifiees` (au moins un titre vérifié par TMDB),
`horizons` (`court`, `semaine`, `mois`), `rayon` (`min` 5, `max` 50, `defaut` 15), `villes_couvertes`.

## `GET /api/communes?q=<texte>`
Proxy de `https://api-adresse.data.gouv.fr/search/?type=municipality&limit=5`, avec timeout de 3 s et cache.
`{"source": "api-adresse" | "local", "communes": [{"nom", "code_postal", "contexte", "lat", "lon"}]}`.
Hors ligne : préfixe parmi les villes couvertes.

## `GET /api/couverture?lat=&lon=`
Ville couverte la plus proche : `{"ville", "lat", "lon", "distance_km"}`. Utilisé quand une recherche de sorties est vide.

## `GET /api/oeuvres?q=<texte>`
Recherche de films et de séries (ajout de « Déjà vu » depuis le profil).

## `POST /api/recommandations`
```json
{ "type": "sortie", "genres": ["Sci-Fi"], "deja_vus": ["film:2571"], "decouverte": 0.3,
  "plateformes": [8, 119], "lat": 45.7772, "lon": 3.087, "rayon_km": 15,
  "horizon": "semaine", "categories": ["scene"], "k": 10 }
```
- `type` : `film` | `serie` | `tout` (2 films pour 1 série) | `sortie`
- `plateformes` : présence confirmée par TMDB (FR.flatrate) ; ignoré si `plateformes_verifiees` est faux
- `lat` / `lon` (optionnels) + `rayon_km` (5–50) : filtre Haversine des sorties
- `horizon` : `court` (aujourd'hui + week-end) | `semaine` | `mois`

Réponse : objets avec `id`, `type`, `titre`, `genres`, `affiche`, `resume`, `plateformes`, `plateformes_verifiees`,
`interesses`, `score`, `origine` (`confort` | `decouverte`), plus :
- **film / serie** : `annee` (+ `annee_fin`, `note`, `chaine`, `affiche_mini` pour les séries)
- **sortie** : `categorie`, `categorie_libelle`, `ville`, `lieu`, `adresse`, `lat`, `lon`, `acces`, `prix`, `tarif`,
  `date_debut` / `date_fin` (`YYYY-MM-DD`), `prochaine` (`{"debut", "fin"}` ISO Paris, dans la fenêtre demandée),
  `distance_km` (si `lat` / `lon`), `credit_image`, `url`

## `POST /api/interets`
`{"id": "sortie:oa-123", "actif": true}` → `{"id", "interesses"}`
