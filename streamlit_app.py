import os
import random
import numpy as np
import pandas as pd
import geopandas as gpd
import pydeck as pdk
import streamlit as st

# ----------------------------------------------------------
# PAGE CONFIG
# ----------------------------------------------------------
st.set_page_config(
    page_title="Andok's Site Selection – Bulacan",
    layout="wide",
)

st.title("Andok's Site Selection – Bulacan (Per Barangay Prototype)")

st.markdown(
    """
This dashboard displays **barangay-level suitability scores** across **Bulacan**,  
using the exact **SLD styling**, competitor locations, and Google Satellite basemap.
"""
)

# ----------------------------------------------------------
# CONSTANTS
# ----------------------------------------------------------

BARANGAY_SHP_PATH = "data/bulacanbarangay.shp"

BRGY_NAME_COL = "ADM4_EN"
CITYMUN_COL = "ADM3_EN"
SCORE_COL = "mean_0"

# Competitors (Google Sheet CSV URL stored in secrets)
COMPETITORS_SHEET_CSV_URL = st.secrets.get("competitors", {}).get("sheet_csv_url", "")

# Exact sheet columns you provided:
COMP_LONG = "longtitude"
COMP_LAT = "latitude"
COMP_BRAND = "brand"

# ----------------------------------------------------------
# LOAD BARANGAYS
# ----------------------------------------------------------

@st.cache_data(show_spinner=True)
def load_barangays(path):
    gdf = gpd.read_file(path)

    # Ensure WGS84 CRS
    if gdf.crs is None or gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)

    # Validate columns
    required = [BRGY_NAME_COL, CITYMUN_COL, SCORE_COL]
    for col in required:
        if col not in gdf.columns:
            st.error(f"Missing column '{col}' in barangay shapefile.")
            st.stop()

    gdf["barangay_name"] = gdf[BRGY_NAME_COL].astype(str)
    gdf["citymun_name"] = gdf[CITYMUN_COL].astype(str)
    gdf["score"] = pd.to_numeric(gdf[SCORE_COL], errors="coerce")

    gdf = gdf[~gdf.geometry.isna()]
    return gdf

gdf_barangays = load_barangays(BARANGAY_SHP_PATH)


# ----------------------------------------------------------
# LOAD COMPETITORS FROM GOOGLE SHEET
# ----------------------------------------------------------

@st.cache_data(show_spinner=True)
def load_competitors(sheet_url):
    if not sheet_url:
        return pd.DataFrame()

    try:
        # Let pandas detect delimiter automatically
        df = pd.read_csv(sheet_url, sep=None, engine="python")
    except Exception as e:
        st.warning(f"Could not load competitors data: {e}")
        return pd.DataFrame()

    expected_cols = [COMP_LONG, COMP_LAT, COMP_BRAND]
    for col in expected_cols:
        if col not in df.columns:
            st.warning(f"Competitors sheet missing column '{col}'. Columns found: {df.columns.tolist()}")
            return pd.DataFrame()

    df["lon"] = pd.to_numeric(df[COMP_LONG], errors="coerce")
    df["lat"] = pd.to_numeric(df[COMP_LAT], errors="coerce")
    df["brand"] = df[COMP_BRAND].astype(str)

    df = df.dropna(subset=["lat", "lon"])
    return df


df_competitors = load_competitors(COMPETITORS_SHEET_CSV_URL)


# ----------------------------------------------------------
# SLD STYLING FUNCTION
# ----------------------------------------------------------

def sld_color(mean_0):
    if mean_0 is None:
        return [200, 200, 200, 150]

    if 1.02915619443098993 <= mean_0 <= 1.67021351760768:
        return [215, 25, 28, 150]
    elif 1.67021351760768 < mean_0 <= 2.11293581101225003:
        return [232, 91, 59, 150]
    elif 2.11293581101225003 < mean_0 <= 2.47597288754775002:
        return [249, 157, 89, 150]
    elif 2.47597288754775002 < mean_0 <= 2.85005666392968982:
        return [254, 201, 129, 150]
    elif 2.85005666392968982 < mean_0 <= 3.18201286704618003:
        return [255, 237, 171, 150]
    elif 3.18201286704618003 < mean_0 <= 3.52431534195362017:
        return [235, 247, 173, 150]
    elif 3.52431534195362017 < mean_0 <= 3.92996775043785984:
        return [196, 230, 135, 150]
    elif 3.92996775043785984 < mean_0 <= 4.44667928886414021:
        return [150, 210, 101, 150]
    elif 4.44667928886414021 < mean_0 <= 5.04817327088676038:
        return [88, 180, 83, 150]
    elif 5.04817327088676038 < mean_0 <= 6.22406019477859029:
        return [26, 150, 65, 150]
    else:
        return [200, 200, 200, 150]


gdf_barangays["fill_color"] = gdf_barangays["score"].apply(sld_color)


# ----------------------------------------------------------
# RANDOM COLORS FOR COMPETITOR BRANDS
# ----------------------------------------------------------

def random_color():
    return [random.randint(0,255), random.randint(0,255), random.randint(0,255), 230]

if not df_competitors.empty:
    brands = df_competitors["brand"].unique().tolist()
    brand_color_map = {b: random_color() for b in brands}
    df_competitors["color"] = df_competitors["brand"].map(brand_color_map)


# ----------------------------------------------------------
# SIDEBAR FILTERS
# ----------------------------------------------------------

st.sidebar.header("Filters")

city_list = sorted(gdf_barangays["citymun_name"].unique())
city_choice = ["All"] + city_list

selected_city = st.sidebar.selectbox("Municipality / City", city_choice)

gdf_filtered = gdf_barangays.copy()
if selected_city != "All":
    gdf_filtered = gdf_filtered[gdf_filtered["citymun_name"] == selected_city]


# ----------------------------------------------------------
# BUILD THE MAP
# ----------------------------------------------------------

centroid = gdf_filtered.geometry.unary_union.centroid

view_state = pdk.ViewState(
    latitude=centroid.y,
    longitude=centroid.x,
    zoom=11,
    pitch=0,
)

# Google Satellite Layer
tile_layer = pdk.Layer(
    "TileLayer",
    data=None,
    minZoom=0,
    maxZoom=19,
    tileSize=256,
    url_template="https://mt1.google.com/vt/lyxrs=s&x={x}&y={y}&z={z}".replace("lyxrs","lyrs"),
)

barangay_layer = pdk.Layer(
    "GeoJsonLayer",
    data=gdf_filtered,
    pickable=True,
    filled=True,
    stroked=True,
    get_fill_color="fill_color",
    get_line_color=[50, 50, 50, 180],
    get_line_width=1,
    auto_highlight=True,
)

layers = [tile_layer, barangay_layer]

# Competitors ABOVE polygons
if not df_competitors.empty:
    competitor_layer = pdk.Layer(
        "ScatterplotLayer",
        data=df_competitors,
        get_position="[lon, lat]",
        get_fill_color="color",
        get_radius=90,
        pickable=True,
    )
    layers.append(competitor_layer)

tooltip = {
    "html": (
        "<b>{barangay_name}</b>, {citymun_name}<br/>"
        "Score: <b>{score}</b>"
    ),
    "style": {"backgroundColor": "steelblue", "color": "white"},
}

deck = pdk.Deck(
    layers=layers,
    initial_view_state=view_state,
    tooltip=tooltip,
    map_style=None,
)

st.subheader("Barangay Suitability Map (Styled using SLD)")
st.pydeck_chart(deck)


# ----------------------------------------------------------
# SUMMARY TABLES
# ----------------------------------------------------------

st.subheader("Municipality Summary")

summary = (
    gdf_barangays.groupby("citymun_name")["score"]
    .agg(["count", "mean", "min", "max"])
    .reset_index()
)

st.dataframe(summary, use_container_width=True)

st.subheader("Barangay Ranking")
rank_table = gdf_filtered[["barangay_name","citymun_name","score"]].sort_values("score", ascending=False)
rank_table.index = rank_table.index + 1
st.dataframe(rank_table, use_container_width=True)
