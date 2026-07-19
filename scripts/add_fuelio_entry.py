#!/usr/bin/env python3
import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = ROOT / "fuelio_log.json"
RESULT_PATH = ROOT / "fuelio_entry_result.json"


def parse_payload():
    raw = os.environ.get("CLIENT_PAYLOAD", "").strip()
    payload = json.loads(raw) if raw and raw != "null" else {}
    for key in ["date", "odometer", "liters", "cost", "station", "note", "full_tank", "consumption_l_per_100km"]:
        env_value = os.environ.get(f"FUELIO_{key.upper()}")
        if env_value not in {None, ""}:
            payload[key] = env_value
    return payload


def parse_number(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = re.sub(r"[^0-9,.\-]", "", text)
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


def parse_bool(value):
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "y", "full"}:
        return True
    if text in {"0", "false", "no", "n", "partial"}:
        return False
    return None


def normalize_date(value):
    text = str(value or "").strip()
    if not text:
        return datetime.utcnow().date().isoformat()
    for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"]:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return text


def load_log():
    if not LOG_PATH.exists():
        return {"entries": []}
    data = json.loads(LOG_PATH.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return {"entries": data}
    data.setdefault("entries", [])
    return data


def entry_id(entry):
    raw = "|".join(str(entry.get(key, "")) for key in ["date", "odometer", "liters", "cost", "station"])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def normalize_entry(payload):
    odometer = parse_number(payload.get("odometer") or payload.get("odo") or payload.get("current_odo"))
    if odometer is None:
        raise ValueError("A Fuelio entry needs an odometer value.")

    entry = {
        "date": normalize_date(payload.get("date")),
        "odometer": round(odometer),
        "source": "macrodroid",
    }
    liters = parse_number(payload.get("liters") or payload.get("litres") or payload.get("quantity"))
    cost = parse_number(payload.get("cost") or payload.get("total_cost") or payload.get("price"))
    consumption = parse_number(payload.get("consumption_l_per_100km") or payload.get("consumption"))
    full_tank = parse_bool(payload.get("full_tank"))

    if liters is not None:
        entry["liters"] = round(liters, 2)
    if cost is not None:
        entry["cost"] = round(cost, 2)
    if consumption is not None:
        entry["consumption_l_per_100km"] = round(consumption, 2)
    if full_tank is not None:
        entry["full_tank"] = full_tank

    for key in ["station", "note"]:
        value = str(payload.get(key) or "").strip()
        if value:
            entry[key] = value

    entry["id"] = str(payload.get("id") or entry_id(entry))
    return entry


def sort_key(entry):
    return (str(entry.get("date", "")), int(entry.get("odometer", 0)), str(entry.get("id", "")))


def main():
    entry = normalize_entry(parse_payload())
    data = load_log()
    entries = [existing for existing in data["entries"] if existing.get("id") != entry["id"]]
    action = "updated" if len(entries) != len(data["entries"]) else "added"
    entries.append(entry)
    data["entries"] = sorted(entries, key=sort_key)
    LOG_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    RESULT_PATH.write_text(json.dumps({"action": action, "entry": entry}, indent=2) + "\n", encoding="utf-8")
    print(f"{action.capitalize()} Fuelio entry {entry['id']} at {entry['odometer']:,} km")


if __name__ == "__main__":
    main()
