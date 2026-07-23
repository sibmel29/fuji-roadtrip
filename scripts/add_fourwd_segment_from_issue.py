import json
import os
from pathlib import Path

import add_poi_from_issue
from add_poi_from_issue import (
    image_entries_for,
    images_from_entries,
    parse_paragraphs,
    parse_sections,
    parse_tags,
    published_from_sections,
    slugify,
    value_for,
)


SEGMENTS_FILE = Path(os.environ.get("FOURWD_SEGMENTS_FILE", "fourwd_segments.json"))
MEDIA_FOLDER = Path(os.environ.get("FOURWD_MEDIA_FOLDER", "fourwd-media"))
RESULT_FILE = Path(os.environ.get("RESULT_FILE", "fourwd_result.json"))


def first_value(sections, labels, default=""):
    for label in labels:
        value = value_for(sections, label)

        if value:
            return value

    return default


def number_value(value):
    value = str(value or "").strip()

    if not value:
        return ""

    try:
        number = float(value)
    except ValueError:
        return value

    return int(number) if number.is_integer() else number


def unique_id(base_id, issue_number, segments):
    source_issue = str(issue_number)

    for segment in segments:
        if str(segment.get("source_issue", "")) == source_issue:
            return segment.get("id", base_id), segment

    existing_ids = {segment.get("id") for segment in segments}

    if base_id not in existing_ids:
        return base_id, None

    issue_id = f"{base_id}-{issue_number}"
    if issue_id not in existing_ids:
        return issue_id, None

    index = 2
    while f"{issue_id}-{index}" in existing_ids:
        index += 1

    return f"{issue_id}-{index}", None


def segment_from_sections(sections, issue_number, issue_url, segments):
    title = value_for(sections, "4WD track title")

    if not title:
        raise ValueError("4WD track title is required")

    segment_id, existing = unique_id(slugify(title), issue_number, segments)
    original_media_folder = add_poi_from_issue.POI_MEDIA_FOLDER
    add_poi_from_issue.POI_MEDIA_FOLDER = MEDIA_FOLDER

    try:
        images = images_from_entries(image_entries_for(value_for(sections, "Image paths")), segment_id, title)
    finally:
        add_poi_from_issue.POI_MEDIA_FOLDER = original_media_folder

    source = {
        "type": "time_range",
        "start_time": value_for(sections, "Start timestamp"),
        "end_time": value_for(sections, "End timestamp"),
    }

    source_file = value_for(sections, "Source route file")
    feature_index = value_for(sections, "Source feature index")
    start_index = value_for(sections, "Source start point index")
    end_index = value_for(sections, "Source end point index")

    if source_file and feature_index and start_index and end_index:
        source = {
            "type": "feature_range",
            "file": source_file,
            "feature_index": int(feature_index),
            "start_index": int(start_index),
            "end_index": int(end_index),
        }

    segment = {
        "id": segment_id,
        "title": title,
        "date": value_for(sections, "Date"),
        "time_hint": value_for(sections, "Time hint"),
        "difficulty": value_for(sections, "Difficulty"),
        "rating": number_value(value_for(sections, "Rating")),
        "conditions": value_for(sections, "Conditions"),
        "summary": value_for(sections, "Short summary"),
        "body": parse_paragraphs(value_for(sections, "Story text")),
        "images": images or (existing.get("images", []) if existing else []),
        "tags": parse_tags(value_for(sections, "Tags")) or ["4wd"],
        "source": source,
        "published": published_from_sections(sections, existing),
        "source_issue": str(issue_number),
        "source_url": issue_url,
    }

    return segment, existing


def main():
    issue_body = os.environ.get("ISSUE_BODY", "")
    issue_number = os.environ.get("ISSUE_NUMBER", "")
    issue_url = os.environ.get("ISSUE_URL", "")

    if not issue_body or not issue_number:
        raise ValueError("ISSUE_BODY and ISSUE_NUMBER are required")

    sections = parse_sections(issue_body)
    segments = json.loads(SEGMENTS_FILE.read_text(encoding="utf-8")) if SEGMENTS_FILE.exists() else []
    segment, existing = segment_from_sections(sections, issue_number, issue_url, segments)

    if existing is not None:
        existing.clear()
        existing.update(segment)
        action = "updated"
    else:
        segments.insert(0, segment)
        action = "added"

    SEGMENTS_FILE.write_text(json.dumps(segments, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    RESULT_FILE.write_text(json.dumps({"id": segment["id"], "title": segment["title"], "action": action}), encoding="utf-8")
    print(f"{action.title()} 4WD segment {segment['id']}: {segment['title']}")


if __name__ == "__main__":
    main()
