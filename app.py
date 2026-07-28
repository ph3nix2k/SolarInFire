import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from folium.plugins import MarkerCluster, HeatMap
import plotly.express as px
import glob
import math
import os
from geocoding import get_coordinates_batch

st.set_page_config(page_title="Dashboard Feux & Solaire", layout="wide")

@st.cache_data
def load_data():
    """Charge et prépare les données CSV, incluant le géocodage."""
    csv_files = glob.glob("data/NotebookLM_Feux_Solaire_Allege_*.csv")
    if not csv_files:
        st.error("Aucun fichier CSV trouvé dans le répertoire.")
        return pd.DataFrame()
    
    df_list = []
    for file in csv_files:
        try:
            df = pd.read_csv(file, dtype={'Code INSEE': str})
            df_list.append(df)
        except Exception as e:
            st.warning(f"Erreur lors de la lecture de {file} : {e}")
            
    if not df_list:
        return pd.DataFrame()
        
    df = pd.concat(df_list, ignore_index=True)
    
    df['Date_du_Feu'] = pd.to_datetime(df['Date_du_Feu'], format='mixed', errors='coerce', dayfirst=True)
    df['Premiere_Mise_en_Service'] = pd.to_datetime(df['Premiere_Mise_en_Service'], format='mixed', errors='coerce', dayfirst=True)
    df['Derniere_Mise_en_Service'] = pd.to_datetime(df['Derniere_Mise_en_Service'], format='mixed', errors='coerce', dayfirst=True)

    df['Annee_du_Feu'] = df['Date_du_Feu'].dt.year
    
    delta_days = (df['Premiere_Mise_en_Service'] - df['Date_du_Feu']).dt.days
    df['Delai_Mois'] = delta_days / 30.44
    
    df['Puissance_Totale_MW'] = df['Puissance_Totale_kW'] / 1000.0
    df['Surface_Brûlée_ha'] = df['Surface_Brûlée_m2'] / 10000.0
    
    df['Code INSEE'] = df['Code INSEE'].str.zfill(5)
    unique_codes = df['Code INSEE'].dropna().unique().tolist()
    coords_dict = get_coordinates_batch(unique_codes)
    
    df['lat'] = df['Code INSEE'].map(lambda code: coords_dict.get(code, (None, None))[0] if coords_dict.get(code) else None)
    df['lon'] = df['Code INSEE'].map(lambda code: coords_dict.get(code, (None, None))[1] if coords_dict.get(code) else None)
    
    df_clean = df.dropna(subset=['lat', 'lon']).copy()
    
    return df_clean

def get_color_category(delai):
    """Renvoie la catégorie et la couleur selon le délai en mois."""
    if pd.isna(delai):
        return 'Inconnu', 'lightgray'
    if delai < 0:
        return 'Pré-existant', 'gray'
    if delai < 12:
        return '< 1 an', 'red'
    elif delai <= 24:
        return '1 à 2 ans', 'orange'
    else:
        return '> 2 ans', 'green'

def main():
    st.title("🔥☀️ Dashboard : Feux de Forêt et Parcs Solaires")
    
    with st.spinner("Chargement des données et géocodage en cours..."):
        df = load_data()
        
    if df.empty:
        st.warning("Les données sont vides ou non trouvées.")
        return
        
    # Catégories de couleurs pré-calculées
    cat_col = df['Delai_Mois'].apply(get_color_category)
    df['Categorie_Delai'] = cat_col.apply(lambda x: x[0])
    df['Color_Delai'] = cat_col.apply(lambda x: x[1])
        
    # --- SIDEBAR: Logo & Titre ---
    logo_path = os.path.join(os.path.dirname(__file__), "assets", "logo.jpg")
    if os.path.exists(logo_path):
        col1, col2, col3 = st.sidebar.columns([1, 2, 1])
        with col2:
            st.image(logo_path, use_column_width=True)
    st.sidebar.markdown("---")
        
    # --- SIDEBAR: Filtres ---
    st.sidebar.header("🔍 Filtres")
    
    search_commune = st.sidebar.text_input("Rechercher une commune", "", placeholder="Ex: Bordeaux")
    
    # Année du Feu
    min_year = int(df['Annee_du_Feu'].min()) if not df['Annee_du_Feu'].isna().all() else 2020
    max_year = int(df['Annee_du_Feu'].max()) if not df['Annee_du_Feu'].isna().all() else 2025
    min_year, max_year = min(2020, min_year), max(2025, max_year)
    selected_year = st.sidebar.slider("Année du feu", min_value=min_year, max_value=max_year, value=(min_year, max_year))
    
    # Puissance
    min_p, max_p = float(df['Puissance_Totale_MW'].min()), float(df['Puissance_Totale_MW'].max())
    if pd.isna(min_p): min_p, max_p = 0.0, 1.0
    selected_puissance = st.sidebar.slider("Puissance Totale (MW)", min_value=min_p, max_value=max_p, value=(min_p, max_p))
    
    # Surface
    min_s, max_s = float(df['Surface_Brûlée_ha'].min()), float(df['Surface_Brûlée_ha'].max())
    if pd.isna(min_s): min_s, max_s = 0.0, 1.0
    selected_surface = st.sidebar.slider("Surface Brûlée (ha)", min_value=min_s, max_value=max_s, value=(min_s, max_s))
    
    # Délai Maximum
    max_delai = float(df['Delai_Mois'].max()) if not df['Delai_Mois'].isna().all() else 120.0
    if pd.isna(max_delai) or max_delai < 0: max_delai = 120.0
    selected_max_delai = st.sidebar.slider("Délai max M.E.S (mois)", min_value=0, max_value=int(math.ceil(max_delai)), value=int(math.ceil(max_delai)))
    
    # --- FILTRAGE ---
    mask = (
        (df['Annee_du_Feu'] >= selected_year[0]) & (df['Annee_du_Feu'] <= selected_year[1]) &
        (df['Puissance_Totale_MW'] >= selected_puissance[0]) & (df['Puissance_Totale_MW'] <= selected_puissance[1]) &
        (df['Surface_Brûlée_ha'] >= selected_surface[0]) & (df['Surface_Brûlée_ha'] <= selected_surface[1]) &
        ((df['Delai_Mois'] <= selected_max_delai) | (df['Delai_Mois'].isna()) | (df['Delai_Mois'] < 0)) 
    )
    
    if search_commune:
        mask = mask & df['Commune'].str.contains(search_commune, case=False, na=False)
        
    df_filtered = df[mask].copy()

    # --- COMPTEUR DYNAMIQUE POST-FEU ---
    nb_post_feu = len(df_filtered[df_filtered['Delai_Mois'] >= 0])
    st.sidebar.markdown("---")
    st.sidebar.metric("Parcs installés APRÈS un feu", f"{nb_post_feu:,}".replace(",", " "))
    
    # --- SIDEBAR: Paramètres Carte ---
    st.sidebar.markdown("---")
    st.sidebar.header("🗺️ Paramètres de la carte")
    map_type = st.sidebar.radio("Type d'affichage", ["Cercles (Top 1000)", "Regroupement (Cluster)", "Carte de chaleur (Heatmap)"])
    
    st.sidebar.info("💡 Vous pouvez désormais changer le fond de carte (Satellite) directement sur la carte, en haut à droite !")

    st.sidebar.markdown("---")
    st.sidebar.caption("v1.1.0")

    # =========================================================
    # LAYOUT PRINCIPAL (ONGLETS)
    # =========================================================
    tab_map, tab_analysis = st.tabs(["🗺️ Carte Interactive", "📊 Analyses Détaillées"])

    with tab_map:
        # --- CARTE FOLIUM ---
        m = folium.Map(location=[46.603354, 1.888334], zoom_start=6, tiles="CartoDB positron", name="Clair (CartoDB)")
        
        folium.TileLayer(
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            attr='Esri', name='Satellite (Esri)',
            overlay=False, control=True
        ).add_to(m)
        
        max_p_filtered = df_filtered['Puissance_Totale_kW'].max() if not df_filtered.empty else 1
        
        def get_tooltip(row):
            date_feu = row['Date_du_Feu'].strftime('%d/%m/%Y') if not pd.isna(row['Date_du_Feu']) else "Inconnue"
            date_mes = row['Premiere_Mise_en_Service'].strftime('%d/%m/%Y') if not pd.isna(row['Premiere_Mise_en_Service']) else "Inconnue"
            delai_str = f"{round(row['Delai_Mois'], 1)}" if not pd.isna(row['Delai_Mois']) else "N/A"
            
            return f"""
            <div style="font-family: Arial; font-size: 13px; width: 250px;">
                <b style="font-size: 15px;">{row['Commune']} ({row['Département']})</b><br/>
                <hr style="margin: 5px 0;">
                <b>Date du feu:</b> {date_feu}<br/>
                <b>Surface brûlée:</b> {round(row['Surface_Brûlée_ha'], 2)} ha<br/>
                <hr style="margin: 5px 0;">
                <b>Nb parcs solaires:</b> {row['Nombre_de_Parcs_Solaires']}<br/>
                <b>Puissance totale:</b> {round(row['Puissance_Totale_MW'], 2)} MW<br/>
                <b>1ère M.E.S:</b> {date_mes}<br/>
                <b>Délai:</b> {delai_str} mois<br/>
            </div>
            """
    
        if map_type == "Cercles (Top 1000)":
            MAX_POINTS = 1000
            df_render = df_filtered
            if len(df_filtered) > MAX_POINTS:
                st.warning(f"⚠️ Pour des raisons de fluidité, seuls les {MAX_POINTS} parcs les plus puissants sont affichés sur la carte. Utilisez le mode 'Regroupement' pour tout voir.")
                df_render = df_filtered.sort_values(by='Puissance_Totale_MW', ascending=False).head(MAX_POINTS)
                
            for _, row in df_render.iterrows():
                p = row['Puissance_Totale_kW']
                radius = 3 + 17 * (math.sqrt(p) / math.sqrt(max_p_filtered)) if (not pd.isna(p) and p > 0 and max_p_filtered > 0) else 4
                folium.CircleMarker(
                    location=[row['lat'], row['lon']], radius=radius,
                    color=row['Color_Delai'], fill=True, fill_color=row['Color_Delai'], fill_opacity=0.7, weight=1,
                    tooltip=folium.Tooltip(get_tooltip(row))
                ).add_to(m)
    
        elif map_type == "Regroupement (Cluster)":
            marker_cluster = MarkerCluster().add_to(m)
            for _, row in df_filtered.iterrows():
                folium.CircleMarker(
                    location=[row['lat'], row['lon']], radius=6,
                    color=row['Color_Delai'], fill=True, fill_color=row['Color_Delai'], fill_opacity=0.9, weight=1,
                    tooltip=folium.Tooltip(get_tooltip(row))
                ).add_to(marker_cluster)
    
        elif map_type == "Carte de chaleur (Heatmap)":
            heat_data = [[row['lat'], row['lon'], row['Puissance_Totale_MW']] for _, row in df_filtered.iterrows() if not pd.isna(row['Puissance_Totale_MW'])]
            HeatMap(heat_data, radius=15).add_to(m)
            
        # Légende HTML
        legend_html = '''
        <div style="position: fixed; bottom: 50px; left: 50px; width: 160px; height: 140px; 
                    border:2px solid grey; z-index:9999; font-size:12px; background-color:white; opacity: 0.9; padding: 10px;">
            <b>Délai Feu -> M.E.S</b><br>
            <i class="fa fa-circle" style="color:gray"></i> Pré-existant<br>
            <i class="fa fa-circle" style="color:red"></i> &lt; 1 an<br>
            <i class="fa fa-circle" style="color:orange"></i> 1 à 2 ans<br>
            <i class="fa fa-circle" style="color:green"></i> &gt; 2 ans<br>
            <i class="fa fa-circle" style="color:lightgray"></i> Inconnu
        </div>
        '''
        m.get_root().html.add_child(folium.Element(legend_html))
    
        # Ajout du contrôle de calques (pour basculer entre les fonds de carte)
        folium.LayerControl(position='topright').add_to(m)
    
        st_folium(m, use_container_width=True, height=850)

    with tab_analysis:
        st.markdown("### 📈 Vue d'ensemble")
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Communes impactées", f"{len(df_filtered):,}".replace(",", " "))
        col2.metric("Puissance Totale", f"{df_filtered['Puissance_Totale_MW'].sum():.1f} MW")
        col3.metric("Surface Brûlée", f"{df_filtered['Surface_Brûlée_ha'].sum():.1f} ha")
        
        valid_delays = df_filtered[df_filtered['Delai_Mois'] >= 0]['Delai_Mois']
        avg_delay = valid_delays.mean() if not valid_delays.empty else 0
        col4.metric("Délai moyen (si post-feu)", f"{avg_delay:.1f} mois")
        
        st.markdown("---")
        
        if not df_filtered.empty:
            c1, c2 = st.columns(2)
            
            with c1:
                delay_counts = df_filtered['Categorie_Delai'].value_counts().reset_index()
                delay_counts.columns = ['Catégorie', 'Nombre']
                color_map = {'Pré-existant': 'gray', '< 1 an': 'red', '1 à 2 ans': 'orange', '> 2 ans': 'green', 'Inconnu': 'lightgray'}
                
                fig_pie = px.pie(delay_counts, values='Nombre', names='Catégorie', title="Répartition des délais de construction", color='Catégorie', color_discrete_map=color_map, hole=0.4)
                fig_pie.update_layout(margin=dict(t=40, b=10, l=10, r=10), height=500)
                st.plotly_chart(fig_pie, use_container_width=True)
    
            with c2:
                df_filtered['Annee_MES'] = df_filtered['Premiere_Mise_en_Service'].dt.year
                df_valid_mes = df_filtered.dropna(subset=['Annee_MES']).copy()
                if not df_valid_mes.empty:
                    df_valid_mes['Annee_MES'] = df_valid_mes['Annee_MES'].astype(int)
                    mes_counts = df_valid_mes['Annee_MES'].value_counts().reset_index().sort_values('Annee_MES')
                    mes_counts.columns = ['Année', 'Nombre de parcs']
                    
                    fig_bar = px.bar(mes_counts, x='Année', y='Nombre de parcs', title="Mises en service par année")
                    fig_bar.update_layout(margin=dict(t=40, b=10, l=10, r=10), height=500)
                    st.plotly_chart(fig_bar, use_container_width=True)
                else:
                    st.info("Pas de données de mise en service pour générer le graphique temporel.")
        else:
            st.info("Aucune donnée pour afficher les analyses.")

    # --- SOURCES ---
    st.markdown("---")
    st.markdown("""
    <div style="color: gray; font-size: 14px;">
        <b>Sources des données (Open Data) :</b><br/>
        - <b>Feux de Forêts</b> : Base de Données sur les Incendies de Forêts en France (BDIFF) / Prométhée<br/>
        - <b>Parcs Solaires</b> : Registre National des installations de production d'électricité et de biogaz (ODRÉ)<br/>
        - <b>Géocodage</b> : API Géo (geo.api.gouv.fr)
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
