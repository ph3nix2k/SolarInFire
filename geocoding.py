import requests
import json
import os
import streamlit as st
import logging
import time
import pandas as pd

CACHE_FILE = "data/geocoding_cache.json"

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

# Load INSEE global cache
_INSEE_CACHE = {}
def get_insee_dict():
    global _INSEE_CACHE
    if _INSEE_CACHE: return _INSEE_CACHE
    try:
        url = "https://geo.api.gouv.fr/communes?fields=centre"
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            for commune in response.json():
                code = commune.get("code")
                centre = commune.get("centre")
                if code and centre and "coordinates" in centre:
                    _INSEE_CACHE[code] = (centre["coordinates"][1], centre["coordinates"][0]) # lat, lon
    except Exception as e:
        logger.error(f"INSEE API Error: {e}")
    return _INSEE_CACHE

def overpass_geocode(insee_code, retries=3):
    """Niveau 1: Requete Overpass API pour les gros parcs solaires."""
    query = f'''
    [out:json];
    area["ref:INSEE"="{insee_code}"]->.a;
    nwr["power"="generator"]["generator:source"="solar"](area.a);
    out center;
    '''
    url = "https://overpass-api.de/api/interpreter"
    headers = {"User-Agent": "Antigravity-SolarInFire/1.0"}
    
    for attempt in range(retries):
        try:
            resp = requests.post(url, data=query.encode('utf-8'), headers=headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                elements = data.get("elements", [])
                if elements:
                    el = elements[0]
                    if "center" in el:
                        return el["center"]["lat"], el["center"]["lon"]
                    elif "lat" in el and "lon" in el:
                        return el["lat"], el["lon"]
                return None # Aucun parc trouvé, on passe au fallback
            elif resp.status_code in [429, 504]:
                logger.warning(f"Overpass API busy ({resp.status_code}). Retrying {attempt+1}/{retries}...")
                time.sleep(3 ** attempt) # Exponential backoff plus long
            else:
                logger.warning(f"Overpass API error {resp.status_code}")
                return None
        except Exception as e:
            logger.warning(f"Overpass request failed: {e}")
            time.sleep(2)
            
    return None

def geocode_row(row, iris_dict):
    """
    Stratégie 3 niveaux:
    1. Overpass (si > 1000 kW)
    2. IRIS (depuis iris_dict local)
    3. INSEE (depuis api.gouv.fr centralisé)
    """
    global _GEO_CACHE
    
    insee = str(row.get('Code INSEE')).zfill(5)
    iris = str(row.get('codeIRIS')) if not pd.isna(row.get('codeIRIS')) else None
    
    try:
        puissance = float(row.get('Puissance_kW')) if not pd.isna(row.get('Puissance_kW')) else 0
    except ValueError:
        puissance = 0
        
    nom = str(row.get('Nom_du_Parc_Solaire'))
    
    cache_key = f"{insee}_{nom}_{iris}"
    
    if cache_key in _GEO_CACHE:
        val = _GEO_CACHE[cache_key]
        return val[0], val[1] if val else (None, None)
        
    lat, lon = None, None
    
    # Niveau 1: Overpass (Grand parc)
    if puissance > 1000:
        logger.info(f"Geocoding {nom} (>1000kW) via Overpass...")
        coords = overpass_geocode(insee)
        if coords:
            lat, lon = coords
            
    # Niveau 2: IRIS
    if lat is None and lon is None and iris and iris != "nan":
        if iris in iris_dict:
            lat, lon = iris_dict[iris]
            
    # Niveau 3: INSEE (Mairie)
    if lat is None and lon is None:
        insee_dict = get_insee_dict()
        if insee in insee_dict:
            lat, lon = insee_dict[insee]
            
    _GEO_CACHE[cache_key] = [lat, lon] if lat and lon else None
    
    return lat, lon if lat and lon else (None, None)

def flush_cache():
    save_cache(_GEO_CACHE)
