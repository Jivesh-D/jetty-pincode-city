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
     "lat": 21.2380912, "lon": 81.6336993, "is_active": false,
     "pos": "nagpur", "basis": "nearest", "dist_km": 294.5}
  ],
  "localities": [
    {"store_id": "29581", "store_name": "Super Store - Delhi Jhilmil ES1", "city": "delhi",
     "lat": 28.674685, "lon": 77.30319, "pos": "noida", "basis": "nearest", "dist_km": 13.6}
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
&mdash; `warehouse.csv` alone has 74 such coordinate groups, the largest
holding 102 warehouses at a single point in Hyderabad.

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
`is_active` column; of its 697 warehouses just 56 are flagged `1`. Those are
the ones actually shipping stock, so they alone create places, draw
boundaries and size areas. The other 641 are dormant: they still appear in
the mapping, attached to whichever place now covers them, but they never
influence the definition. On the map they are drawn as hollow dots.

- A **site** is one unique active-warehouse coordinate (49 of them); a
  **place** is every site sharing a `dc_blinkit_internal_city` (32 of them).
  Bengaluru's three feeders are one place; Delhi NCR's six warehouse cities
  stay six places, matching Blinkit's own `pos_city` vocabulary. The 320
  cities with no active warehouse do not become places &mdash; nothing ships
  from them.
- Each darkstore (and each dormant warehouse) is assigned to the place of its
  own `dc_blinkit_internal_city` when that city has an active warehouse
  &mdash; that label is Blinkit's own operational grouping &mdash; **unless**
  another place is more than 25 km closer (`LABEL_OVERRIDE_KM`), which
  indicates a mislabel. Everything else attaches to the nearest place by
  haversine distance.
- The map draws each place as a single tinted **supply area**, starting from
  the convex hull of its active warehouse sites and every darkstore assigned to
  it, expanded by a 3 km margin so points sit inside the shape rather than on
  its edge. One place is one shape in one colour &mdash; 32 places, 32
  polygons, 738 vertices in total. Dormant warehouses are deliberately left out
  of the hull: they are assigned to a place but supply nothing from it, and one
  shuttered site 350 km away would stretch the whole area to reach it.
- **Areas never overlap.** Hulls are convex, so two can intersect where
  Blinkit's city label sends a darkstore across a border &mdash; most visibly
  in Delhi NCR. Rather than layer the fills, the hulls are resolved into a
  partition: the map is rasterised on a 1.5 km grid and any cell claimed by
  more than one hull goes to the place whose own served points lie nearest.
  Every shared border is then simplified **once** and reused by both sides, so
  the two neighbours draw the identical line and cannot drift apart. Verified
  exhaustively on a 2 km lattice: of 328,768 sample points inside shaded
  ground, **0 fell inside more than one place**.
- Because a darkstore is at zero distance from itself, that rule cannot pull
  ground out from under the store that put it there: all 56 active warehouses
  and 2,438 of 2,440 darkstores sit inside their own place's area. The two
  exceptions are Delhi NCR stores belonging to different places that sit within
  one grid cell of each other &mdash; at any finite resolution one of them has
  to lose the cell.
- Colours come from the API as `color_index`, assigned by greedy graph
  colouring over hulls that touch or come within 25 km, so no two neighbouring
  places share a tint. Five colours suffice for all 32 places.
- Clicking an area shows its stats and fans out supply links to every member
  darkstore, each starting at the warehouse site that actually covers it.

**Proportionality and its exceptions.** Every place reports `area_km2`,
`km2_per_warehouse` and an `area_balance` flag comparing it to the national
median. Most places come out `proportional`; the `concentrated` ones are
metros such as Noida, Gurgaon and Mumbai where warehouses are packed into a
small dense catchment, and the `stretched` ones are single feeders whose
darkstores are scattered across most of a state. Reach is set by geography and
by where the nearest other warehouse sits, so the ratio is driven mainly by
density &mdash; the flag is what makes those exceptions visible rather than
hidden.

**Accuracy.** Checked against Blinkit's own `city` &rarr; `pos_city` pairs in
`place_of_supply.csv`: of the 71 cities whose true place of supply is one of
the 32 active places, the inference agrees on 70 (99%). The one miss is
Rohtak, which Blinkit routes to Kundli although it sits ~16 km closer to
Farukhnagar.

`GET /api/place-of-supply/mapping.csv` downloads the full assignment: one row
per warehouse and darkstore with `is_active`, `place_of_supply`,
`assignment_basis` (`site`, `label`, `label+nearest`, `nearest`,
`label-overridden`), `distance_km` and the place's warehouse, darkstore and
area statistics.

## Data source

Results are fetched live from public third-party APIs. Availability and accuracy depend on those services.
