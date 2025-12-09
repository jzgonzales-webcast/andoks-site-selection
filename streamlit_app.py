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

st.title("Andok's Site Selection – Bulacan")

st.markdown(
    """
This dashboard displays **barangay-level suitability scores** across **Bulacan**.
"""
)

# ----------------------------------------------------------
# CONSTANTS
# ----------------------------------------------------------

BARANGAY_SHP_PATH = "data/bulacanbarangay.shp"

BRGY_NAME_COL = "ADM4_EN"
CITYMUN_COL = "ADM3_EN"
SCORE_COL = "mean_0"

# Competitors source: XLSX file in repo data folder
COMPETITORS_XLSX_PATH = "data/andoks-competitors.xlsx"

# ----------------------------------------------------------
# LOAD BARANGAYS
# ----------------------------------------------------------

@st.cache_data(show_spinner=True)
def load_barangays(path: str) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(path)

    # Ensure WGS84 CRS
    if gdf.crs is None or gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)

    required = [BRGY_NAME_COL, CITYMUN_COL, SCORE_COL]
    for col in required:
        if col not in gdf.columns:
            st.error(
                f"Missing column '{col}' in barangay shapefile. "
                f"Columns: {gdf.columns.tolist()}"
            )
            st.stop()

    gdf = gdf.copy()
    gdf["barangay_name"] = gdf[BRGY_NAME_COL].astype(str)
    gdf["citymun_name"] = gdf[CITYMUN_COL].astype(str)
    gdf["score"] = pd.to_numeric(gdf[SCORE_COL], errors="coerce")
    gdf = gdf[~gdf.geometry.isna()]

    return gdf


gdf_barangays = load_barangays(BARANGAY_SHP_PATH)

# ----------------------------------------------------------
# LOAD COMPETITORS FROM XLSX (IN REPO)
# ----------------------------------------------------------

@st.cache_data(show_spinner=True)
def load_competitors_from_xlsx(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        st.warning(f"Competitors file not found at: {path}")
        return pd.DataFrame()

    try:
        raw = pd.read_excel(path)
    except Exception as e:
        st.warning(f"Could not load competitors file: {e}")
        return pd.DataFrame()

    if raw.empty:
        st.warning("Competitors file is empty.")
        return pd.DataFrame()

    # Normalize column names: lowercase + strip spaces
    df = raw.copy()
    df.columns = df.columns.str.strip().str.lower()

    # Candidate names for each logical column
    long_candidates = ["longitude", "longtitude", "lon", "lng"]
    lat_candidates = ["latitude", "lat"]
    brand_candidates = ["brand", "brand_name"]

    def pick_column(candidates, available_cols):
        for c in candidates:
            if c in available_cols:
                return c
        return None

    col_lon = pick_column(long_candidates, df.columns)
    col_lat = pick_column(lat_candidates, df.columns)
    col_brand = pick_column(brand_candidates, df.columns)

    missing = []
    if col_lon is None:
        missing.append(f"one of {long_candidates}")
    if col_lat is None:
        missing.append(f"one of {lat_candidates}")
    if col_brand is None:
        missing.append(f"one of {brand_candidates}")

    if missing:
        st.warning(
            "Competitors file is missing required columns.\n"
            f"Expected: {missing}\n"
            f"Found columns: {df.columns.tolist()}"
        )
        return pd.DataFrame()

    df["lon"] = pd.to_numeric(df[col_lon], errors="coerce")
    df["lat"] = pd.to_numeric(df[col_lat], errors="coerce")
    df["brand"] = df[col_brand].astype(str)

    df = df.dropna(subset=["lat", "lon"]).reset_index(drop=True)
    return df


df_competitors = load_competitors_from_xlsx(COMPETITORS_XLSX_PATH)

# ----------------------------------------------------------
# SLD STYLING FUNCTION (EXACT FROM YOUR .sld)
# ----------------------------------------------------------

def sld_color(mean_0):
    if mean_0 is None or np.isnan(mean_0):
        return [200, 200, 200, 150]

    if 1.02915619443098993 <= mean_0 <= 1.67021351760768:
        return [215, 25, 28, 150]      # #d7191c
    elif 1.67021351760768 < mean_0 <= 2.11293581101225003:
        return [232, 91, 59, 150]      # #e85b3b
    elif 2.11293581101225003 < mean_0 <= 2.47597288754775002:
        return [249, 157, 89, 150]     # #f99d59
    elif 2.47597288754775002 < mean_0 <= 2.85005666392968982:
        return [254, 201, 129, 150]    # #fec981
    elif 2.85005666392968982 < mean_0 <= 3.18201286704618003:
        return [255, 237, 171, 150]    # #ffedab
    elif 3.18201286704618003 < mean_0 <= 3.52431534195362017:
        return [235, 247, 173, 150]    # #ebf7ad
    elif 3.52431534195362017 < mean_0 <= 3.92996775043785984:
        return [196, 230, 135, 150]    # #c4e687
    elif 3.92996775043785984 < mean_0 <= 4.44667928886414021:
        return [150, 210, 101, 150]    # #96d265
    elif 4.44667928886414021 < mean_0 <= 5.04817327088676038:
        return [88, 180, 83, 150]      # #58b453
    elif 5.04817327088676038 < mean_0 <= 6.22406019477859029:
        return [26, 150, 65, 150]      # #1a9641
    else:
        return [200, 200, 200, 150]


gdf_barangays["fill_color"] = gdf_barangays["score"].apply(sld_color)

# ----------------------------------------------------------
# RANDOM COLORS PER BRAND (DETERMINISTIC PER SESSION)
# ----------------------------------------------------------

def random_color():
    return [random.randint(0, 255), random.randint(0, 255), random.randint(0, 255), 240]

if not df_competitors.empty:
    brands = df_competitors["brand"].unique().tolist()
    brand_color_map = {b: random_color() for b in brands}
    df_competitors["color"] = df_competitors["brand"].map(brand_color_map)

# ----------------------------------------------------------
# SIDEBAR FILTERS & DEBUG INFO
# ----------------------------------------------------------

st.sidebar.header("Filters")

city_list = sorted(gdf_barangays["citymun_name"].unique())
city_choice = ["All"] + city_list
selected_city = st.sidebar.selectbox("Municipality / City", city_choice)

show_competitors = st.sidebar.checkbox("Show competitors", value=True)

# Debug info so you can confirm data is loading
st.sidebar.markdown("### Data info")
st.sidebar.write(f"Barangays loaded: {len(gdf_barangays)}")
st.sidebar.write(f"Competitors loaded (after cleaning): {len(df_competitors)}")

gdf_filtered = gdf_barangays.copy()
if selected_city != "All":
    gdf_filtered = gdf_filtered[gdf_filtered["citymun_name"] == selected_city]

if gdf_filtered.empty:
    st.warning("No barangays match the current filter.")
    st.stop()

# Optional: preview competitors
if not df_competitors.empty:
    st.expander("Preview competitors data").dataframe(
        df_competitors[["brand", "lat", "lon"]].head(),
        use_container_width=True,
    )

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
    url_template="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
)

barangay_layer = pdk.Layer(
    "GeoJsonLayer",
    data=gdf_filtered,
    pickable=True,
    filled=True,
    stroked=True,
    get_fill_color="fill_color",
    get_line_color=[35, 35, 35, 200],
    get_line_width=1,
    auto_highlight=True,
)

layers = [tile_layer, barangay_layer]

# Competitors ABOVE polygons, high contrast, with outlines
if show_competitors and not df_competitors.empty:
    competitor_layer = pdk.Layer(
        "ScatterplotLayer",
        data=df_competitors,
        get_position="[lon, lat]",
        get_fill_color="color",
        get_radius=120,                 # large radius for visibility
        get_line_color=[0, 0, 0, 255],  # black outline
        line_width_min_pixels=1.0,
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
    .rename(columns={
        "citymun_name": "Municipality / City",
        "count": "No. of barangays",
        "mean": "Average score",
        "min": "Min score",
        "max": "Max score",
    })
)

st.dataframe(summary, use_container_width=True)

st.subheader("Barangay Ranking")
rank_table = (
    gdf_filtered[["barangay_name", "citymun_name", "score"]]
    .sort_values("score", ascending=False)
    .reset_index(drop=True)
)
rank_table.index = rank_table.index + 1
rank_table = rank_table.rename(columns={
    "barangay_name": "Barangay",
    "citymun_name": "Municipality / City",
    "score": "Score (mean_0)",
})
st.dataframe(rank_table, use_container_width=True)
