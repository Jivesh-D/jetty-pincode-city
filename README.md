# Jetty Tools

Web tools for spreadsheet workflows:

- **Pincode Lookup** — batch lookup Indian pincodes for city (district) and state, backed by [api.postalpincode.in](https://api.postalpincode.in)
- **FKMin Sales Converter** — convert a wide-format `Sales` sheet from `.xlsx` into a normalized CSV with the required schema

Open [http://localhost:8000](http://localhost:8000) and use the tabs to switch between tools.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Open [http://localhost:8000](http://localhost:8000) for the UI.

### FKMin Sales Converter (browser)

1. Open the **FKMin Sales Converter** tab
2. Choose an `.xlsx` file with a `Sales` sheet
3. Click **Convert & download CSV**

The downloaded CSV columns are:

`order_date_time,city,product_id,analytic_business_unit,analytic_super_category,analytic_vertical,brand_csv,units,mrp`

## Deploy on Render

Set the **Start Command** to:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Or use the included [`render.yaml`](render.yaml) blueprint. A root [`main.py`](main.py) shim also supports Render’s default `uvicorn main:app` if you cannot change the start command.

## API

### `POST /api/pincodes/lookup`

**Request:**

```json
{
  "pincodes": ["781001", "781002"]
}
```

**Response:**

```json
{
  "results": [
    {
      "pincode": "781001",
      "city": "Kamrup",
      "state": "Assam",
      "status": "ok",
      "message": null
    }
  ]
}
```

- **city** — `District` from the upstream post office record
- **state** — `State` from the upstream post office record
- **status** — `ok`, `not_found`, `invalid`, or `error`

**Example:**

```bash
curl -X POST http://localhost:8000/api/pincodes/lookup \
  -H "Content-Type: application/json" \
  -d '{"pincodes": ["781001", "781002"]}'
```

### `POST /api/sales/convert`

Upload an `.xlsx` workbook and receive a CSV attachment. Only the **Sales** sheet is converted.

**Input layout (Sales sheet):**

- Row 1: dates (`dd/mm/yyyy` or Excel date values)
- Row 2: `FSN`, `Title`, `City`, then repeating `GMV` / `Units` pairs per date
- Row 3+: data rows

**Output mapping:**

| Output column | Source |
|---|---|
| `order_date_time` | Date from row 1 (`yyyy-mm-dd`) |
| `city` | `City` |
| `product_id` | `FSN` |
| `analytic_business_unit` | `Title` |
| `units` | `Units` (blank → `0`) |
| `mrp` | `GMV` (blank → `0`) |
| `analytic_super_category`, `analytic_vertical`, `brand_csv` | empty |

**Example:**

```bash
curl -X POST http://localhost:8000/api/sales/convert \
  -F "file=@sales.xlsx" \
  -o sales.csv
```

### `GET /api/place-of-supply/points`

Returns the Blinkit warehouse and locality coordinates that the
**PlaceOfSupply Blinkit** map tab plots, read from `warehouse.csv` and
`localities.csv` at the repo root.

```json
{
  "warehouses": [
    {"id": "76857989", "name": "RAIPUR - FEEDER WAREHOUSE", "city": "raipur",
     "lat": 21.2380912, "lon": 81.6336993, "is_active": true,
     "pos": "raipur", "basis": "site", "dist_km": 0.0}
  ],
  "localities": [
    {"store_id": "29581", "store_name": "Super Store - Delhi Jhilmil ES1", "city": "delhi",
     "lat": 28.674685, "lon": 77.30319, "pos": "noida", "basis": "city-majority", "dist_km": 17.69}
  ],
  "places": [
    {"id": "bengaluru", "name": "bengaluru", "lat": 12.957067, "lon": 77.784800,
     "site_count": 3, "active_warehouse_count": 3, "inactive_warehouse_count": 59,
     "warehouse_count": 62, "locality_count": 222, "median_km": 22.2, "max_km": 251.1,
     "remote_count": 18, "area_km2": 105708, "km2_per_warehouse": 35236,
     "area_per_warehouse_ratio": 0.67, "area_balance": "proportional",
     "areas": [[[12.9, 77.7], "..."]]}
  ]
}
```

Both files are parsed once per process and cached in memory, so edits to the
CSVs need a server restart. Rows whose latitude/longitude fail to parse, or
that fall outside India's bounding box, are skipped and logged rather than
failing the request.

### `GET /health`

Returns `{"status": "ok"}`.

## Limits

- Up to 5000 pincodes per request
- Up to 10 concurrent upstream calls per request

## Logging

With `uvicorn app.main:app --reload`, lookup activity is printed to the terminal:

- Each upstream URL and HTTP status
- API `Status` / `Message` from the postal service
- Full stack traces for connection failures
- Batch summary (`ok`, `not_found`, `invalid`, `error` counts)

The UI **Details** column shows the same error message returned in the API response.

## SSL note

`api.postalpincode.in` currently uses an **expired TLS certificate**. By default this app disables SSL verification for that host only so lookups work. When their certificate is fixed, run with:

```bash
UPSTREAM_SSL_VERIFY=1 uvicorn app.main:app --reload --port 8000
```

## GroundTruth (reverse geocoding)

The **GroundTruth** tab looks up city/locality/postcode/plus code for pasted
`latitude,longitude` pairs via BigDataCloud's server-side reverse-geocode API.
This endpoint requires a free API key (their `-client` endpoint is
CORS-enabled for browser calls only and rejects server-side traffic with a
400).

1. Get a free key at <https://www.bigdatacloud.com/>
2. Set it as an environment variable before starting the server:

```bash
BIGDATACLOUD_API_KEY=your-key-here uvicorn app.main:app --reload --port 8000
```

On Render, set `BIGDATACLOUD_API_KEY` under the service's **Environment**
tab (or via the `render.yaml` blueprint, which declares it as a required
manually-set variable).

## PlaceOfSupply Blinkit (map)

The **PlaceOfSupply Blinkit** tab plots every Blinkit feeder warehouse
(amber) and darkstore locality (green) from `warehouse.csv` and
`localities.csv` on a zoomable India map, using the latitude/longitude in
those files directly. Leaflet and Leaflet.markercluster are loaded from a CDN
&mdash; there is no build step.

Markers never draw on top of one another at any zoom level. Overlapping
points merge into a single ring whose colour is split by its warehouse /
locality composition, with the point count in the middle; zooming in breaks
the rings apart. Points that share the *exact* same coordinate can never be
separated by zoom, so clicking their ring fans them out on legs instead
&mdash; `warehouse.csv` alone has 75 such coordinate groups, the largest
holding 99 warehouses at a single point in Hyderabad.

Clicking a point shows `dc_blinkit_warehouse_id` and `warehouse` for a
warehouse, or `store_id`, `store_name` and `dc_blinkit_internal_city` for a
locality. The checkboxes above the map toggle each layer and report how many
points are currently plotted.

**Fullscreen** expands the map to fill the screen (`Esc` or the button exits).
The layer toggles and *Reset view* stay available while fullscreen. Entering
and leaving both trigger `map.invalidateSize()`, without which Leaflet keeps
the old container size and renders a cropped tile grid.

To keep the no-overlap guarantee, cluster icon diameters (32&ndash;44px) are
held well below `maxClusterRadius` (70px) in `static/app.js`; raising the icon
sizes or lowering that radius will let neighbouring rings collide.

### Place-of-supply definition

Which warehouse caters which darkstore is not recorded anywhere, so the tab
infers a **place-of-supply** for every point (`app/place_of_supply.py`).

**Only active warehouses define places.** `warehouse.csv` carries an
`is_active` column; of its 697 warehouses 113 are flagged `1`. Those are
the ones actually shipping stock, so they alone create places, draw
boundaries and size areas. The other 584 are dormant: they still appear in
the mapping, attached to whichever place now covers them, but they never
influence the definition. On the map they are drawn as hollow dots.

- A **site** is one unique active-warehouse coordinate (106 of them); a
  **place** is every site sharing a `dc_blinkit_internal_city` (40 of them).
  Bengaluru's three feeders are one place. `PLACE_MERGES` pools named
  warehouse cities into one place: Delhi NCR's six warehouse cities &mdash;
  `noida`, `gurgaon`, `faridabad`, `farukhnagar`, `dasna` and `kundli`, which
  Blinkit's `pos_city` vocabulary keeps apart &mdash; are one `delhi ncr`
  place with eight sites. The 311 cities with no active warehouse do not
  become places &mdash; nothing ships from them.
- Many of the active sites are **Super Stores that are also darkstores**: 55
  of them appear again in `localities.csv` under their `Super Store ...` name,
  and the two files disagree on where they are by a median 4.5 km (max 13 km).
  `warehouse.csv` is taken as authoritative and the rows are left as two
  independent points, so in those cities a store both supplies and is supplied,
  from coordinates a few km apart. It widens those hulls slightly; it is data
  drift, not a geometry fault.
- **One city, one place.** A place of supply is a cluster of darkstores and
  warehouses, and a `dc_blinkit_internal_city` belongs to exactly one of them:
  many cities may share a place, but no city is ever split across two. A city
  that has an active warehouse is its own place, and every one of its
  darkstores and dormant warehouses goes there (`label`). Every other city is
  attached **as a whole** to the place that the majority of its points are
  nearest to by haversine distance (`city-nearest` when every point agrees,
  `city-majority` otherwise; ties break on the smallest mean distance). The
  module asserts the rule before returning and refuses to serve a mapping that
  violates it. Delhi, for instance, is ringed by the six NCR warehouse
  cities, and all 214 of its darkstores sit in `delhi ncr`.
- Points more than 200 km from their city's place (`OUTLIER_KM`) &mdash; either
  a genuinely far-flung city such as Jodhpur served from Jaipur, or a reused
  label such as a "bardoli" store 900 km from Bardoli &mdash; keep the city's
  place but are left out of its hull, so one distant point cannot stretch an
  area across half the country. Each such city is logged as a warning on
  startup; 124 points in 32 cities are affected today.
- The map draws each place as a single tinted **supply area**, starting from
  the convex hull of its active warehouse sites and every darkstore assigned to
  it, expanded by a 3 km margin so points sit inside the shape rather than on
  its edge. One place is one shape in one colour &mdash; 40 places, 41
  polygons. Dormant warehouses are deliberately left out
  of the hull: they are assigned to a place but supply nothing from it, and one
  shuttered site 350 km away would stretch the whole area to reach it.
- **Areas never overlap.** Hulls are convex, so two can intersect where a
  city's catchment reaches across a neighbour's. Rather than layer the fills, the hulls are resolved into a
  partition: the map is rasterised on a 1.5 km grid and any cell claimed by
  more than one hull goes to the place whose own served points lie nearest.
  Every shared border is then simplified **once** and reused by both sides, so
  the two neighbours draw the identical line and cannot drift apart. Verified
  so that no sample point inside shaded ground falls in more than one place.
- Because a darkstore is at zero distance from itself, that rule cannot pull
  ground out from under the store that put it there: every active warehouse
  and every darkstore within `OUTLIER_KM` of its place sits inside its own
  place's area.
- Rings under `_MIN_RING_KM2` (60 km&sup2;) are dropped as raster slivers, but
  **a place always keeps its largest ring**. A lone site with one nearby
  darkstore hulls to a ~28 km&sup2; disk, entirely under that threshold; without
  the exemption Gangtok (38 km&sup2;) and Udupi (45 km&sup2;) would report an
  area in their stats and yet draw no shape at all.
- Colours come from the API as `color_index`, assigned by greedy graph
  colouring over hulls that touch or come within 25 km, so no two neighbouring
  places share a tint. Three colours suffice for all 40 places.
- Clicking an area shows its stats and fans out supply links to every member
  darkstore, each starting at the warehouse site that actually covers it.

**Proportionality and its exceptions.** Every place reports `area_km2`,
`km2_per_warehouse` and an `area_balance` flag comparing it to the national
median. Of the 40 places 18 come out `proportional` &mdash; Delhi NCR among
them, its eight sites and 60,000 km&sup2; landing almost exactly on the
median; the 12 `concentrated` ones are Mumbai plus the single-store places
(Gangtok, Udupi, Srinagar) whose catchment is one town, and the 10 `stretched`
ones are single feeders whose darkstores are scattered across most of a
state. Reach is set by geography and by where the nearest other warehouse
sits, so the ratio is driven mainly by density &mdash; the flag is what makes
those exceptions visible rather than hidden.

**Accuracy.** `place_of_supply.csv` and the two `*_deepdive.csv` files are
downstream of this mapping, so they play no part in defining it; they are only
useful as a sanity check. Across the 139 `city` &rarr; `pos_city` pairs in
`place_of_supply.csv` the inference agrees on 138 (99%), counting the six NCR
`pos_city` values as `delhi ncr`. The one miss is a border town with a single
store &mdash; `kishangarh` (Blinkit says jaipur, distance says delhi ncr)
&mdash; where the nearest place differs from the one Blinkit chose.

`GET /api/place-of-supply/mapping.csv` downloads the full assignment: one row
per warehouse and darkstore with `is_active`, `place_of_supply`,
`assignment_basis` (`site`, `label`, `city-nearest`, `city-majority`),
`distance_km` and the place's warehouse, darkstore and
area statistics.

## Data source

Results are fetched live from public third-party APIs. Availability and accuracy depend on those services.
