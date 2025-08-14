"""
Write a program to do the following:

Extract geospatial data for roadway and nearby cities/towns within 500 meters of the roadway for a given roadway
You may use Overpass API or QGIS
Tag the places as either “city” or “town” in the output.
Tag the roadway as “roadway” in the output.
Output in JSON format with the following elements: roadway, placename, placename_ascii, placename_en, placetag, latitude, longitude, state/province, country.

TODO:   -test different versions and cleanup code.
        -test different naming conventions
        -compare results for discrepancies by name format
        -keep is simple
        -store results

        NOTE: This version uses the Overpass API via direct HTTP requests.  It is working off the kumi.systems mirror site endpoint.
"""

import requests
import json
import time
import sys  # used for simplicity as argparse was making things more complex
from shapely.geometry import LineString, Point
from shapely.ops import transform
from pyproj import Transformer, CRS

API_URL = "https://overpass.kumi.systems/api/interpreter"
REV_GEO_URL = "https://nominatim.openstreetmap.org/reverse"
HEADERS = {"User-Agent": "overpass-api test_script v.1 (john7774@icloud.com)"}


def find_roadway(roadway_name, bbox=None):
    key_str = ""
    if bbox:
        s, w, n, e = bbox
        key_str = f"({s},{w},{n},{e})"
    query = f"""
    [out:json][timeout:60];
    (
      relation["ref"~"{roadway_name}",i]["type"="route"]["route"="road"]{key_str};
      way["ref"~"{roadway_name}",i]["highway"]{key_str};
      way["name"~"{roadway_name}",i]["highway"]{key_str};
    );
    out geom;
    """

    res = requests.post(API_URL, data={"data": query}, headers=HEADERS, timeout=90)
    res.raise_for_status()
    data = res.json()
    gpsx = []
    for e in data.get("elements", []):
        if "geometry" in e:
            gpsx.extend([(pt["lon"], pt["lat"]) for pt in e["geometry"]])
    return gpsx


def create_buffer(gpsx, buffer_m=500):
    seg = LineString(gpsx)
    utm_zone = int((gpsx[0][0] + 180) / 6) + 1
    utm_crs = CRS.from_proj4(
        f"+proj=utm +zone={utm_zone} +datum=WGS84 +units=m +no_defs"
    )
    trans_to_utm = Transformer.from_crs("EPSG:4326", utm_crs, always_xy=True).transform
    trans_to_wgs = Transformer.from_crs(utm_crs, "EPSG:4326", always_xy=True).transform
    seg_m = transform(trans_to_utm, seg)
    buff_mpoly = seg_m.buffer(buffer_m)
    buff_wgs = transform(trans_to_wgs, buff_mpoly)
    return buff_wgs


def global_area(geom, expand_factor=0.02):
    minx, miny, maxx, maxy = geom.bounds
    dx = maxx - minx
    dy = maxy - miny
    padx = dx * expand_factor + 0.01
    pady = dy * expand_factor + 0.01
    return (miny - pady, minx - padx, maxy + pady, maxx + padx)


def search_zone(bbox):
    s, w, n, e = bbox
    query = f"""
    [out:json][timeout:60];
    (
      node["place"~"city|town"]({s},{w},{n},{e});
      way["place"~"city|town"]({s},{w},{n},{e});
      relation["place"~"city|town"]({s},{w},{n},{e});
    );
    out center tags;
    """
    res = requests.post(API_URL, data={"data": query}, headers=HEADERS, timeout=90)
    res.raise_for_status()
    return res.json().get("elements", [])


def reverse_geocode(lat, lon):
    params = {"format": "jsonv2", "lat": lat, "lon": lon, "accept-language": "en"}
    res = requests.get(REV_GEO_URL, params=params, headers=HEADERS, timeout=30)
    if res.status_code != 200:
        return {}
    return res.json()


def chosen_area(elem):
    if elem["type"] == "node":
        lat = elem.get("lat")
        lon = elem.get("lon")
    else:
        center = elem.get("center")
        if center:
            lat = center.get("lat")
            lon = center.get("lon")
        else:
            return None
    tags = elem.get("tags", {}) or {}
    name = tags.get("name") or tags.get("name:en") or ""
    name_ascii = tags.get("name:ascii") or name
    name_en = tags.get("name:en") or name
    place_tag = tags.get("place", "town")
    return {
        "placename": name,
        "placename_ascii": name_ascii,
        "placename_en": name_en,
        "placetag": place_tag,
        "latitude": lat,
        "longitude": lon,
    }


def set_state_country(lat, lon):
    r = reverse_geocode(lat, lon)
    addr = r.get("address", {})
    state = addr.get("state") or addr.get("province") or addr.get("state_district")
    country = addr.get("country")
    return state, country


def set_city(city, state):
    """Use city/state to narrow search area/reduce response time"""
    query = f"{city}, {state}, USA"
    params = {"format": "jsonv2", "q": query, "limit": 1}
    res = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params=params,
        headers=HEADERS,
        timeout=30,
    )
    if res.status_code != 200 or not res.json():
        raise ValueError(f"Location not found: {city}, {state}")
    result = res.json()[0]
    lat, lon = float(result["lat"]), float(result["lon"])
    # Create 50km radius zone around city
    bbox_size = 0.45  # approx 50km
    return (lat - bbox_size, lon - bbox_size, lat + bbox_size, lon + bbox_size)


def road_search(roadway_name, city, state, buffer_m=500):
    bbox = set_city(city, state)
    print(f"Search area around {city}, {state}:", bbox)
    gpsx = find_roadway(roadway_name, bbox=bbox)
    print("Coordinates found:", len(gpsx))
    if not gpsx:
        raise ValueError(f"No locaton found: {roadway_name}")
    buff_geom = create_buffer(gpsx, buffer_m=buffer_m)
    bbox_search = global_area(buff_geom, expand_factor=0.02)
    print("Search area:", bbox_search)
    elements = search_zone(bbox_search)
    print("Places found in search area:", len(elements))
    results = []
    for e in elements:
        place = chosen_area(e)
        if not place:
            continue
        pt = Point(place["longitude"], place["latitude"])
        if not pt.within(buff_geom):
            continue
        state, country = set_state_country(place["latitude"], place["longitude"])
        result = {
            "roadway": roadway_name,
            "placename": place["placename"],
            "placename_ascii": place["placename_ascii"],
            "placename_en": place["placename_en"],
            "placetag": place["placetag"],
            "latitude": place["latitude"],
            "longitude": place["longitude"],
            "state/province": state or "",
            "state/province-ascii": state or "",
            "country": country or "",
        }
        results.append(result)
        time.sleep(1.0)
    # Deduplicate - avoid duplicaton
    found = set()
    deduped = []
    for r in results:
        key = (
            r["placename"],
            round(float(r["latitude"]), 6),
            round(float(r["longitude"]), 6),
        )
        if key in found:
            continue
        found.add(key)
        deduped.append(r)
    return deduped


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python jmc_rev_roadsearch.py <roadway_name> <city> <state>")
        print("Example: python jmc_rev_roadsearch.py 'I 95' 'Miami' 'Florida'")
        sys.exit(1)
    roadway = sys.argv[1]
    city = sys.argv[2]
    state = sys.argv[3]
    print(f"Searching for '{roadway}' near {city}, {state}")
    try:
        out = road_search(roadway, city, state, buffer_m=500)
        print(json.dumps(out, indent=2, ensure_ascii=False))
        filename = f"{roadway.replace(' ', '_')}_{city.replace(' ', '_')}_{state.replace(' ', '_')}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, ensure_ascii=False)
        print(f"Results saved to local directory as {filename}")
    except Exception as e:
        print(f"Error for {roadway} near {city}, {state}: {e}")
