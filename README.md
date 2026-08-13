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
    {"id": "76857989", "name": "RAIPUR - FEEDER WAREHOUSE", "city": "raipur", "lat": 21.2380912, "lon": 81.6336993}
  ],
  "localities": [
    {"store_id": "29581", "store_name": "Super Store - Delhi Jhilmil ES1", "city": "delhi", "lat": 28.674685, "lon": 77.30319}
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

## Data source

Results are fetched live from public third-party APIs. Availability and accuracy depend on those services.
