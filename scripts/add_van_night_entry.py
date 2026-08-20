import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path


VAN_NIGHTS_FILE = Path(os.environ.get("VAN_NIGHTS_FILE", "van-nights.geojson"))


def slugify(value):
    slug = re.sub(r"[^a-z0-9]+", "-", str(value).strip().lower())
    return slug.strip("-") or "van-night"


def payload_value(payload, env_name, key, default=""):
    value = os.environ.get(env_name)
    if value not in (None, ""):
        return value
    return payload.get(key, default)


def numeric(value, field):
    if value in (None, ""):
        raise ValueError(f"{field} is required")

    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a number") from exc


def bool_value(value, default=True):
    if value in (None, ""):
        return default
    return str(value).strip().lower() not in {"0", "false", "no", "draft"}


def load_payload():
    raw = os.environ.get("CLIENT_PAYLOAD", "{}")
    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        payload = {}
    return payload if isinstance(payload, dict) else {}


def load_geojson():
    if VAN_NIGHTS_FILE.exists():
        return json.loads(VAN_NIGHTS_FILE.read_text(encoding="utf-8"))
    return {"type": "FeatureCollection", "features": []}


def unique_id(base_id, features):
    existing = {feature.get("properties", {}).get("id") for feature in features}

    if base_id not in existing:
        return base_id

    index = 2
    while f"{base_id}-{index}" in existing:
        index += 1

    return f"{base_id}-{index}"


def main():
    payload = load_payload()
    data = load_geojson()
    features = data.setdefault("features", [])

    title = payload_value(payload, "VAN_NIGHT_TITLE", "title", "Van night spot").strip() or "Van night spot"
    date = payload_value(payload, "VAN_NIGHT_DATE", "date", "")
    latitude = numeric(payload_value(payload, "VAN_NIGHT_LATITUDE", "latitude", ""), "latitude")
    longitude = numeric(payload_value(payload, "VAN_NIGHT_LONGITUDE", "longitude", ""), "longitude")

    if not -90 <= latitude <= 90:
      raise ValueError("latitude must be between -90 and 90")
    if not -180 <= longitude <= 180:
      raise ValueError("longitude must be between -180 and 180")

    notes = payload_value(payload, "VAN_NIGHT_NOTES", "notes", "")
    vibe = payload_value(payload, "VAN_NIGHT_VIBE", "vibe", "")
    facilities = payload_value(payload, "VAN_NIGHT_FACILITIES", "facilities", "")
    warnings = payload_value(payload, "VAN_NIGHT_WARNINGS", "warnings", "")
    published = bool_value(payload_value(payload, "VAN_NIGHT_PUBLISHED", "published", True), True)
    base_id = slugify(payload_value(payload, "VAN_NIGHT_ID", "id", f"{date}-{title}"))
    entry_id = unique_id(base_id, features)

    feature = {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [round(longitude, 6), round(latitude, 6)],
        },
        "properties": {
            "id": entry_id,
            "type": "van-night",
            "profile": "manual",
            "source_profile": "manual",
            "source_profiles": ["manual"],
            "title": title,
            "first_night": date,
            "last_night": date,
            "night_count": 1,
            "nights": [date] if date else [],
            "note": notes,
            "vibe": vibe,
            "facilities": facilities,
            "warnings": warnings,
            "published": published,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    }

    features.insert(0, feature)
    VAN_NIGHTS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Added van night spot {entry_id}: {title}")


if __name__ == "__main__":
    main()
