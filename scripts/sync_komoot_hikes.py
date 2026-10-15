#!/usr/bin/env python3

import argparse
import json
import math
import urllib.parse
import urllib.request
from pathlib import Path


ACTIVITIES_URL = "https://www.komoot.com/api/v007/users/{user_id}/activities/"
OUTPUT_GEOJSON = Path("komoot_hikes.geojson")
OUTPUT_STATS = Path("komoot_hikes_stats.json")
AUSTRALIA_BOUNDS = {
    "min_lat": -44.5,
    "max_lat": -9.0,
    "min_lng": 112.0,
    "max_lng": 154.5,
}
MAX_ROUTE_POINTS = 650
USER_AGENT = "fuji-roadtrip-komoot-sync/1.0"


def fetch_json(url):
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/hal+json, application/json",
            "User-Agent": USER_AGENT,
        },
    )

    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def load_json(path, fallback):
    if not path.exists():
        return fallback

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return fallback


def activity_tour(activity):
    return (activity.get("_embedded") or {}).get("tour") or {}


def is_australian_hike(tour):
    start = tour.get("start_point") or {}
    lat = start.get("lat")
    lng = start.get("lng")

    if tour.get("sport") != "hike" or tour.get("type") != "tour_recorded":
        return False

    if lat is None or lng is None:
        return False

    return (
        AUSTRALIA_BOUNDS["min_lat"] <= float(lat) <= AUSTRALIA_BOUNDS["max_lat"]
        and AUSTRALIA_BOUNDS["min_lng"] <= float(lng) <= AUSTRALIA_BOUNDS["max_lng"]
    )


def fetch_public_activities(user_id):
    activities = []
    page = 0

    while True:
        query = urllib.parse.urlencode({"page": page, "limit": 50})
        payload = fetch_json(f"{ACTIVITIES_URL.format(user_id=user_id)}?{query}")
        activities.extend((payload.get("_embedded") or {}).get("items") or [])
        page_info = payload.get("page") or {}
        total_pages = int(page_info.get("totalPages") or 1)

        if page + 1 >= total_pages:
            break

        page += 1

    return activities


def simplify_points(points):
    if len(points) <= MAX_ROUTE_POINTS:
        return points

    step = math.ceil((len(points) - 1) / (MAX_ROUTE_POINTS - 1))
    simplified = points[::step]

    if simplified[-1] != points[-1]:
        simplified.append(points[-1])

    return simplified


def route_coordinates(tour_id):
    payload = fetch_json(f"https://api.komoot.de/v007/tours/{tour_id}/coordinates")
    points = simplify_points(payload.get("items") or [])
    coordinates = []

    for point in points:
        if point.get("lat") is None or point.get("lng") is None:
            continue

        coordinate = [round(float(point["lng"]), 6), round(float(point["lat"]), 6)]

        if point.get("alt") is not None:
            coordinate.append(round(float(point["alt"]), 1))

        coordinates.append(coordinate)

    return coordinates


def image_url(template):
    return (
        str(template)
        .replace("{width}", "1400")
        .replace("{height}", "1050")
        .replace("{crop}", "false")
    )


def tour_images(tour_id, fallback_images, title):
    try:
        payload = fetch_json(f"https://api.komoot.de/v007/tours/{tour_id}/cover_images/?limit=50")
        items = (payload.get("_embedded") or {}).get("items") or []
    except Exception as error:
        print(f"Warning: using activity images for Komoot tour {tour_id}: {error}")
        items = fallback_images or []

    images = []

    for item in items:
        source = item.get("src")

        if not source:
            continue

        images.append({
            "src": image_url(source),
            "alt": item.get("title") or item.get("caption") or f"{title} photo {len(images) + 1}",
        })

    return images


def format_duration(seconds):
    minutes = max(0, round(float(seconds or 0) / 60))
    hours, minutes = divmod(minutes, 60)

    if hours and minutes:
        return f"{hours}h {minutes}m"
    if hours:
        return f"{hours}h"
    return f"{minutes}m"


def feature_for(activity, previous_feature=None):
    tour = activity_tour(activity)
    tour_id = str(tour["id"])
    title = (tour.get("name") or activity.get("title") or "Komoot hike").strip()

    try:
        coordinates = route_coordinates(tour_id)
    except Exception as error:
        if previous_feature:
            print(f"Warning: keeping cached Komoot tour {tour_id}: {error}")
            return previous_feature
        print(f"Warning: skipping Komoot tour {tour_id}: {error}")
        return None

    if len(coordinates) < 2:
        return previous_feature

    distance_km = round(float(tour.get("distance") or 0) / 1000, 2)
    ascent_m = round(float(tour.get("elevation_up") or 0))
    descent_m = round(float(tour.get("elevation_down") or 0))
    duration = format_duration(tour.get("duration"))
    moving_time = format_duration(tour.get("time_in_motion"))
    date = str(tour.get("date") or "")[:10] or None
    description = (tour.get("description") or activity.get("text") or "").strip()
    images = tour_images(tour_id, activity.get("images"), title)

    return {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": coordinates,
        },
        "properties": {
            "id": f"komoot-{tour_id}",
            "komoot_id": int(tour_id),
            "source": "komoot",
            "source_url": f"https://www.komoot.com/tour/{tour_id}",
            "source_label": "View on Komoot",
            "title": title,
            "date": date,
            "summary": f"{distance_km:g} km | {ascent_m} m ascent | {moving_time} moving",
            "body": [description] if description else ["Recorded on Komoot."],
            "images": images,
            "tags": ["hike", "komoot"],
            "details": {
                "Distance": f"{distance_km:g} km",
                "Ascent": f"{ascent_m} m",
                "Descent": f"{descent_m} m",
                "Duration": duration,
                "Moving time": moving_time,
            },
            "start": coordinates[0][:2],
            "distance_km": distance_km,
            "ascent_m": ascent_m,
            "descent_m": descent_m,
            "duration_seconds": round(float(tour.get("duration") or 0)),
            "time_in_motion_seconds": round(float(tour.get("time_in_motion") or 0)),
            "started_at": tour.get("date"),
        },
    }


def sync(user_id):
    activities = fetch_public_activities(user_id)
    previous = load_json(OUTPUT_GEOJSON, {"features": []})
    previous_by_id = {
        str((feature.get("properties") or {}).get("komoot_id")): feature
        for feature in previous.get("features") or []
    }
    candidates = [
        activity
        for activity in activities
        if is_australian_hike(activity_tour(activity))
    ]
    candidates.sort(key=lambda item: activity_tour(item).get("date") or "", reverse=True)
    features = []

    for activity in candidates:
        tour_id = str(activity_tour(activity).get("id"))
        print(f"Syncing Komoot hike {tour_id}: {activity_tour(activity).get('name') or 'Hike'}")
        feature = feature_for(activity, previous_by_id.get(tour_id))

        if feature:
            features.append(feature)

    geojson = {"type": "FeatureCollection", "features": features}
    stats = {
        "hike_count": len(features),
        "distance_km": round(sum(item["properties"]["distance_km"] for item in features), 2),
        "ascent_m": round(sum(item["properties"]["ascent_m"] for item in features)),
        "descent_m": round(sum(item["properties"]["descent_m"] for item in features)),
        "source": "komoot",
        "user_id": str(user_id),
    }

    OUTPUT_GEOJSON.write_text(json.dumps(geojson, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    OUTPUT_STATS.write_text(json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Synced {len(features)} public Australian Komoot hikes")


def main():
    parser = argparse.ArgumentParser(description="Sync public Australian Komoot hikes into static GeoJSON.")
    parser.add_argument("--user-id", required=True, help="Public numeric Komoot user id")
    args = parser.parse_args()
    sync(args.user_id)


if __name__ == "__main__":
    main()
