import os
import random
import base64
from io import BytesIO
import calendar

import numpy as np
import pandas as pd
import geopandas as gpd
import pydeck as pdk
import streamlit as st
from PIL import Image

# ----------------------------------------------------------
# PAGE CONFIG
# ----------------------------------------------------------
st.set_page_config(
    page_title="Andok's – Bulacan Dashboards",
    layout="wide",
)

st.title("Andok's – Bulacan Dashboards")

st.markdown(
    """
Use the sidebar to switch between:
- **Site Selection** dashboard  
- **Monthly Sales** dashboard
"""
)

# ----------------------------------------------------------
# CONSTANTS
# ----------------------------------------------------------

BARANGAY_SHP_PATH = "data/bulacanbarangay.shp"

BRGY_NAME_COL = "ADM4_EN"
CITYMUN_COL = "ADM3_EN"
SCORE_COL = "mean_0"

# Local Excel sources
COMPETITORS_XLSX_PATH = "data/andoks-competitors.xlsx"
BRANCHES_XLSX_PATH = "data/andoks-branches.xlsx"
ANDOKS_ICON_PATH = "icon/andoks-icon.png"

# New paths for Monthly Sales dashboard
MUNI_SHP_PATH = "data/bulacan_muni.shp"
MONTHLY_SALES_XLSX_PATH = "data/andoks_monthly_sales.xlsx"

# ----------------------------------------------------------
# LOAD BARANGAYS (SITE SELECTION)
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
# LOAD ANDOK'S BRANCHES FROM XLSX
# ----------------------------------------------------------

@st.cache_data(show_spinner=True)
def load_andoks_branches(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        st.warning(f"Andok's branches file not found at: {path}")
        return pd.DataFrame()

    try:
        raw = pd.read_excel(path)
    except Exception as e:
        st.warning(f"Could not load andoks-branches.xlsx: {e}")
        return pd.DataFrame()

    if raw.empty:
        st.warning("Andok's branches file is empty.")
        return pd.DataFrame()

    # Normalize column names
    df = raw.copy()
    df.columns = df.columns.str.strip().str.lower()

    required_cols = ["outlet name", "outlet address", "latitude", "longitude"]
    for col in required_cols:
        if col not in df.columns:
            st.warning(
                f"Andok's branches file missing column '{col}'. "
                f"Found: {df.columns.tolist()}"
            )
            return pd.DataFrame()

    df["lat"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["lon"] = pd.to_numeric(df["longitude"], errors="coerce")
    df["name"] = df["outlet name"].astype(str)
    df["address"] = df["outlet address"].astype(str)

    df = df.dropna(subset=["lat", "lon"]).reset_index(drop=True)
    return df


df_branches = load_andoks_branches(BRANCHES_XLSX_PATH)

# ----------------------------------------------------------
# LOAD ANDOK'S ICON (REMOVE WHITE BACKGROUND)
# ----------------------------------------------------------

@st.cache_data(show_spinner=True)
def load_andoks_icon(path: str):
    if not os.path.exists(path):
        st.warning(f"Andok's icon not found at: {path}")
        return None

    try:
        img = Image.open(path).convert("RGBA")
    except Exception as e:
        st.warning(f"Could not read Andok's icon: {e}")
        return None

    # Remove white background
    datas = img.getdata()
    new_data = []
    for item in datas:
        # Detect white or near-white pixels
        if item[0] > 240 and item[1] > 240 and item[2] > 240:
            # Make transparent
            new_data.append((255, 255, 255, 0))
        else:
            new_data.append(item)

    img.putdata(new_data)

    # Encode PNG → Base64
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    icon_spec = {
        "url": f"data:image/png;base64,{b64}",
        "width": img.width,
        "height": img.height,
        "anchorX": img.width // 2,
        "anchorY": img.height,  # bottom anchor
    }

    return icon_spec


andoks_icon_spec = load_andoks_icon(ANDOKS_ICON_PATH)

if andoks_icon_spec is not None and not df_branches.empty:
    df_branches["icon_data"] = [andoks_icon_spec] * len(df_branches)

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
# RANDOM COLORS PER COMPETITOR BRAND
# ----------------------------------------------------------

def random_color():
    return [random.randint(0, 255), random.randint(0, 255), random.randint(0, 255), 240]

if not df_competitors.empty:
    brands = df_competitors["brand"].unique().tolist()
    brand_color_map = {b: random_color() for b in brands}
    df_competitors["color"] = df_competitors["brand"].map(brand_color_map)

# ----------------------------------------------------------
# NEW: LOAD MUNICIPALITIES & MONTHLY SALES (MONTHLY SALES DASHBOARD)
# ----------------------------------------------------------

@st.cache_data(show_spinner=True)
def load_municipalities(path: str) -> gpd.GeoDataFrame:
    if not os.path.exists(path):
        st.warning(f"Municipality shapefile not found at: {path}")
        return gpd.GeoDataFrame()

    gdf = gpd.read_file(path)

    if gdf.crs is None or gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)

    if "MUNICIPAL" not in gdf.columns:
        st.warning(
            "Municipality shapefile is missing column 'MUNICIPAL'. "
            f"Columns: {gdf.columns.tolist()}"
        )
        return gdf

    gdf = gdf[~gdf.geometry.isna()].copy()
    gdf["MUNICIPAL"] = gdf["MUNICIPAL"].astype(str)
    gdf["MUNICIPAL_clean"] = gdf["MUNICIPAL"].str.upper().str.strip()
    return gdf


@st.cache_data(show_spinner=True)
def load_monthly_sales(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        st.warning(f"Monthly sales file not found at: {path}")
        return pd.DataFrame()

    try:
        df = pd.read_excel(path)
    except Exception as e:
        st.warning(f"Could not load monthly sales file: {e}")
        return pd.DataFrame()

    if df.empty:
        st.warning("Monthly sales file is empty.")
        return pd.DataFrame()

    required_cols = ["Municipality", "year", "month", "monthly_sales"]
    for col in required_cols:
        if col not in df.columns:
            st.warning(
                f"Monthly sales file missing column '{col}'. "
                f"Found: {df.columns.tolist()}"
            )
            return pd.DataFrame()

    df = df.copy()
    df["Municipality"] = df["Municipality"].astype(str)
    df["Municipality_clean"] = df["Municipality"].str.upper().str.strip()
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    df["month"] = pd.to_numeric(df["month"], errors="coerce").astype("Int64")
    df["monthly_sales"] = pd.to_numeric(df["monthly_sales"], errors="coerce")

    df = df.dropna(subset=["year", "month", "monthly_sales"]).reset_index(drop=True)
    return df


gdf_muni = load_municipalities(MUNI_SHP_PATH)
df_monthly_sales = load_monthly_sales(MONTHLY_SALES_XLSX_PATH)

# ----------------------------------------------------------
# DASHBOARD SELECTION
# ----------------------------------------------------------

st.sidebar.title("Dashboard")
dashboard_choice = st.sidebar.radio(
    "Select dashboard",
    ["Site Selection", "Monthly Sales"],
    index=0,
)

# ----------------------------------------------------------
# SITE SELECTION DASHBOARD
# ----------------------------------------------------------

if dashboard_choice == "Site Selection":
    st.subheader("Site Selection – Barangay Suitability")

    # SIDEBAR FILTERS & DEBUG INFO
    st.sidebar.header("Filters")

    city_list = sorted(gdf_barangays["citymun_name"].unique())
    city_choice = ["All"] + city_list
    selected_city = st.sidebar.selectbox("Municipality / City", city_choice)

    show_competitors = st.sidebar.checkbox("Show competitors", value=True)
    show_andoks_branches = st.sidebar.checkbox("Show Andok's branches", value=True)

    # Debug info
    st.sidebar.markdown("### Data info")
    st.sidebar.write(f"Barangays loaded: {len(gdf_barangays)}")
    st.sidebar.write(f"Competitors loaded (after cleaning): {len(df_competitors)}")
    st.sidebar.write(f"Andok's branches loaded: {len(df_branches)}")

    gdf_filtered = gdf_barangays.copy()
    if selected_city != "All":
        gdf_filtered = gdf_filtered[gdf_filtered["citymun_name"] == selected_city]

    if gdf_filtered.empty:
        st.warning("No barangays match the current filter.")
        st.stop()

    # Optional previews
    if not df_competitors.empty:
        st.expander("Preview competitors data").dataframe(
            df_competitors[["brand", "lat", "lon"]].head(),
            use_container_width=True,
        )

    if not df_branches.empty:
        st.expander("Preview Andok's branches data").dataframe(
            df_branches[["name", "address", "lat", "lon"]].head(),
            use_container_width=True,
        )

    # BUILD THE MAP
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

    # Competitors ABOVE polygons
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

    # Andok's branches as ICONS
    if (
        show_andoks_branches
        and andoks_icon_spec is not None
        and not df_branches.empty
    ):
        andoks_layer = pdk.Layer(
            "IconLayer",
            data=df_branches,
            get_position="[lon, lat]",
            get_icon="icon_data",
            get_size=4,
            size_scale=10,
            pickable=True,
        )
        layers.append(andoks_layer)

    tooltip = {
        "html": (
            "<b>{barangay_name}</b>, {citymun_name}<br/>"
            "Score: <b>{score}</b><br/>"
            "<hr/>"
            "<b>{name}</b><br/>{address}"
        ),
        "style": {"backgroundColor": "steelblue", "color": "white"},
    }

    deck = pdk.Deck(
        layers=layers,
        initial_view_state=view_state,
        tooltip=tooltip,
        map_style=None,
    )

    st.subheader("Barangay Suitability Map")
    st.pydeck_chart(deck)

    # SUMMARY TABLES
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

# ----------------------------------------------------------
# MONTHLY SALES DASHBOARD
# ----------------------------------------------------------

elif dashboard_choice == "Monthly Sales":
    st.subheader("Monthly Sales – Municipality Performance")

    st.sidebar.header("Monthly Sales Filters")

    if gdf_muni is None or gdf_muni.empty or df_monthly_sales is None or df_monthly_sales.empty:
        st.warning("Municipality boundaries or monthly sales data are not available.")
        st.stop()

    # Year selector
    years = sorted(df_monthly_sales["year"].dropna().unique())
    if not years:
        st.warning("No valid years found in monthly sales data.")
        st.stop()

    default_year_index = len(years) - 1
    selected_year = st.sidebar.selectbox("Year", years, index=default_year_index)

    # Month time slider
    selected_month = st.sidebar.slider("Month", 1, 12, 1)
    month_name = calendar.month_name[int(selected_month)]

    # Filter sales for selected year and month
    df_filtered_sales = df_monthly_sales[
        (df_monthly_sales["year"] == selected_year)
        & (df_monthly_sales["month"] == selected_month)
    ].copy()

    if df_filtered_sales.empty:
        st.warning("No sales data for the selected year and month.")
    else:
        # Aggregate sales per municipality (sum of all branches inside each municipality)
        sales_agg = (
            df_filtered_sales.groupby("Municipality_clean")["monthly_sales"]
            .sum()
            .reset_index()
            .rename(columns={"monthly_sales": "sales_total"})
        )

        gdf_muni_local = gdf_muni.copy()

        # Join aggregated sales to municipality polygons
        gdf_joined = gdf_muni_local.merge(
            sales_agg,
            left_on="MUNICIPAL_clean",
            right_on="Municipality_clean",
            how="left",
        )

        # Compute percentiles on non-null sales
        valid_sales = gdf_joined["sales_total"].dropna()
        if valid_sales.empty:
            p25 = p75 = None
        else:
            p25 = float(np.percentile(valid_sales, 25))
            p75 = float(np.percentile(valid_sales, 75))

        def sales_color(value):
            if value is None or (isinstance(value, float) and np.isnan(value)) or p25 is None or p75 is None:
                return [200, 200, 200, 120]  # neutral grey
            if value <= p25:
                return [255, 165, 0, 180]   # orange
            elif value < p75:
                return [255, 255, 0, 180]   # yellow
            else:
                return [0, 128, 0, 180]     # green

        gdf_joined["fill_color_sales"] = gdf_joined["sales_total"].apply(sales_color)

        # Map view
        centroid = gdf_joined.geometry.unary_union.centroid

        view_state_sales = pdk.ViewState(
            latitude=centroid.y,
            longitude=centroid.x,
            zoom=10,
            pitch=0,
        )

        tile_layer_sales = pdk.Layer(
            "TileLayer",
            data=None,
            minZoom=0,
            maxZoom=19,
            tileSize=256,
            url_template="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
        )

        muni_layer = pdk.Layer(
            "GeoJsonLayer",
            data=gdf_joined,
            pickable=True,
            filled=True,
            stroked=True,
            get_fill_color="fill_color_sales",
            get_line_color=[80, 80, 80, 200],
            get_line_width=1,
            auto_highlight=True,
        )

        layers_sales = [tile_layer_sales, muni_layer]

        tooltip_sales = {
            "html": (
                "<b>{MUNICIPAL}</b><br/>"
                f"Sales ({selected_year}-{int(selected_month):02d}): "
                "<b>{sales_total}</b>"
            ),
            "style": {"backgroundColor": "steelblue", "color": "white"},
        }

        deck_sales = pdk.Deck(
            layers=layers_sales,
            initial_view_state=view_state_sales,
            tooltip=tooltip_sales,
            map_style=None,
        )

        st.subheader(f"Monthly Sales by Municipality – {month_name} {selected_year}")
        st.pydeck_chart(deck_sales)

        st.markdown(
            """
            **Legend:**  
            - 🟧 Orange: ≤ 25th percentile (lower sales)  
            - 🟨 Yellow: 25th–74th percentile (mid-range sales)  
            - 🟩 Green: ≥ 75th percentile (higher sales)
            """
        )

        # Municipality sales summary table
        summary_sales = (
            gdf_joined[["MUNICIPAL", "sales_total"]]
            .rename(columns={"MUNICIPAL": "Municipality", "sales_total": "Total monthly sales"})
            .sort_values("Total monthly sales", ascending=False)
        )

        st.subheader("Municipality Sales Summary")
        st.dataframe(summary_sales, use_container_width=True)
