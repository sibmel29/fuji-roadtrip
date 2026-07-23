import json
import math
from datetime import datetime
from pathlib import Path


SEGMENTS_FILE = Path("fourwd_segments.json")
OUTPUT_FILE = Path("fourwd-tracks.geojson")
STATS_FILE = Path("fourwd_stats.json")


def parse_time(value):
    if not value:
        return None

    value = str(value).strip()

    if not value:
        return None

    if value.endswith("Z"):
        value = value[:-1] + "+00:00"

    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def haversine_km(a, b):
    lon1, lat1 = a[:2]
    lon2, lat2 = b[:2]
    radius_km = 6371.0088
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    h = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * radius_km * math.asin(math.sqrt(h))


def line_distance_km(coordinates):
    return sum(
        haversine_km(coordinates[index - 1], coordinates[index])
        for index in range(1, len(coordinates))
    )


def load_feature(source):
    data = json.loads(Path(source.get("file", "")).read_text(encoding="utf-8"))
    features = data.get("features", [])
    feature_index = int(source.get("feature_index", 0))

    if not 0 <= feature_index < len(features):
        raise ValueError(f"feature_index {feature_index} is out of range for {source.get('file')}")

    return features[feature_index]


def coordinates_from_feature_range(source):
    feature = load_feature(source)
    coordinates = feature.get("geometry", {}).get("coordinates", [])
    start_index = int(source.get("start_index", 0))
    end_index = int(source.get("end_index", len(coordinates) - 1))

    if start_index > end_index:
        start_index, end_index = end_index, start_index

    return coordinates[max(start_index, 0): min(end_index + 1, len(coordinates))]


def coordinates_from_time_range(source):
    source_files = source.get("files") or ["route_live.geojson", "route_past.geojson"]
    start_time = parse_time(source.get("start_time"))
    end_time = parse_time(source.get("end_time"))

    if not start_time or not end_time:
        raise ValueError("time_range segments require start_time and end_time")

    if start_time > end_time:
        start_time, end_time = end_time, start_time

    selected = []

    for source_file in source_files:
        path = Path(source_file)
        if not path.exists():
            continue

        data = json.loads(path.read_text(encoding="utf-8"))

        for feature in data.get("features", []):
            coordinates = feature.get("geometry", {}).get("coordinates", [])
            times = feature.get("properties", {}).get("times", [])

            for coordinate, timestamp in zip(coordinates, times):
                point_time = parse_time(timestamp)

                if point_time and start_time <= point_time <= end_time:
                    selected.append(coordinate)

    return selected


def coordinates_for_segment(segment):
    if segment.get("geometry", {}).get("coordinates"):
        return segment["geometry"]["coordinates"]

    source = segment.get("source", {})
    source_type = source.get("type", "time_range")

    if source_type == "feature_range":
        return coordinates_from_feature_range(source)

    if source_type == "time_range":
        return coordinates_from_time_range(source)

    raise ValueError(f"Unsupported 4WD source type: {source_type}")


def feature_for_segment(segment):
    coordinates = coordinates_for_segment(segment)

    if len(coordinates) < 2:
        raise ValueError(f"Segment {segment.get('id')} does not contain enough points")

    distance_km = round(line_distance_km(coordinates), 2)
    difficulty = segment.get("difficulty", "")
    rating = segment.get("rating", "")
    details = {
        "Difficulty": difficulty,
        "Rating": rating,
        "Conditions": segment.get("conditions", ""),
        "Distance": f"{distance_km:g} km",
        "Time hint": segment.get("time_hint", ""),
    }

    return {
        "type": "Feature",
        "properties": {
            "id": segment.get("id"),
            "title": segment.get("title"),
            "date": segment.get("date", ""),
            "difficulty": difficulty,
            "rating": rating,
            "conditions": segment.get("conditions", ""),
            "distance_km": distance_km,
            "summary": segment.get("summary", ""),
            "body": segment.get("body", []),
            "images": segment.get("images", []),
            "tags": segment.get("tags", ["4wd"]),
            "published": segment.get("published", True),
            "details": details,
            "start": coordinates[0],
            "end": coordinates[-1],
        },
        "geometry": {
            "type": "LineString",
            "coordinates": coordinates,
        },
    }


def stats_for_features(features):
    published = [
        feature
        for feature in features
        if feature.get("properties", {}).get("published", True) is not False
    ]
    difficulty_counts = {}

    for feature in published:
        difficulty = feature.get("properties", {}).get("difficulty") or "unknown"
        difficulty_counts[difficulty] = difficulty_counts.get(difficulty, 0) + 1

    top_feature = sorted(
        published,
        key=lambda feature: (
            float(feature.get("properties", {}).get("rating") or 0),
            float(feature.get("properties", {}).get("distance_km") or 0),
        ),
        reverse=True,
    )

    return {
        "track_count": len(published),
        "distance_km": round(sum(float(feature.get("properties", {}).get("distance_km") or 0) for feature in published), 2),
        "difficulty_counts": difficulty_counts,
        "top_track": top_feature[0].get("properties", {}).get("title", "") if top_feature else "",
    }


def main():
    segments = json.loads(SEGMENTS_FILE.read_text(encoding="utf-8")) if SEGMENTS_FILE.exists() else []
    features = []

    for segment in segments:
        if segment.get("published", True) is False:
            continue

        try:
            features.append(feature_for_segment(segment))
        except Exception as exc:
            print(f"Skipping 4WD segment {segment.get('id', 'unknown')}: {exc}")

    OUTPUT_FILE.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    STATS_FILE.write_text(json.dumps(stats_for_features(features), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_FILE} with {len(features)} 4WD tracks")


if __name__ == "__main__":
    main()
