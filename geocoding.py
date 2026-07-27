import requests
import json
import os
import streamlit as st
import logging

CACHE_FILE = "cache_geo.json"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Erreur lors du chargement du cache : {e}")
            return {}
    return {}

def save_cache(cache_data):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Erreur lors de la sauvegarde du cache : {e}")

_GEO_CACHE = load_cache()

@st.cache_data
def get_coordinates_batch(codes_insee):
    """
    Récupère les coordonnées pour une liste de codes INSEE.
    Optimisation : télécharge la base complète des communes si des codes manquent.
    """
    global _GEO_CACHE
    
    results = {}
    codes_to_fetch = [code for code in codes_insee if code not in _GEO_CACHE]
    
    # Si on a des codes manquants, on télécharge la base entière (très rapide ~3Mo)
    # plutôt que de faire 1000 appels API individuels.
    if codes_to_fetch:
        logger.info(f"Chargement initial optimisé de toutes les communes (API gouv)...")
        try:
            url = "https://geo.api.gouv.fr/communes?fields=centre"
            response = requests.get(url, timeout=15)
            if response.status_code == 200:
                data = response.json()
                for commune in data:
                    code = commune.get("code")
                    centre = commune.get("centre")
                    if code and centre and "coordinates" in centre:
                        lon, lat = centre["coordinates"]
                        _GEO_CACHE[code] = [lat, lon]
                    elif code:
                        _GEO_CACHE[code] = None
                        
                # Marquer les codes toujours introuvables comme None pour ne pas les re-chercher
                for code in codes_to_fetch:
                    if code not in _GEO_CACHE:
                        _GEO_CACHE[code] = None
                        
                save_cache(_GEO_CACHE)
            else:
                logger.error(f"Erreur API ({response.status_code}) lors de la récupération globale.")
        except Exception as e:
            logger.error(f"Erreur de connexion à l'API : {e}")

    # Récupération depuis le cache (mis à jour)
    for code in codes_insee:
        val = _GEO_CACHE.get(code)
        results[code] = tuple(val) if val else None
        
    return results

def get_coordinates(code_insee):
    res = get_coordinates_batch([code_insee])
    return res.get(code_insee)
