# Pincode City Lookup

Batch lookup Indian pincodes for city (district) and state, backed by [api.postalpincode.in](https://api.postalpincode.in). Includes a spreadsheet-style UI for pasting pincodes from Google Sheets and copying results back.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Open [http://localhost:8000](http://localhost:8000) for the UI.

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
