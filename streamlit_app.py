import os
from typing import Optional

import numpy as np
import pandas as pd
import geopandas as gpd
import pydeck as pdk
import streamlit as st

# ----------------------------------------------------------
# CONFIG / CONSTANTS
# ----------------------------------------------------------

# Paths (relative to repo root)
BARANGAY_SHP_PATH = "data/bulacanbarangay.shp"

# Column names in the shapefile – ADJUST THESE TO MATCH YOUR DATA
BRGY_NAME_COL = "barangay"      # e.g. "BRGY", "BRGY_NM", etc.
CITYMUN_COL = "citymun"         # e.g. "MUN_NAME", "CITY_MUN"
SCORE_COL = "mean_0"            # as per your info

BRGY_NAME_COL = "ADM4_EN"      # e.g. "BRGY", "BRGY_NM", etc.
CITYMUN_COL = "ADM3_EN"         # e.g. "MUN_NAME", "CITY_MUN"
SCORE_COL = "mean_0"            # as per your info

# Competitors Google Sheet CSV URL:
# Option 1: from secrets.toml
COMPETITORS_SHEET_CSV_URL = st.secrets.get(
    "competitors", {}
).get(
    "sheet_csv_url",
    ""  # fallback if not set in secrets
)

# If you want to hardcode (for quick test), uncomment and paste:
# COMPETITORS_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/.../export?format=csv&gid=0"

# Column names in competitors sheet – ADJUST THESE TO MATCH YOUR SHEET
COMP_BRAND_COL = "brand"
COMP_CAT_COL = "category"
COMP_CITYMUN_COL = "citymun"
COMP_PROV_COL = "province"
COMP_LAT_COL = "latitude"
COMP_LON_COL = "longitude"


# ----------------------------------------------------------
# BASIC PAGE CONFIG
# ----------------------------------------------------------
st.set_page_config(
    page_title="Andok's Site Selection – Bulacan",
    layout="wide",
)

st.title("Andok's Site Selection – Bulacan (Per Barangay Prototype)")

st.markdown(
    """
This prototype dashboard shows **per-barangay site selection scores** in **Bulacan**,
with an **interactive map on Google Satellite** and **score tables per municipality and barangay**.

- Map background: Google Satellite (for prototyping)
- Score source: `mean_0` column in your Bulacan barangay shapefile
- Competitors: loaded from a Google Sheet (partial data for now)
"""
)


# ----------------------------------------------------------
# DATA LOADING HELPERS (CACHED)
# ----------------------------------------------------------

@st.cache_data(show_spinner=True)
def load_barangays(shp_path: str) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(shp_path)

    # Ensure CRS is WGS84
    if gdf.crs is None or gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)

    # Standardize columns we will use; create generic ones for convenience
    # (If your columns differ, adjust BRGY_NAME_COL, etc.)
    missing = [c for c in [BRGY_NAME_COL, CITYMUN_COL, SCORE_COL] if c not in gdf.columns]
    if missing:
        st.error(
            f"Missing expected columns in shapefile: {missing}. "
            f"Please check BRGY_NAME_COL/CITYMUN_COL/SCORE_COL at top of script."
        )
        st.stop()

    # Create standard columns
    gdf = gdf.copy()
    gdf["barangay_name"] = gdf[BRGY_NAME_COL].astype(str)
    gdf["citymun_name"] = gdf[CITYMUN_COL].astype(str)
    gdf["score"] = pd.to_numeric(gdf[SCORE_COL], errors="coerce")

    # Drop rows with null geometry or score if necessary
    gdf = gdf[~gdf.geometry.isna()].copy()

    return gdf


@st.cache_data(show_spinner=True)
def load_competitors_from_sheet(sheet_csv_url: str) -> Optional[pd.DataFrame]:
    if not sheet_csv_url:
        return None

    try:
        df = pd.read_csv(sheet_csv_url)
    except Exception as e:
        st.warning(f"Could not load competitors from Google Sheet: {e}")
        return None

    # Check required columns
    required_cols = [COMP_BRAND_COL, COMP_LAT_COL, COMP_LON_COL]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        st.warning(
            f"Competitors sheet is missing expected columns: {missing}. "
            f"Please adjust COMP_*_COL constants in the script."
        )
        return None

    # Basic cleanup
    df = df.copy()
    df["brand"] = df[COMP_BRAND_COL].astype(str)
    df["category"] = df.get(COMP_CAT_COL, "").astype(str) if COMP_CAT_COL in df.columns else ""
    df["citymun"] = df.get(COMP_CITYMUN_COL, "").astype(str) if COMP_CITYMUN_COL in df.columns else ""
    df["province"] = df.get(COMP_PROV_COL, "").astype(str) if COMP_PROV_COL in df.columns else ""
    df["lat"] = pd.to_numeric(df[COMP_LAT_COL], errors="coerce")
    df["lon"] = pd.to_numeric(df[COMP_LON_COL], errors="coerce")

    df = df.dropna(subset=["lat", "lon"]).reset_index(drop=True)
    return df


# ----------------------------------------------------------
# LOAD DATA
# ----------------------------------------------------------

gdf_barangays = load_barangays(BARANGAY_SHP_PATH)
df_competitors = load_competitors_from_sheet(COMPETITORS_SHEET_CSV_URL)

# Province is fixed to Bulacan here, but we keep city/mun selection dynamic
citymun_list = sorted(gdf_barangays["citymun_name"].unique().tolist())
citymun_list_display = ["All municipalities"] + citymun_list


# ----------------------------------------------------------
# SIDEBAR FILTERS
# ----------------------------------------------------------

st.sidebar.header("Filters")

selected_citymun = st.sidebar.selectbox(
    "Municipality / City",
    options=citymun_list_display,
    index=0,
)

min_score = float(np.nanmin(gdf_barangays["score"]))
max_score = float(np.nanmax(gdf_barangays["score"]))

score_range = st.sidebar.slider(
    "Score range (mean_0)",
    float(round(min_score, 3)),
    float(round(max_score, 3)),
    (float(round(min_score, 3)), float(round(max_score, 3))),
    step=0.01,
)

show_comp_layer = st.sidebar.checkbox("Show competitors", value=True)


# ----------------------------------------------------------
# FILTER DATA ACCORDING TO SELECTION
# ----------------------------------------------------------

gdf_filtered = gdf_barangays.copy()

if selected_citymun != "All municipalities":
    gdf_filtered = gdf_filtered[gdf_filtered["citymun_name"] == selected_citymun]

gdf_filtered = gdf_filtered[
    (gdf_filtered["score"] >= score_range[0]) &
    (gdf_filtered["score"] <= score_range[1])
].copy()

if gdf_filtered.empty:
    st.warning("No barangays match the current filters.")
    st.stop()


# ----------------------------------------------------------
# COLOR MAPPING FOR SCORES
# ----------------------------------------------------------

def score_to_color(score: float):
    """Return [R, G, B, A] for a score between min_score and max_score."""
    if pd.isna(score):
        return [200, 200, 200, 180]

    # Normalize 0–1 using global min/max to keep colors consistent
    norm = (score - min_score) / (max_score - min_score + 1e-9)
    # Red (low) -> Yellow (mid) -> Green (high)
    if norm < 0.33:
        return [230, 30, 30, 180]      # red
    elif norm < 0.66:
        return [255, 165, 0, 180]      # orange
    else:
        return [0, 180, 0, 180]        # green

gdf_filtered["fill_color"] = gdf_filtered["score"].apply(score_to_color)


# ----------------------------------------------------------
# BUILD MAP (PYDECK WITH GOOGLE SATELLITE)
# ----------------------------------------------------------

# GeoJsonLayer for barangays
barangay_layer = pdk.Layer(
    "GeoJsonLayer",
    data=gdf_filtered,
    pickable=True,
    stroked=True,
    filled=True,
    get_fill_color="fill_color",
    get_line_color=[255, 255, 255],
    get_line_width=1,
    auto_highlight=True,
)

layers = []

# Tile layer with Google Satellite (for prototyping)
tile_layer = pdk.Layer(
    "TileLayer",
    data=None,
    minZoom=0,
    maxZoom=19,
    tileSize=256,
    get_tile_data=None,
    pickable=False,
    # Google satellite tiles (prototype only)
    # For production, use a proper map provider and API key.
    url_template="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
)

layers.append(tile_layer)
layers.append(barangay_layer)

# Competitors layer (if data is available and toggle is on)
if show_comp_layer and df_competitors is not None and not df_competitors.empty:
    comp_layer = pdk.Layer(
        "ScatterplotLayer",
        data=df_competitors,
        get_position="[lon, lat]",
        get_radius=60,
        get_fill_color=[0, 0, 255, 200],
        pickable=True,
    )
    layers.append(comp_layer)

# Compute initial view state from filtered barangays
centroid = gdf_filtered.geometry.unary_union.centroid
view_state = pdk.ViewState(
    latitude=centroid.y,
    longitude=centroid.x,
    zoom=11,
    pitch=0,
    bearing=0,
)

# Tooltip
tooltip = {
    "html": (
        "<b>{barangay_name}</b>, {citymun_name}<br/>"
        "Score (mean_0): {score}<br/>"
    ),
    "style": {
        "backgroundColor": "steelblue",
        "color": "white",
    },
}

deck = pdk.Deck(
    layers=layers,
    initial_view_state=view_state,
    tooltip=tooltip,
    map_style=None,  # None because we are using a custom TileLayer (Google Satellite)
)

st.subheader("Interactive Map – Bulacan Barangays (mean_0 score)")
st.pydeck_chart(deck)


# ----------------------------------------------------------
# TABLES: MUNICIPALITY SUMMARY + BARANGAY RANKING
# ----------------------------------------------------------

st.subheader("Score Summary")

# Municipality-level summary (based on filtered set or whole Bulacan)
if selected_citymun == "All municipalities":
    gdf_for_summary = gdf_barangays.copy()
else:
    gdf_for_summary = gdf_barangays[gdf_barangays["citymun_name"] == selected_citymun].copy()

mun_summary = (
    gdf_for_summary
    .groupby("citymun_name")["score"]
    .agg(["count", "mean", "min", "max"])
    .reset_index()
    .rename(columns={
        "citymun_name": "Municipality/City",
        "count": "No. of Barangays",
        "mean": "Average Score",
        "min": "Min Score",
        "max": "Max Score",
    })
    .sort_values("Average Score", ascending=False)
)

st.markdown("**Municipality / City summary (Bulacan)**")
st.dataframe(
    mun_summary.style.format(
        {
            "Average Score": "{:.3f}",
            "Min Score": "{:.3f}",
            "Max Score": "{:.3f}",
        }
    ),
    use_container_width=True,
)

# Barangay-level detail table (filtered)
st.markdown(
    f"**Barangay scores for: "
    f"{'All municipalities' if selected_citymun == 'All municipalities' else selected_citymun}**"
)

brgy_table = (
    gdf_filtered[["barangay_name", "citymun_name", "score"]]
    .sort_values("score", ascending=False)
    .reset_index(drop=True)
)
brgy_table.index = brgy_table.index + 1  # 1-based rank

brgy_table = brgy_table.rename(
    columns={
        "barangay_name": "Barangay",
        "citymun_name": "Municipality/City",
        "score": "Score (mean_0)",
    }
)

st.dataframe(
    brgy_table.style.format({"Score (mean_0)": "{:.3f}"}),
    use_container_width=True,
)
