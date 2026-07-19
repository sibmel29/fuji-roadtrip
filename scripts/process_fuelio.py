#!/usr/bin/env python3
import csv
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPORT_DIR = Path(os.environ.get("FUELIO_EXPORT_DIR", ROOT / "fuelio" / "exports"))
ODO_PATH = ROOT / "odo.json"
STATS_PATH = ROOT / "fuelio_stats.json"
LOG_PATH = ROOT / "fuelio_log.json"


FIELD_ALIASES = {
    "date": [
        "date",
        "data",
        "datetime",
        "time",
        "fill date",
        "fuel-up date",
        "fuel up date",
        "refuel date",
    ],
    "odometer": [
        "odometer",
        "odo",
        "mileage",
        "mileage (km)",
        "odometer (km)",
        "odometer value",
        "meter reading",
    ],
    "liters": [
        "quantity",
        "quantity (l)",
        "qty",
        "liters",
        "litres",
        "volume",
        "fuel amount",
        "fuel amount (l)",
    ],
    "consumption": [
        "consumption",
        "fuel consumption",
        "fuel economy",
        "l/100km",
        "l/100 km",
        "liters/100km",
        "litres/100km",
        "liters per 100 km",
        "litres per 100 km",
    ],
    "cost": [
        "total cost",
        "total price",
        "price",
        "cost",
        "amount",
        "fuel cost",
    ],
    "station": [
        "station",
        "gas station",
        "petrol station",
        "place",
        "location",
        "city",
    ],
    "note": [
        "note",
        "notes",
        "comment",
        "description",
    ],
    "full_tank": [
        "full tank",
        "full",
        "full fill",
        "is full",
    ],
}


def normalize_header(value):
    value = (value or "").strip().lower()
    value = re.sub(r"\s+", " ", value)
    return value.replace("\ufeff", "")


def get_field(row, aliases):
    normalized = {normalize_header(key): value for key, value in row.items()}
    for alias in aliases:
        if alias in normalized:
            return normalized[alias]
    for key, value in normalized.items():
        for alias in aliases:
            if alias in key:
                return value
    return ""


def parse_number(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[^0-9,.\-]", "", text)
    if not text:
        return None
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def parse_date(value):
    text = (value or "").strip()
    if not text:
        return None
    text = re.sub(r"\s+", " ", text)
    formats = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%m/%d/%Y",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%d-%m-%Y %H:%M:%S",
        "%d %b %Y",
        "%d %B %Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_bool(value):
    text = (value or "").strip().lower()
    if text in {"1", "true", "yes", "y", "full"}:
        return True
    if text in {"0", "false", "no", "n", "partial"}:
        return False
    return None


def read_csv(path):
    raw = path.read_text(encoding="utf-8-sig", errors="replace")
    lines = raw.splitlines()
    for index, line in enumerate(lines):
        if line.strip().strip('"').lower() == "## log":
            section = []
            for section_line in lines[index + 1:]:
                if section_line.strip().strip('"').startswith("## "):
                    break
                if section_line.strip():
                    section.append(section_line)
            raw = "\n".join(section)
            break
    sample = raw[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return list(csv.DictReader(raw.splitlines(), dialect=dialect))


def load_odo():
    if ODO_PATH.exists():
        return json.loads(ODO_PATH.read_text(encoding="utf-8"))
    return {"current_odo": 0, "trip_start_odo": 0}


def display_path(path):
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def entry_sort_key(entry):
    parsed = entry.get("_date")
    return (parsed or datetime.min, entry["odometer"])


def normalize_log_entry(row):
    odometer = parse_number(row.get("odometer") or row.get("odo") or row.get("current_odo"))
    if odometer is None:
        return None
    liters = parse_number(row.get("liters") or row.get("litres") or row.get("quantity"))
    cost = parse_number(row.get("cost") or row.get("total_cost") or row.get("price"))
    consumption = parse_number(row.get("consumption_l_per_100km") or row.get("consumption"))
    date_text = str(row.get("date") or "").strip()
    parsed_date = parse_date(date_text)
    entry = {
        "date": parsed_date.date().isoformat() if parsed_date else date_text,
        "_date": parsed_date,
        "odometer": round(odometer),
        "liters": round(liters, 2) if liters is not None else None,
        "consumption_l_per_100km": round(consumption, 2) if consumption is not None else None,
        "cost": round(cost, 2) if cost is not None else None,
        "station": str(row.get("station") or "").strip(),
        "note": str(row.get("note") or "").strip(),
        "source": str(row.get("source") or "fuelio_log.json"),
    }
    if "full_tank" in row:
        entry["full_tank"] = row["full_tank"]
    if "id" in row:
        entry["id"] = row["id"]
    return entry


def collect_log_entries():
    if not LOG_PATH.exists():
        return []
    data = json.loads(LOG_PATH.read_text(encoding="utf-8"))
    rows = data if isinstance(data, list) else data.get("entries", [])
    entries = []
    for row in rows:
        entry = normalize_log_entry(row)
        if entry:
            entries.append(entry)
    return entries


def collect_entries():
    entries = collect_log_entries()
    files = []
    if entries:
        files.append("fuelio_log.json")
    for path in sorted(EXPORT_DIR.glob("*.csv")):
        source = display_path(path)
        files.append(source)
        for row in read_csv(path):
            odometer = parse_number(get_field(row, FIELD_ALIASES["odometer"]))
            if odometer is None:
                continue
            liters = parse_number(get_field(row, FIELD_ALIASES["liters"]))
            consumption = parse_number(get_field(row, FIELD_ALIASES["consumption"]))
            cost = parse_number(get_field(row, FIELD_ALIASES["cost"]))
            date_text = get_field(row, FIELD_ALIASES["date"])
            parsed_date = parse_date(date_text)
            station = get_field(row, FIELD_ALIASES["station"]).strip()
            note = get_field(row, FIELD_ALIASES["note"]).strip()
            full_tank = parse_bool(get_field(row, FIELD_ALIASES["full_tank"]))
            entries.append({
                "date": parsed_date.date().isoformat() if parsed_date else date_text.strip(),
                "_date": parsed_date,
                "odometer": round(odometer),
                "liters": round(liters, 2) if liters is not None else None,
                "consumption_l_per_100km": round(consumption, 2) if consumption is not None else None,
                "cost": round(cost, 2) if cost is not None else None,
                "station": station,
                "note": note,
                "full_tank": full_tank,
                "source": source,
            })
    entries.sort(key=entry_sort_key)
    return entries, files


def dedupe_entries(entries):
    deduped = {}
    for entry in entries:
        key = (
            entry.get("date"),
            entry.get("odometer"),
            entry.get("liters"),
            entry.get("cost"),
        )
        deduped[key] = entry
    return sorted(deduped.values(), key=entry_sort_key)


def calculate_stats(entries, odo):
    trip_start = round(parse_number(odo.get("trip_start_odo")) or 0)
    current_odo = max([round(parse_number(odo.get("current_odo")) or 0)] + [entry["odometer"] for entry in entries])
    trip_entries = [entry for entry in entries if entry["odometer"] >= trip_start]
    fuel_entries = [entry for entry in trip_entries if entry.get("liters") is not None]
    liters = sum(entry["liters"] for entry in fuel_entries)
    costs = [entry["cost"] for entry in fuel_entries if entry.get("cost") is not None]
    total_cost = sum(costs) if costs else None
    distance = max(0, current_odo - trip_start)
    exported_consumption = [entry["consumption_l_per_100km"] for entry in fuel_entries if entry.get("consumption_l_per_100km") is not None]
    if exported_consumption:
        average = sum(exported_consumption) / len(exported_consumption)
        fuel_distance = None
    elif len(fuel_entries) >= 2:
        fuel_distance = fuel_entries[-1]["odometer"] - fuel_entries[0]["odometer"]
        fuel_liters = sum(entry["liters"] for entry in fuel_entries[1:] if entry.get("liters") is not None)
        average = (fuel_liters / fuel_distance * 100) if fuel_liters and fuel_distance > 0 else None
    else:
        average = None
        fuel_distance = None
    latest = entries[-1] if entries else None

    def public_entry(entry):
        if not entry:
            return None
        return {key: value for key, value in entry.items() if not key.startswith("_") and value not in {"", None}}

    return {
        "updated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source_files": sorted({entry["source"] for entry in entries}),
        "entries_count": len(entries),
        "current_odo": current_odo,
        "trip_start_odo": trip_start,
        "trip_distance_km": distance,
        "latest_entry": public_entry(latest),
        "history": [public_entry(entry) for entry in reversed(entries[-24:])],
        "fuel": {
            "fills": len(fuel_entries),
            "liters": round(liters, 2) if fuel_entries else None,
            "cost": round(total_cost, 2) if total_cost is not None else None,
            "average_l_per_100km": round(average, 2) if average is not None else None,
            "distance_km": round(fuel_distance, 2) if fuel_distance is not None else None,
        },
    }


def main():
    odo = load_odo()
    entries, files = collect_entries()
    entries = dedupe_entries(entries)
    if not entries:
        print(f"No Fuelio entries found in {LOG_PATH} or {EXPORT_DIR}")
        return

    stats = calculate_stats(entries, odo)
    STATS_PATH.write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")

    odo["current_odo"] = stats["current_odo"]
    odo["trip_start_odo"] = stats["trip_start_odo"]
    ODO_PATH.write_text(json.dumps(odo, indent=2) + "\n", encoding="utf-8")

    print(f"Processed {stats['entries_count']} Fuelio entries from {', '.join(files)}")
    print(f"Current ODO: {stats['current_odo']:,} km")
    average = stats["fuel"]["average_l_per_100km"]
    if average is not None:
        print(f"Average consumption: {average} L/100 km")


if __name__ == "__main__":
    main()
