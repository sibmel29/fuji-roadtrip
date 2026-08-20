#!/usr/bin/env python3
"""
Extract likely van overnight spots from Google Timeline / Location History JSON.

The script runs several detection profiles against the same input so the outputs
can be compared before choosing the best thresholds.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


GEO_RE = re.compile(r"geo:\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)", re.I)
LAT_LNG_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*°?\s*,\s*(-?\d+(?:\.\d+)?)\s*°?")
EARTH_RADIUS_M = 6_371_000
DEFAULT_START_DATE = date(2025, 11, 1)


@dataclass(frozen=True)
class Profile:
    name: str
    overnight_start_hour: int
    overnight_end_hour: int
    settle_start_hour: int
    settle_end_hour: int
    radius_m: float
    min_duration_minutes: int
    min_settle_overlap_minutes: int
    dedupe_radius_m: float
    morning_confirm_radius_m: float
    description: str


PROFILES = [
    Profile(
        name="strict",
        overnight_start_hour=19,
        overnight_end_hour=7,
        settle_start_hour=20,
        settle_end_hour=22,
        radius_m=700,
        min_duration_minutes=180,
        min_settle_overlap_minutes=45,
        dedupe_radius_m=250,
        morning_confirm_radius_m=700,
        description="Fewer, higher-confidence nights: tight stop radius, longer stop, tiny true-spot grouping.",
    ),
    Profile(
        name="balanced",
        overnight_start_hour=18,
        overnight_end_hour=8,
        settle_start_hour=20,
        settle_end_hour=22,
        radius_m=1_000,
        min_duration_minutes=120,
        min_settle_overlap_minutes=20,
        dedupe_radius_m=500,
        morning_confirm_radius_m=1_000,
        description="Default first pass: 1km stop detection, 500m true-spot grouping.",
    ),
    Profile(
        name="loose",
        overnight_start_hour=17,
        overnight_end_hour=9,
        settle_start_hour=19,
        settle_end_hour=23,
        radius_m=1_500,
        min_duration_minutes=90,
        min_settle_overlap_minutes=0,
        dedupe_radius_m=1_000,
        morning_confirm_radius_m=1_500,
        description="More inclusive: sparse phone-off nights, grouped only within 1km.",
    ),
]


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return EARTH_RADIUS_M * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def parse_time(value: Any) -> datetime | None:
    if value is None:
        return None

    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)

    if not isinstance(value, str) or not value.strip():
        return None

    text = value.strip()
    if text.isdigit():
        return parse_time(int(text))

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def parse_coordinate(value: Any, is_lat: bool) -> float | None:
    if value is None:
        return None

    try:
        coordinate = float(value)
    except (TypeError, ValueError):
        return None

    if abs(coordinate) > 180:
        coordinate /= 10_000_000

    if is_lat and not -90 <= coordinate <= 90:
        return None

    if not is_lat and not -180 <= coordinate <= 180:
        return None

    return coordinate


def parse_accuracy_m(item: dict[str, Any]) -> float | None:
    for key in ("accuracy", "accuracyMeters", "horizontalAccuracy", "horizontalAccuracyMeters"):
        if key not in item:
            continue

        try:
            value = float(item[key])
        except (TypeError, ValueError):
            continue

        if value >= 0:
            return value

    return None


def first_time_from_dict(item: dict[str, Any], keys: tuple[str, ...]) -> datetime | None:
    for key in keys:
        parsed = parse_time(item.get(key))
        if parsed:
            return parsed
    return None


def duration_times(item: dict[str, Any]) -> tuple[datetime | None, datetime | None]:
    duration = item.get("duration")
    if isinstance(duration, dict):
        start = first_time_from_dict(duration, ("startTimestamp", "startTime", "start", "from"))
        end = first_time_from_dict(duration, ("endTimestamp", "endTime", "end", "to"))
        return start, end
    return None, None


def coordinates_from_dict(item: dict[str, Any]) -> tuple[float, float] | None:
    candidates = [
        ("latitudeE7", "longitudeE7"),
        ("latE7", "lngE7"),
        ("latE7", "lonE7"),
        ("latitude", "longitude"),
        ("lat", "lng"),
        ("lat", "lon"),
    ]

    for lat_key, lon_key in candidates:
        if lat_key in item and lon_key in item:
            lat = parse_coordinate(item.get(lat_key), True)
            lon = parse_coordinate(item.get(lon_key), False)
            if lat is not None and lon is not None:
                return lat, lon

    for key in ("geo", "point", "latLng", "centerLatLng", "placeLocation", "location", "startLocation", "endLocation"):
        value = item.get(key)

        if isinstance(value, str):
            match = GEO_RE.search(value) or LAT_LNG_RE.search(value)
            if match:
                return float(match.group(1)), float(match.group(2))

        if isinstance(value, dict):
            nested = coordinates_from_dict(value)
            if nested:
                return nested

    return None


def diagnose_json_shape(obj: Any) -> dict[str, Any]:
    stats = {
        "dict_count": 0,
        "list_count": 0,
        "time_like_key_count": 0,
        "coordinate_like_key_count": 0,
        "geo_string_count": 0,
        "lat_lng_string_count": 0,
        "common_keys": {},
        "example_coordinate_paths": [],
        "example_time_paths": [],
    }

    time_keys = {
        "timestamp",
        "timestampMs",
        "startTimestamp",
        "endTimestamp",
        "startTime",
        "endTime",
        "time",
    }
    coord_keys = {
        "latitudeE7",
        "longitudeE7",
        "latE7",
        "lngE7",
        "latitude",
        "longitude",
        "lat",
        "lng",
        "lon",
        "latLng",
        "centerLatLng",
        "geo",
        "point",
    }

    def walk(value: Any, path: str = "$") -> None:
        if isinstance(value, dict):
            stats["dict_count"] += 1

            for key, child in value.items():
                stats["common_keys"][key] = stats["common_keys"].get(key, 0) + 1

                if key in time_keys:
                    stats["time_like_key_count"] += 1
                    if len(stats["example_time_paths"]) < 8:
                        stats["example_time_paths"].append(f"{path}.{key}")

                if key in coord_keys:
                    stats["coordinate_like_key_count"] += 1
                    if len(stats["example_coordinate_paths"]) < 8:
                        stats["example_coordinate_paths"].append(f"{path}.{key}")

                if isinstance(child, str):
                    if GEO_RE.search(child):
                        stats["geo_string_count"] += 1
                    elif key.lower().endswith("latlng") and LAT_LNG_RE.search(child):
                        stats["lat_lng_string_count"] += 1

                walk(child, f"{path}.{key}")

        elif isinstance(value, list):
            stats["list_count"] += 1
            for index, child in enumerate(value[:200]):
                walk(child, f"{path}[{index}]")

    walk(obj)
    stats["common_keys"] = dict(sorted(stats["common_keys"].items(), key=lambda item: item[1], reverse=True)[:25])
    return stats


def collect_points(obj: Any, inherited_start: datetime | None = None, inherited_end: datetime | None = None) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []

    if isinstance(obj, list):
        for item in obj:
            points.extend(collect_points(item, inherited_start, inherited_end))
        return points

    if not isinstance(obj, dict):
        return points

    duration_start, duration_end = duration_times(obj)
    local_start = (
        first_time_from_dict(obj, ("timestamp", "timestampMs", "startTimestamp", "startTime", "time", "rawTime"))
        or duration_start
        or inherited_start
    )
    local_end = (
        first_time_from_dict(obj, ("endTimestamp", "endTime", "stopTime"))
        or duration_end
        or inherited_end
    )

    coordinates = coordinates_from_dict(obj)
    if coordinates and (local_start or local_end):
        if local_start and local_end:
            timestamp = local_start + (local_end - local_start) / 2
        else:
            timestamp = local_start or local_end

        points.append(
            {
                "time": timestamp,
                "lat": round(coordinates[0], 7),
                "lon": round(coordinates[1], 7),
                "accuracy_m": parse_accuracy_m(obj),
            }
        )

    for value in obj.values():
        if isinstance(value, (dict, list)):
            points.extend(collect_points(value, local_start, local_end))

    return points


def load_points(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text())
    points = collect_points(data)

    unique = {}
    for point in points:
        key = (point["time"].isoformat(), point["lat"], point["lon"])
        unique[key] = point

    return sorted(unique.values(), key=lambda point: point["time"])


def parse_date_arg(value: str, label: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(f"{label} must use YYYY-MM-DD format, got {value!r}") from exc


def filter_points_by_date(points: list[dict[str, Any]], start_date: date, end_date: date, tz: ZoneInfo) -> list[dict[str, Any]]:
    return [
        point
        for point in points
        if start_date <= point["time"].astimezone(tz).date() <= end_date
    ]


def night_window(day: date, profile: Profile, tz: ZoneInfo) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time(profile.overnight_start_hour), tzinfo=tz)
    end_day = day + timedelta(days=1) if profile.overnight_end_hour <= profile.overnight_start_hour else day
    end = datetime.combine(end_day, time(profile.overnight_end_hour), tzinfo=tz)
    return start, end


def settle_window(day: date, profile: Profile, tz: ZoneInfo) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time(profile.settle_start_hour), tzinfo=tz)
    end_day = day + timedelta(days=1) if profile.settle_end_hour <= profile.settle_start_hour else day
    end = datetime.combine(end_day, time(profile.settle_end_hour), tzinfo=tz)
    return start, end


def overlap_minutes(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> float:
    latest_start = max(a_start, b_start)
    earliest_end = min(a_end, b_end)
    seconds = (earliest_end - latest_start).total_seconds()
    return max(0, seconds / 60)


def best_observed_point(cluster: list[dict[str, Any]], settle_start: datetime, settle_end: datetime, tz: ZoneInfo) -> dict[str, Any]:
    def score(point: dict[str, Any]) -> tuple[int, float, float]:
        local_time = point["time"].astimezone(tz)
        in_settle = settle_start <= local_time <= settle_end
        accuracy = point["accuracy_m"] if point.get("accuracy_m") is not None else 9_999
        return (1 if in_settle else 0, local_time.timestamp(), -accuracy)

    return max(cluster, key=score)


def first_morning_point(day: date, points: list[dict[str, Any]], tz: ZoneInfo) -> dict[str, Any] | None:
    start = datetime.combine(day + timedelta(days=1), time(5), tzinfo=tz)
    end = datetime.combine(day + timedelta(days=1), time(9), tzinfo=tz)

    for point in points:
        local_time = point["time"].astimezone(tz)
        if start <= local_time <= end:
            return point

    return None


def cluster_points(points: list[dict[str, Any]], radius_m: float) -> list[list[dict[str, Any]]]:
    clusters: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []

    for point in points:
        if not current:
            current = [point]
            continue

        center_lat = sum(item["lat"] for item in current) / len(current)
        center_lon = sum(item["lon"] for item in current) / len(current)
        distance = haversine_m(center_lat, center_lon, point["lat"], point["lon"])

        if distance <= radius_m:
            current.append(point)
        else:
            clusters.append(current)
            current = [point]

    if current:
        clusters.append(current)

    return clusters


def candidate_for_night(day: date, points: list[dict[str, Any]], profile: Profile, tz: ZoneInfo) -> dict[str, Any] | None:
    window_start, window_end = night_window(day, profile, tz)
    settle_start, settle_end = settle_window(day, profile, tz)

    window_points = [
        point
        for point in points
        if window_start <= point["time"].astimezone(tz) <= window_end
    ]

    if len(window_points) < 2:
        return None

    candidates = []
    for cluster in cluster_points(window_points, profile.radius_m):
        if len(cluster) < 2:
            continue

        start = cluster[0]["time"].astimezone(tz)
        end = cluster[-1]["time"].astimezone(tz)
        duration = (end - start).total_seconds() / 60
        settle_overlap = overlap_minutes(start, end, settle_start, settle_end)

        if duration < profile.min_duration_minutes:
            continue

        if settle_overlap < profile.min_settle_overlap_minutes:
            continue

        center_lat = sum(item["lat"] for item in cluster) / len(cluster)
        center_lon = sum(item["lon"] for item in cluster) / len(cluster)
        spread = max(haversine_m(center_lat, center_lon, item["lat"], item["lon"]) for item in cluster)
        best_point = best_observed_point(cluster, settle_start, settle_end, tz)
        best_local_time = best_point["time"].astimezone(tz)
        morning_point = first_morning_point(day, points, tz)
        morning_distance_m = None
        morning_confirmed = False

        if morning_point:
            morning_distance_m = haversine_m(best_point["lat"], best_point["lon"], morning_point["lat"], morning_point["lon"])
            morning_confirmed = morning_distance_m <= profile.morning_confirm_radius_m

        score = duration + (settle_overlap * 2) - (spread / 100)
        if morning_confirmed:
            score += 90
        if best_point.get("accuracy_m") is not None:
            score -= min(best_point["accuracy_m"], 500) / 20

        candidates.append(
            {
                "night": day.isoformat(),
                "coordinates": [round(best_point["lon"], 6), round(best_point["lat"], 6)],
                "start": start.isoformat(),
                "end": end.isoformat(),
                "chosen_point_time": best_local_time.isoformat(),
                "chosen_point_accuracy_m": best_point.get("accuracy_m"),
                "duration_hours": round(duration / 60, 2),
                "settle_overlap_minutes": round(settle_overlap, 1),
                "point_count": len(cluster),
                "spread_m": round(spread),
                "cluster_center_coordinates": [round(center_lon, 6), round(center_lat, 6)],
                "morning_confirmed": morning_confirmed,
                "morning_distance_m": round(morning_distance_m) if morning_distance_m is not None else None,
                "score": round(score, 1),
            }
        )

    if not candidates:
        return None

    return max(candidates, key=lambda item: item["score"])


def merge_spots(candidates: list[dict[str, Any]], profile: Profile) -> list[dict[str, Any]]:
    spots: list[dict[str, Any]] = []

    for candidate in sorted(candidates, key=lambda item: item["night"]):
        lon, lat = candidate["coordinates"]
        match = None

        for spot in spots:
            spot_lon, spot_lat = spot["coordinates"]
            distance_m = haversine_m(lat, lon, spot_lat, spot_lon)
            if distance_m <= profile.dedupe_radius_m:
                match = spot
                break

        if match is None:
            match = {
                "coordinates": [lon, lat],
                "nights": [],
                "nightly_candidates": [],
                "first_night": candidate["night"],
                "last_night": candidate["night"],
                "max_spread_m": candidate["spread_m"],
                "total_point_count": 0,
                "representative_score": candidate["score"],
                "representative_night": candidate["night"],
                "morning_confirmed_count": 0,
            }
            spots.append(match)

        match["nights"].append(candidate["night"])
        match["nightly_candidates"].append(candidate)
        match["first_night"] = min(match["first_night"], candidate["night"])
        match["last_night"] = max(match["last_night"], candidate["night"])
        match["max_spread_m"] = max(match["max_spread_m"], candidate["spread_m"])
        match["total_point_count"] += candidate["point_count"]
        match["morning_confirmed_count"] += 1 if candidate.get("morning_confirmed") else 0

        if candidate["score"] > match["representative_score"]:
            match["coordinates"] = candidate["coordinates"]
            match["representative_score"] = candidate["score"]
            match["representative_night"] = candidate["night"]

    for index, spot in enumerate(spots, start=1):
        spot["id"] = f"{profile.name}-van-night-{index:03d}"
        spot["nights"] = sorted(spot["nights"])
        spot["night_count"] = len(spot["nights"])

    return spots


def confidence_for_candidate(candidate: dict[str, Any], profile: Profile) -> str:
    if (
        candidate["duration_hours"] >= max(4, profile.min_duration_minutes / 60 + 1)
        and candidate["settle_overlap_minutes"] >= max(45, profile.min_settle_overlap_minutes)
        and candidate["spread_m"] <= profile.radius_m
    ):
        return "high"

    if candidate["duration_hours"] >= profile.min_duration_minutes / 60:
        return "medium"

    return "low"


def spots_geojson(spots: list[dict[str, Any]], profile: Profile) -> dict[str, Any]:
    features = []

    for spot in spots:
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": spot["coordinates"],
                },
                "properties": {
                    "id": spot["id"],
                    "type": "van-night",
                    "profile": profile.name,
                    "first_night": spot["first_night"],
                    "last_night": spot["last_night"],
                    "night_count": spot["night_count"],
                    "nights": spot["nights"],
                    "max_spread_m": spot["max_spread_m"],
                    "dedupe_radius_m": profile.dedupe_radius_m,
                    "representative_night": spot["representative_night"],
                    "morning_confirmed_count": spot["morning_confirmed_count"],
                    "title": f"Van night spot x{spot['night_count']}",
                },
            }
        )

    return {"type": "FeatureCollection", "features": features}


def nightly_geojson(candidates: list[dict[str, Any]], profile: Profile) -> dict[str, Any]:
    features = []

    for index, candidate in enumerate(candidates, start=1):
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": candidate["coordinates"],
                },
                "properties": {
                    "id": f"{profile.name}-van-nightly-{index:03d}",
                    "type": "van-nightly",
                    "profile": profile.name,
                    "night": candidate["night"],
                    "confidence": candidate.get("confidence"),
                    "chosen_point_time": candidate["chosen_point_time"],
                    "chosen_point_accuracy_m": candidate["chosen_point_accuracy_m"],
                    "duration_hours": candidate["duration_hours"],
                    "settle_overlap_minutes": candidate["settle_overlap_minutes"],
                    "point_count": candidate["point_count"],
                    "spread_m": candidate["spread_m"],
                    "morning_confirmed": candidate["morning_confirmed"],
                    "morning_distance_m": candidate["morning_distance_m"],
                    "score": candidate["score"],
                    "title": f"Van night {candidate['night']}",
                },
            }
        )

    return {"type": "FeatureCollection", "features": features}


def write_outputs(output_dir: Path, profile: Profile, candidates: list[dict[str, Any]], spots: list[dict[str, Any]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "profile": profile.__dict__,
        "nightly_candidate_count": len(candidates),
        "deduped_spot_count": len(spots),
        "nightly_candidates": candidates,
        "deduped_spots": spots,
    }

    (output_dir / f"van_nights_{profile.name}.json").write_text(json.dumps(payload, indent=2) + "\n")
    (output_dir / f"van_nights_{profile.name}_nightly.geojson").write_text(
        json.dumps(nightly_geojson(candidates, profile), indent=2) + "\n"
    )
    (output_dir / f"van_nights_{profile.name}_spots.geojson").write_text(
        json.dumps(spots_geojson(spots, profile), indent=2) + "\n"
    )
    (output_dir / f"van_nights_{profile.name}.geojson").write_text(
        json.dumps(spots_geojson(spots, profile), indent=2) + "\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare van-night extraction profiles from Google Timeline JSON.")
    parser.add_argument("timeline_json", type=Path, help="Path to Google Timeline / Location History JSON.")
    parser.add_argument("--timezone", default="Australia/Brisbane", help="Timezone used for night windows.")
    parser.add_argument("--output-dir", type=Path, default=Path("van-nights-output"), help="Output folder.")
    parser.add_argument("--start-date", default=DEFAULT_START_DATE.isoformat(), help="First local date to inspect, YYYY-MM-DD.")
    parser.add_argument("--end-date", default=None, help="Last local date to inspect, YYYY-MM-DD. Defaults to today in --timezone.")
    parser.add_argument("--diagnose", action="store_true", help="Print the detected JSON shape without extracting nights.")
    args = parser.parse_args()

    raw_data = json.loads(args.timeline_json.read_text())

    if args.diagnose:
        print(json.dumps(diagnose_json_shape(raw_data), indent=2))
        return

    tz = ZoneInfo(args.timezone)
    start_date = parse_date_arg(args.start_date, "--start-date")
    end_date = parse_date_arg(args.end_date, "--end-date") if args.end_date else datetime.now(tz).date()

    if end_date < start_date:
        raise SystemExit("--end-date must be on or after --start-date")

    all_points = load_points(args.timeline_json)
    points = filter_points_by_date(all_points, start_date, end_date, tz)

    if not points:
        print("No timestamped GPS points found in the Timeline file.")
        print(f"Date filter: {start_date.isoformat()} to {end_date.isoformat()} in {args.timezone}")
        print(f"Recognized timestamped GPS points before date filtering: {len(all_points)}")
        print()
        print("Diagnostic summary:")
        print(json.dumps(diagnose_json_shape(raw_data), indent=2))
        print()
        raise SystemExit(
            "The file is valid JSON, but this script still does not recognize its coordinate/time structure."
        )

    first_day = points[0]["time"].astimezone(tz).date()
    last_day = points[-1]["time"].astimezone(tz).date()
    days = [first_day + timedelta(days=offset) for offset in range((last_day - first_day).days + 1)]

    comparison = []

    for profile in PROFILES:
        candidates = []

        for day in days:
            candidate = candidate_for_night(day, points, profile, tz)
            if candidate:
                candidate["confidence"] = confidence_for_candidate(candidate, profile)
                candidates.append(candidate)

        spots = merge_spots(candidates, profile)
        write_outputs(args.output_dir, profile, candidates, spots)

        comparison.append(
            {
                "profile": profile.name,
                "description": profile.description,
                "nightly_candidates": len(candidates),
                "deduped_spots": len(spots),
                "radius_m": profile.radius_m,
                "min_duration_minutes": profile.min_duration_minutes,
                "dedupe_radius_m": profile.dedupe_radius_m,
                "morning_confirm_radius_m": profile.morning_confirm_radius_m,
            }
        )

    (args.output_dir / "van_nights_comparison.json").write_text(json.dumps(comparison, indent=2) + "\n")

    with (args.output_dir / "van_nights_comparison.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(comparison[0].keys()))
        writer.writeheader()
        writer.writerows(comparison)

    print(f"Read {len(points)} timestamped GPS points from {args.timeline_json}")
    print(f"Date filter: {start_date.isoformat()} to {end_date.isoformat()} in {args.timezone}")
    print(f"Date range found: {first_day.isoformat()} to {last_day.isoformat()} ({len(days)} nights checked)")
    print()
    for item in comparison:
        print(
            f"{item['profile']}: "
            f"{item['nightly_candidates']} nightly candidates, "
            f"{item['deduped_spots']} deduped spots"
        )
    print()
    print(f"Wrote outputs to {args.output_dir}")


if __name__ == "__main__":
    main()
