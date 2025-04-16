import streamlit as st
import os
import requests
import pandas as pd
import numpy as np
import rasterio
import pydeck as pdk
from io import StringIO

# Constants
DOWNLOAD_FOLDER = "downloads"
OUTPUT_FILE = "output.csv"
SAMPLE_LIMIT = 100000

st.set_page_config(page_title="Inundation Extractor", layout="wide")

def download_file(url):
    os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
    filename = url.split("/")[-1]
    filepath = os.path.join(DOWNLOAD_FOLDER, filename)
    if os.path.exists(filepath):
        return filepath
    response = requests.get(url, stream=True)
    if response.status_code == 200:
        with open(filepath, "wb") as f:
            for chunk in response.iter_content(1024):
                f.write(chunk)
        return filepath
    return None

def extract_sampled_depths(tiff_path, sample_limit=SAMPLE_LIMIT):
    coords_data = []
    try:
        with rasterio.open(tiff_path) as src:
            band = src.read(1)
            nodata = src.nodata
            valid_mask = (band != nodata) & (band > 0)
            valid_indices = np.argwhere(valid_mask)
            if len(valid_indices) == 0:
                return pd.DataFrame(columns=["Longitude", "Latitude", "InundationDepth_m"])
            sampled_indices = (
                valid_indices[np.random.choice(len(valid_indices), sample_limit, replace=False)]
                if len(valid_indices) > sample_limit else valid_indices
            )
            for row, col in sampled_indices:
                x, y = rasterio.transform.xy(src.transform, row, col)
                value = band[row, col]
                coords_data.append((x, y, value))
        return pd.DataFrame(coords_data, columns=["Longitude", "Latitude", "InundationDepth_m"])
    except Exception as e:
        st.error(f"Error processing {tiff_path}: {e}")
        return pd.DataFrame(columns=["Longitude", "Latitude", "InundationDepth_m"])

def append_to_output_file(df):
    if os.path.exists(OUTPUT_FILE):
        existing_df = pd.read_csv(OUTPUT_FILE)
        combined_df = pd.concat([existing_df, df], ignore_index=True)
    else:
        combined_df = df
    combined_df.drop_duplicates(subset=["Longitude", "Latitude", "InundationDepth_m"], inplace=True)
    combined_df.to_csv(OUTPUT_FILE, index=False)

# UI
st.title("🌊 Inundation Depth Extractor from GeoTIFF URLs")

uploaded_file = st.file_uploader("📄 Upload `urls.txt` containing one GeoTIFF URL per line", type=["txt"])

if uploaded_file is not None:
    content = uploaded_file.read().decode("utf-8")
    urls = [line.strip() for line in StringIO(content) if line.strip()]
    if not urls:
        st.warning("The uploaded file is empty or improperly formatted.")
    else:
        st.success(f"✅ {len(urls)} URLs loaded.")

        progress = st.progress(0)
        status_text = st.empty()

        for i, url in enumerate(urls):
            status_text.text(f"Processing {url} ({i+1} of {len(urls)})")
            tiff_path = download_file(url)
            if tiff_path:
                df = extract_sampled_depths(tiff_path)
                if not df.empty:
                    append_to_output_file(df)
            progress.progress((i + 1) / len(urls))

        st.success("🎉 All files processed and data extracted!")

        with open(OUTPUT_FILE, "rb") as f:
            st.download_button(
                label="📥 Download output.csv",
                data=f,
                file_name="output.csv",
                mime="text/csv"
            )

# Show top 50
if os.path.exists(OUTPUT_FILE):
    st.subheader("🔎 Preview: Top 50 Records from Output")
    output_df = pd.read_csv(OUTPUT_FILE)
    st.dataframe(output_df.head(50))

    # Show map
    st.subheader("🗺️ Inundation Map (Depth in meters)")

    if not output_df.empty:
        map_df = output_df.copy()
        map_df = map_df.dropna(subset=["Latitude", "Longitude", "InundationDepth_m"])

        layer = pdk.Layer(
            "ScatterplotLayer",
            data=map_df,
            get_position="[Longitude, Latitude]",
            get_radius=50,
            get_fill_color="[255, 0, 0, 160]",
            pickable=True,
        )

        view_state = pdk.ViewState(
            longitude=map_df["Longitude"].mean(),
            latitude=map_df["Latitude"].mean(),
            zoom=4,
            pitch=0,
        )

        tooltip = {
            "html": "Depth: <b>{InundationDepth_m} m</b><br>Lat: {Latitude}<br>Lon: {Longitude}",
            "style": {"backgroundColor": "steelblue", "color": "white"}
        }

        st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view_state, tooltip=tooltip))
