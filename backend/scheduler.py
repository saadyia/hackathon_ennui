"""
Synchronisation automatique de l'agenda (tâche de fond asyncio lancée au démarrage de FastAPI).

Toutes les INTERVALLE (6 h), ou à la demande :
  1. interroge OpenAgenda (fetch_france.collecter) dans un thread, sans bloquer le serveur ;
     si le réseau échoue, on garde les sorties existantes ;
  2. retire les occurrences et événements terminés ;
  3. reconstruit le graphe à chaud (build_graph.reconstruire_externes, < 1 s, sans MovieLens)
     puis remplace le moteur en mémoire : les requêtes en cours finissent sur l'ancien,
     les suivantes utilisent le nouveau. Aucune coupure.

Désactivable avec la variable d'environnement ENNUI_SYNC=0 (tests, démo hors ligne).
"""

import asyncio
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

try:
    from . import build_graph, database, fetch_france
except ImportError:
    import build_graph, database, fetch_france

INTERVALLE = timedelta(hours=6)
DELAI_MIN_MANUEL = timedelta(minutes=2)  # anti-double-clic sur « Mettre à jour »
log = logging.getLogger("ennui.agenda")


class Synchroniseur:
    def __init__(self, recharger: Callable[[], int]):
        """recharger : recharge le moteur depuis le disque, renvoie le nb de sorties."""
        self.recharger = recharger
        self.verrou = asyncio.Lock()
        self.en_cours = False
        self.derniere: Optional[datetime] = self._lire_derniere()
        self.statut = "ok" if self.derniere else "jamais"
        self.message: Optional[str] = None
        self.tache: Optional[asyncio.Task] = None

    @staticmethod
    def _lire_derniere() -> Optional[datetime]:
        valeur = database.lire_meta("agenda_derniere_sync")
        if not valeur:  # première exécution : date de génération du fichier versionné
            fichier = build_graph.charger_json("france.json", {})
            valeur = fichier.get("genere_le")
        return datetime.fromisoformat(valeur) if valeur else None

    def etat(self) -> dict:
        prochaine = (self.derniere + INTERVALLE) if self.derniere else None
        return {
            "derniere_sync": self.derniere.isoformat() if self.derniere else None,
            "prochaine_sync": prochaine.isoformat() if prochaine else None,
            "en_cours": self.en_cours,
            "statut": self.statut,
            "message": self.message,
            "automatique": os.environ.get("ENNUI_SYNC", "1") != "0",
        }

    def _synchroniser_bloquant(self) -> str:
        """Exécuté dans un thread : réseau + reconstruction du graphe."""
        t0 = time.perf_counter()
        try:
            donnees = fetch_france.collecter(journal=log.info)
            source = "OpenAgenda"
        except Exception as e:  # réseau ou format : on nettoie simplement l'existant
            log.warning("OpenAgenda injoignable (%s) : sorties existantes conservées", e)
            donnees = build_graph.charger_json("france.json")
            source = None
        retires = fetch_france.retirer_passes(donnees)
        fetch_france.ecrire(donnees)
        build_graph.reconstruire_externes(journal=log.info)
        n = len(donnees["sorties"])
        duree = time.perf_counter() - t0
        if source is None:
            raise RuntimeError(f"Agenda injoignable : {n} sorties conservées, {retires} passées retirées")
        return f"{n} sorties à venir, {retires} passées retirées ({duree:.0f} s)"

    async def synchroniser(self, manuel: bool = False) -> dict:
        if self.en_cours:
            return self.etat()
        if manuel and self.derniere and datetime.now(timezone.utc) - self.derniere < DELAI_MIN_MANUEL:
            self.message = "Déjà à jour"
            return self.etat()
        async with self.verrou:
            self.en_cours = True
            try:
                self.message = await asyncio.to_thread(self._synchroniser_bloquant)
                self.statut = "ok"
            except Exception as e:
                self.statut = "erreur"
                self.message = str(e)
                log.warning("Synchronisation : %s", e)
            finally:
                # même en cas d'échec réseau, le nettoyage a eu lieu : on recharge
                try:
                    self.recharger()
                except Exception as e:  # le moteur précédent reste en place
                    log.error("Rechargement du moteur impossible : %s", e)
                self.derniere = datetime.now(timezone.utc)
                database.ecrire_meta("agenda_derniere_sync", self.derniere.isoformat())
                self.en_cours = False
        return self.etat()

    async def boucle(self):
        while True:
            attente = INTERVALLE.total_seconds()
            if self.derniere:
                attente = max(30.0, (self.derniere + INTERVALLE - datetime.now(timezone.utc)).total_seconds())
            await asyncio.sleep(attente)
            await self.synchroniser()

    def demarrer(self):
        if os.environ.get("ENNUI_SYNC", "1") == "0":
            log.info("Synchronisation automatique désactivée (ENNUI_SYNC=0)")
            return
        self.tache = asyncio.create_task(self.boucle())

    async def arreter(self):
        if self.tache:
            self.tache.cancel()
            try:
                await self.tache
            except asyncio.CancelledError:
                pass
