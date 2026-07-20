# Fuji Road Trip

Interactive public map for [fujiroadtrip.com](https://fujiroadtrip.com/): live road-trip route tracking, always-visible travel POIs, optional hike/fishing/surf overlays, Fuelio stats, and an analog photo gallery.

## What Is Here

- `index.html` renders the Leaflet map and floating UI.
- `route_past.geojson` stores the historic Google Timeline route.
- `route_live.geojson` stores the current GPX-derived car route.
- `route_meta.json` stores the latest GPS update metadata shown on the site.
- `car/gpx/` is the upload folder for new car GPX tracks.
- `car/archive/` stores processed car GPX tracks by month.
- `odo.json`, `fuelio_log.json`, and `fuelio_stats.json` power odometer, trip distance, fuel cost, and consumption stats.
- `poi.json` stores always-visible story points.
- `hikes.geojson`, `hikes_stats.json`, and `hike_stories.json` power the hiking overlay.
- `fishing-log.json` and `surf-log.json` power the fishing and surf overlay menus.
- `analog-gallery/gallery.json` powers the analog photo gallery.
- `favicon.png`, `favicon-32.png`, `favicon-192.png`, and `apple-touch-icon.png` are the browser/app icons.

## Car Route Updates

When a car GPX file is pushed to `car/gpx/`, GitHub Actions runs `geojson_merge.py`.

The script:

1. Reads GPX files in the repository root, `car/gpx/`, and `car/archive/`.
2. Keeps points that move at least 150 metres from the previous accepted point.
3. Bridges short, physically plausible GPS signal gaps and splits impossible jumps or long pauses.
4. Writes `route_live.geojson` and updates `route_meta.json`.
5. Moves processed files from `car/gpx/` into `car/archive/YYYY-MM/`.

If the GPX data does not include enough movement to draw a line, the script writes an empty GeoJSON feature collection and exits successfully.

## Local Testing

Install GPX dependencies when needed:

```sh
pip install gpxpy
```

Regenerate the live route:

```sh
python3 geojson_merge.py
```

Regenerate the hike overlay:

```sh
python3 process_hikes.py
```

Serve the site locally so Chrome can load JSON files through `fetch()`:

```sh
python3 -m http.server 8001
```

Then open `http://127.0.0.1:8001/index.html`.

## Fuelio Sync

Fuelio is the source of truth for odometer and fuel stats. The site reads:

- `odo.json` for current odometer and trip distance
- `fuelio_log.json` for individual fill-up entries
- `fuelio_stats.json` for latest fill-up, litres, cost, and average consumption

MacroDroid can send a small JSON payload to GitHub after a Fuelio fill-up. GitHub Actions appends the entry, recalculates the stats, commits the result, and publishes the updated site.

Create a fine-grained GitHub token for this repository with **Contents: Read and write** permission. Store it only in MacroDroid.

MacroDroid HTTP request:

```text
POST https://api.github.com/repos/sibmel29/fuji-roadtrip/dispatches
```

Headers:

```text
Accept: application/vnd.github+json
Authorization: Bearer <your-github-token>
Content-Type: application/json
X-GitHub-Api-Version: 2022-11-28
```

Body:

```json
{
  "event_type": "fuelio_entry",
  "client_payload": {
    "date": "2026-07-19",
    "odometer": 151900,
    "liters": 72.4,
    "cost": 158.25,
    "station": "Roadhouse",
    "note": "Optional note"
  }
}
```

At minimum, send `odometer`. Add `date`, `liters`, `cost`, `station`, and `note` when available. The workflow can also be run manually from the Actions tab.

As a fallback, export CSV from Fuelio and upload it to `fuelio/exports/`; the **Process Fuelio** workflow will update the same generated files.

## Points Of Interest

Published entries in `poi.json` are always shown on the map. Draft POIs can stay in the file with `"published": false`.

Each POI can include:

- `title`
- `date`
- `coordinates` as `[longitude, latitude]`
- `marker`: `info`, `sun`, `star`, `camera`, `camp`, `food`, `forest`, `mountain`, `fish`, or `surf`
- `summary`
- `body`
- `images`
- `tags`
- `published`

Use the GitHub issue forms from a phone instead of editing JSON manually:

- **Add POI** creates a new story marker.
- **Update POI** edits an existing POI by id.

The POI forms accept coordinates or a Google Maps link. Uploaded/linked images are downloaded, resized to a maximum width of 1600px, stripped of metadata, compressed to JPG, and saved under `poi-media/<poi-id>/`.

## Hikes

Use the **Add hike** issue form. Add the hike details and media in the form. Because GitHub issue forms do not reliably accept GPX attachments, GPX files can also be uploaded to `hikes/gpx/`.

The workflow stores hike text/photos in `hike_stories.json` and `hike-media/`, regenerates `hikes.geojson` and `hikes_stats.json`, commits the result, and closes the issue when possible.

The hiking layer is hidden by default behind the hiking menu. Toggling it shows hike routes, stats, and clickable hike markers.

## Fishing And Surf Logs

Fishing and surf entries are stored separately from normal POIs so the main map stays clean:

- `fishing-log.json` and `fishing-media/`
- `surf-log.json` and `surf-media/`

Use the **Add fishing log** and **Add surf spot** issue forms. Both forms accept a Google Maps link or coordinates, story text, tags, and optional images.

Fishing entries can include several species in one session. The fishing menu shows aggregate species totals, and the map markers open catch details with species, size, count, timestamp, notes, and photos.

Surf is a fixed spot log rather than a session-by-session log. Adding the same surf spot again updates that spot instead of creating duplicate markers.

## Analog Photo Gallery

The camera button below the ODO tile opens the full-screen analog photo gallery. The manifest lives at `analog-gallery/gallery.json`.

Use the **Add analog photos** issue form from a phone. The workflow downloads originals temporarily and commits optimized copies only:

```text
analog-gallery/thumbs/issue-<number>-<photo>.jpg
analog-gallery/web/issue-<number>-<photo>.jpg
```

Thumbnails are capped at 600px. Full viewing copies are capped at 2000px. Large phone originals are not stored in the repo.

## Reference Data

`fish_species_nsw.json` is a small reference list derived from the NSW DPI fish species index. It stores species names and freshwater/saltwater category only, with the official source URL kept in the file for deeper lookup.
