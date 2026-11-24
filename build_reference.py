"""Build the reference address store (run once, then refresh occasionally).

    python build_reference.py
    python build_reference.py --postcodes data/postcodes.csv --extra data/licensed_addresses.csv

--postcodes : CSV with columns  postcode,locality
--extra     : CSV with columns  street,locality,city,postcode   (e.g. a licensed dataset)
"""
import argparse
import faiss
import numpy as np
import pandas as pd
import requests
from sentence_transformers import SentenceTransformer
from sklearn.neighbors import BallTree
import time

from config import EMBED_MODEL, FAISS_INDEX, REFERENCE_PARQUET
from normalize import normalize

# OVERPASS = "https://overpass-api.de/api/interpreter"
Q_PLACES = '[out:json][timeout:300];area["ISO3166-1"="MU"]->.a;node["place"~"city|town|village|suburb|hamlet|neighbourhood"]["name"](area.a);out;'
Q_STREETS = '[out:json][timeout:300];area["ISO3166-1"="MU"]->.a;way["highway"]["name"](area.a);out center tags;'


# def overpass(query: str) -> list[dict]:
#     r = requests.post(OVERPASS, data={"data": query}, timeout=400)
#     r.raise_for_status()
#     return r.json()["elements"]
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
HEADERS = {
    # overpass-api.de now refuses (HTTP 406) requests without a proper User-Agent
    "User-Agent": "address_pipeline/1.0 (Mauritius address reference builder)",
    "Referer": "https://github.com/address_pipeline",
}


def overpass(query: str) -> list[dict]:
    last = None
    for url in OVERPASS_URLS:
        for attempt in range(2):
            try:
                r = requests.post(url, data={"data": query}, headers=HEADERS, timeout=400)
                if r.status_code == 200:
                    return r.json()["elements"]
                last = f"{url} -> HTTP {r.status_code}: {r.text[:200]}"
            except (requests.RequestException, ValueError) as e:
                last = f"{url} -> {e}"
            print(f"  Overpass failed ({last}), retrying...")
            time.sleep(10)
    raise RuntimeError(f"All Overpass servers failed. Last error: {last}")


def nearest(src: pd.DataFrame, dst: pd.DataFrame) -> np.ndarray:
    tree = BallTree(np.radians(src[["lat", "lon"]].values), metric="haversine")
    _, idx = tree.query(np.radians(dst[["lat", "lon"]].values), k=1)
    return src["name"].values[idx[:, 0]]


def from_osm() -> pd.DataFrame:
    places = pd.DataFrame([{"name": e["tags"]["name"], "place": e["tags"]["place"], "lat": e["lat"], "lon": e["lon"]}
                           for e in overpass(Q_PLACES)])
    streets = pd.DataFrame([{"street": e["tags"]["name"], "lat": e["center"]["lat"], "lon": e["center"]["lon"]}
                            for e in overpass(Q_STREETS) if "center" in e])
    towns = places[places["place"].isin(["city", "town"])]
    streets["locality"] = nearest(places, streets)
    streets["city"] = nearest(towns, streets)
    streets["postcode"] = ""
    return streets[["street", "locality", "city", "postcode"]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--postcodes")
    ap.add_argument("--extra")
    args = ap.parse_args()

    df = from_osm()
    if args.extra:
        df = pd.concat([df, pd.read_csv(args.extra, dtype=str).fillna("")], ignore_index=True)
    if args.postcodes:
        pc = pd.read_csv(args.postcodes, dtype=str)
        lookup = dict(zip(pc["locality"].map(normalize), pc["postcode"]))
        missing = df["postcode"].eq("")
        df.loc[missing, "postcode"] = df.loc[missing, "locality"].map(lambda x: lookup.get(normalize(x), ""))

    df["search_key"] = (df["street"] + " " + df["locality"] + " " + df["city"]).map(normalize)
    df = df.drop_duplicates("search_key").reset_index(drop=True)
    df.to_parquet(REFERENCE_PARQUET)
    print(f"{len(df)} reference addresses saved")

    model = SentenceTransformer(EMBED_MODEL)
    emb = model.encode(["passage: " + k for k in df["search_key"]], batch_size=128,
                       normalize_embeddings=True, show_progress_bar=True).astype("float32")
    index = faiss.IndexFlatIP(emb.shape[1])
    index.add(emb)
    faiss.write_index(index, str(FAISS_INDEX))
    print("FAISS index saved")


if __name__ == "__main__":
    main()
