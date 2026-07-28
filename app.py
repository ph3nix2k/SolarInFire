import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import glob
import math
from geocoding import get_coordinates_batch

st.set_page_config(page_title="Dashboard Feux & Solaire", layout="wide")

@st.cache_data
def load_data():
    """Charge et prépare les données CSV, incluant le géocodage."""
    # Trouver tous les fichiers CSV dans le dossier data/
    csv_files = glob.glob("data/NotebookLM_Feux_Solaire_Allege_*.csv")
    if not csv_files:
        st.error("Aucun fichier CSV trouvé dans le répertoire.")
        return pd.DataFrame()
    
    # Concaténer les fichiers
    df_list = []
    for file in csv_files:
        try:
            # S'assurer de charger le code INSEE comme une string pour préserver les zéros initiaux
            df = pd.read_csv(file, dtype={'Code INSEE': str})
            df_list.append(df)
        except Exception as e:
            st.warning(f"Erreur lors de la lecture de {file} : {e}")
            
    if not df_list:
        return pd.DataFrame()
        
    df = pd.concat(df_list, ignore_index=True)
    
    # Traitement des dates : format mixte YYYY-MM-DD / DD/MM/YYYY
    # to_datetime avec format mixed est très pratique sur Pandas récent
    df['Date_du_Feu'] = pd.to_datetime(df['Date_du_Feu'], format='mixed', errors='coerce', dayfirst=True)
    df['Premiere_Mise_en_Service'] = pd.to_datetime(df['Premiere_Mise_en_Service'], format='mixed', errors='coerce', dayfirst=True)
    df['Derniere_Mise_en_Service'] = pd.to_datetime(df['Derniere_Mise_en_Service'], format='mixed', errors='coerce', dayfirst=True)

    # Année du feu (pour le filtre)
    df['Annee_du_Feu'] = df['Date_du_Feu'].dt.year
    
    # Calcul du délai en mois (30.44 jours par mois en moyenne)
    delta_days = (df['Premiere_Mise_en_Service'] - df['Date_du_Feu']).dt.days
    df['Delai_Mois'] = delta_days / 30.44
    
    # Géocodage
    # Formater le code INSEE sur 5 caractères au cas où
    df['Code INSEE'] = df['Code INSEE'].str.zfill(5)
    
    unique_codes = df['Code INSEE'].dropna().unique().tolist()
    coords_dict = get_coordinates_batch(unique_codes)
    
    # Appliquer lat/lon
    df['lat'] = df['Code INSEE'].map(lambda code: coords_dict.get(code, (None, None))[0] if coords_dict.get(code) else None)
    df['lon'] = df['Code INSEE'].map(lambda code: coords_dict.get(code, (None, None))[1] if coords_dict.get(code) else None)
    
    # Éliminer les données non géolocalisables
    df_clean = df.dropna(subset=['lat', 'lon']).copy()
    
    return df_clean

def get_color(delai):
    """Renvoie une couleur selon le délai en mois."""
    if pd.isna(delai) or delai < 0:
        return 'gray'
    if delai < 12:
        return 'red'
    elif delai <= 24:
        return 'orange'
    else:
        return 'green'

def main():
    st.title("🔥☀️ Dashboard : Feux de Forêt et Parcs Solaires en France")
    
    with st.spinner("Chargement des données et géocodage en cours..."):
        df = load_data()
        
    if df.empty:
        st.warning("Les données sont vides ou non trouvées.")
        return
        
    # --- SIDEBAR: Filtres ---
    st.sidebar.header("Filtres")
    
    # 1. Année du Feu
    min_year = int(df['Annee_du_Feu'].min()) if not df['Annee_du_Feu'].isna().all() else 2020
    max_year = int(df['Annee_du_Feu'].max()) if not df['Annee_du_Feu'].isna().all() else 2025
    # Assurons-nous que la plage demandée (2020-2025) soit au moins couverte
    min_year = min(2020, min_year)
    max_year = max(2025, max_year)
    
    selected_year = st.sidebar.slider("Année du feu", min_value=min_year, max_value=max_year, value=(min_year, max_year))
    
    # 2. Puissance
    min_puissance = float(df['Puissance_Totale_kW'].min()) if not df['Puissance_Totale_kW'].empty else 0.0
    max_puissance = float(df['Puissance_Totale_kW'].max()) if not df['Puissance_Totale_kW'].empty else 1000.0
    selected_puissance = st.sidebar.slider(
        "Puissance Totale (kW)", 
        min_value=min_puissance, 
        max_value=max_puissance, 
        value=(min_puissance, max_puissance)
    )
    
    # 3. Surface
    min_surface = float(df['Surface_Brûlée_m2'].min()) if not df['Surface_Brûlée_m2'].empty else 0.0
    max_surface = float(df['Surface_Brûlée_m2'].max()) if not df['Surface_Brûlée_m2'].empty else 10000.0
    selected_surface = st.sidebar.slider(
        "Surface Brûlée (m²)", 
        min_value=min_surface, 
        max_value=max_surface, 
        value=(min_surface, max_surface)
    )
    
    # 4. Délai Maximum
    # Filtre sur le délai. On permet d'aller jusqu'au max délai présent.
    max_delai_data = float(df['Delai_Mois'].max()) if not df['Delai_Mois'].isna().all() else 120.0
    if pd.isna(max_delai_data) or max_delai_data < 0:
        max_delai_data = 120.0
        
    selected_max_delai = st.sidebar.slider(
        "Délai max avant 1ère Mise en Service (mois)", 
        min_value=0, 
        max_value=int(math.ceil(max_delai_data)), 
        value=int(math.ceil(max_delai_data))
    )
    
    # --- FILTRAGE DES DONNEES ---
    mask = (
        (df['Annee_du_Feu'] >= selected_year[0]) & (df['Annee_du_Feu'] <= selected_year[1]) &
        (df['Puissance_Totale_kW'] >= selected_puissance[0]) & (df['Puissance_Totale_kW'] <= selected_puissance[1]) &
        (df['Surface_Brûlée_m2'] >= selected_surface[0]) & (df['Surface_Brûlée_m2'] <= selected_surface[1]) &
        # Garder les points où le délai est inférieur au max, ET ceux où le délai n'a pas pu être calculé
        ((df['Delai_Mois'] <= selected_max_delai) | (df['Delai_Mois'].isna()) | (df['Delai_Mois'] < 0)) 
    )
    
    df_filtered = df[mask].copy()
    
    st.write(f"Nombre de communes correspondantes : **{len(df_filtered)}** / {len(df)}")
    
    # Sécurité pour ne pas faire crasher le navigateur avec 10000 points SVG :
    MAX_POINTS = 1000
    if len(df_filtered) > MAX_POINTS:
        st.warning(f"⚠️ Pour des raisons de fluidité, seuls les {MAX_POINTS} parcs les plus puissants sont affichés sur la carte.")
        df_filtered = df_filtered.sort_values(by='Puissance_Totale_kW', ascending=False).head(MAX_POINTS)
        
    # --- CARTE FOLIUM ---
    # Coordonnées pour centrer sur la France
    m = folium.Map(location=[46.603354, 1.888334], zoom_start=6, tiles="CartoDB positron")
    
    # Référence pour la taille des points (normalisation par rapport au max affiché)
    max_p_filtered = df_filtered['Puissance_Totale_kW'].max()
    
    for _, row in df_filtered.iterrows():
        p = row['Puissance_Totale_kW']
        # Calcul de la taille du marqueur (Surface ~ Puissance, donc rayon ~ sqrt(Puissance))
        if pd.isna(p) or p <= 0:
            radius = 3
        else:
            if max_p_filtered > 0:
                # Echelle entre 3 et 20
                radius = 3 + 17 * (math.sqrt(p) / math.sqrt(max_p_filtered))
            else:
                radius = 5
                
        color = get_color(row['Delai_Mois'])
        
        # Formatage propre des dates
        date_feu = row['Date_du_Feu'].strftime('%d/%m/%Y') if not pd.isna(row['Date_du_Feu']) else "Inconnue"
        date_mes = row['Premiere_Mise_en_Service'].strftime('%d/%m/%Y') if not pd.isna(row['Premiere_Mise_en_Service']) else "Inconnue"
        
        delai_str = f"{round(row['Delai_Mois'], 1)}" if not pd.isna(row['Delai_Mois']) else "N/A"
        
        # Construction du tooltip
        tooltip_html = f"""
        <div style="font-family: Arial; font-size: 13px; width: 250px;">
            <b style="font-size: 15px;">{row['Commune']} ({row['Département']})</b><br/>
            <hr style="margin: 5px 0;">
            <b>Date du feu:</b> {date_feu}<br/>
            <b>Surface brûlée:</b> {row['Surface_Brûlée_m2']} m²<br/>
            <hr style="margin: 5px 0;">
            <b>Nb parcs solaires:</b> {row['Nombre_de_Parcs_Solaires']}<br/>
            <b>Puissance totale:</b> {row['Puissance_Totale_kW']} kW<br/>
            <b>1ère M.E.S:</b> {date_mes}<br/>
            <b>Délai:</b> {delai_str} mois<br/>
        </div>
        """
        
        folium.CircleMarker(
            location=[row['lat'], row['lon']],
            radius=radius,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.7,
            weight=1,
            tooltip=folium.Tooltip(tooltip_html)
        ).add_to(m)
        
    # Ajout d'une légende HTML directement dans la carte
    legend_html = '''
    <div style="position: fixed; 
                bottom: 50px; left: 50px; width: 160px; height: 120px; 
                border:2px solid grey; z-index:9999; font-size:12px;
                background-color:white; opacity: 0.9; padding: 10px;">
        <b>Délai Feu -> M.E.S</b><br>
        <i class="fa fa-circle" style="color:red"></i> &lt; 1 an<br>
        <i class="fa fa-circle" style="color:orange"></i> 1 à 2 ans<br>
        <i class="fa fa-circle" style="color:green"></i> &gt; 2 ans<br>
        <i class="fa fa-circle" style="color:gray"></i> Inconnu / Négatif
    </div>
    '''
    m.get_root().html.add_child(folium.Element(legend_html))

    # Rendu Streamlit de la carte Folium
    st_folium(m, use_container_width=True, height=700)

if __name__ == "__main__":
    main()
