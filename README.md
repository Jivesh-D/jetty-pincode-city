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

### `GET /health`

Returns `{"status": "ok"}`.

## Limits

- Up to 200 pincodes per request
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

## Data source

Results are fetched live from the public postal API. Availability and accuracy depend on that third-party service.
