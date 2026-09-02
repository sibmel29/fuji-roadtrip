# Fuji Road Trip

Interactive public map for [fujiroadtrip.com](https://fujiroadtrip.com/): live road-trip route tracking, always-visible travel POIs, optional hike/fishing/surf/4WD overlays, Fuelio stats, and an analog photo gallery.

## What Is Here

- `index.html` renders the Leaflet map and floating UI.
- `route_past.geojson` stores the historic Google Timeline route.
- `route_live.geojson` stores the current GPX-derived car route.
- `route_expected.geojson` stores the manually planned future route chapters.
- `expected_stops.geojson` stores clickable planned stop markers for the Expected Route overlay.
- `route_meta.json` stores the latest GPS update metadata shown on the site.
- `car/gpx/` is the upload folder for new car GPX tracks.
- `car/archive/` stores processed car GPX tracks by month.
- `odo.json`, `fuelio_log.json`, and `fuelio_stats.json` power odometer, trip distance, fuel cost, and consumption stats.
- `poi.json` stores always-visible story points.
- `hikes.geojson`, `hikes_stats.json`, and `hike_stories.json` power the hiking overlay.
- `fishing-log.json` and `surf-log.json` power the fishing and surf overlay menus.
- `fourwd_segments.json`, `fourwd-tracks.geojson`, and `fourwd_stats.json` power the 4WD tracks overlay.
- `van-nights.geojson` powers the hidden van-night sleep spot overlay.
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

Regenerate the 4WD overlay:

```sh
python3 process_fourwd.py
```

Serve the site locally so Chrome can load JSON files through `fetch()`:

```sh
python3 -m http.server 8001
```

Then open `http://127.0.0.1:8001/index.html`.

## Van Night Extraction Experiment

`scripts/extract_van_nights.py` compares three filters for finding likely nights spent in the van from Google Timeline / Location History JSON.

Run it locally with:

```sh
python3 scripts/extract_van_nights.py Timeline.json
```

By default it only checks local dates from `2025-11-01` through the day you run it. Override that with `--start-date YYYY-MM-DD` or `--end-date YYYY-MM-DD` if needed.

It writes separate outputs to `van-nights-output/`:

- `van_nights_strict.json`, `_nightly.geojson`, and `_spots.geojson`
- `van_nights_balanced.json`, `_nightly.geojson`, and `_spots.geojson`
- `van_nights_loose.json`, `_nightly.geojson`, and `_spots.geojson`
- `van_nights_comparison.csv`
- `van_nights_comparison.json`

The profiles are:

- `strict`: tighter radius, longer stop, clear 8-10pm overlap, grouped only within 250m.
- `balanced`: default first pass for “settled by around 8pm, not moving for 2+ hours”, grouped within 500m.
- `loose`: catches sparse Timeline data and phone-off nights, grouped within 1km.

The marker coordinate is now a real observed GPS point, not an averaged midpoint. The script prefers the latest observed point around the settle window and records morning confirmation when the first next-morning point is nearby. Compare `van_nights_comparison.csv` first, inspect `_nightly.geojson` for one marker per detected night, then inspect `_spots.geojson` for tightly grouped unique spots.

## Hidden Van Night Layer

The site includes a casual-secret van-night layer for sleep spots in `van-nights.geojson`.

Unlock flow:

1. Click the Fuji van drawing 7 times.
2. Enter `donttellthecouncil`.
3. Use the moon/van icon that appears in the right-side layer menu.

This is an easter egg, not real security. Because the GeoJSON is shipped with the static site, technical visitors could still find it in the public files.

Manual entries can be added later through GitHub's API using the `van_night_entry` repository dispatch event.

## Expected Route

The **Expected Route** overlay is a manually curated future itinerary. It is intentionally separate from the real GPS data:

- Actual travelled route: `route_past.geojson` and `route_live.geojson`
- Planned future route: `route_expected.geojson`
- Planned stop popups: `expected_stops.geojson`

The expected route is shown as dashed, semi-transparent chapter lines and is on by default.

## Fuelio Sync

Fuelio is the source of truth for odometer and fuel stats. The site reads:

- `odo.json` for current odometer and trip distance
- `fuelio_log.json` for individual fill-up entries
- `fuelio_stats.json` for latest fill-up, litres, cost, and average consumption stats

## Points Of Interest

Published entries in `poi.json` are always shown on the map. Draft POIs can stay in the file with `"published": false`.

## Hikes

Use the **Add hike** issue form. Add the hike details and media in the form.

## Fishing And Surf Logs

Fishing and surf entries are stored separately from normal POIs so the main map stays clean:

- `fishing-log.json` and `fishing-media/`
- `surf-log.json` and `surf-media/`

## 4WD Tracks

The 4WD layer highlights special off-road sections without changing the normal car route. Segment definitions live in `fourwd_segments.json`.

## Analog Photo Gallery

The camera button below the ODO tile opens the full-screen analog photo gallery. The manifest lives at `analog-gallery/gallery.json`.

## Reference Data

`fish_species_nsw.json` is a small reference list derived from the NSW DPI fish species index.
