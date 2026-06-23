import logging
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from app.noon_uae_converter import (
    convert_noon_uae_csv,
    parse_date_param,
    read_csv_headers,
)
from app.pincode_service import lookup_pincodes
from app.sales_converter import convert_sales_xlsx_to_csv
from app.schemas import (
    NoonUaeHeadersResponse,
    PincodeLookupRequest,
    PincodeLookupResponse,
    PincodeResult,
)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

logger = logging.getLogger(__name__)

app = FastAPI(title="Jetty Tools", version="1.1.0")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/pincodes/lookup", response_model=PincodeLookupResponse)
async def pincode_lookup(body: PincodeLookupRequest) -> PincodeLookupResponse:
    logger.info("POST /api/pincodes/lookup count=%d", len(body.pincodes))
    try:
        results = await lookup_pincodes(body.pincodes)
    except ValueError as exc:
        logger.warning("lookup rejected: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return PincodeLookupResponse(
        results=[
            PincodeResult(
                pincode=r.pincode,
                city=r.city,
                state=r.state,
                status=r.status,
                message=r.message,
            )
            for r in results
        ]
    )


@app.post("/api/sales/convert")
async def sales_convert(file: UploadFile = File(...)) -> Response:
    filename = file.filename or ""
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Upload must be an .xlsx file")

    logger.info("POST /api/sales/convert filename=%s", filename)
    content = await file.read()
    try:
        csv_text = convert_sales_xlsx_to_csv(content)
    except ValueError as exc:
        logger.warning("sales convert rejected: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    row_count = max(0, csv_text.count("\n") - 1)
    logger.info("sales convert ok rows=%d", row_count)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="sales.csv"'},
    )


@app.post("/api/noon-uae/headers", response_model=NoonUaeHeadersResponse)
async def noon_uae_headers(file: UploadFile = File(...)) -> NoonUaeHeadersResponse:
    filename = file.filename or ""
    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Upload must be a .csv file")

    logger.info("POST /api/noon-uae/headers filename=%s", filename)
    content = await file.read()
    try:
        columns = read_csv_headers(content)
    except ValueError as exc:
        logger.warning("noon-uae headers rejected: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return NoonUaeHeadersResponse(columns=columns)


@app.post("/api/noon-uae/convert")
async def noon_uae_convert(
    file: UploadFile = File(...),
    platform_type_col: str = Form(...),
    qty_sold_col: str = Form(...),
    revenue_col: str = Form(...),
    item_id_col: str = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
) -> Response:
    filename = file.filename or ""
    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Upload must be a .csv file")

    logger.info("POST /api/noon-uae/convert filename=%s", filename)
    content = await file.read()
    try:
        parsed_start = parse_date_param(start_date, field_name="start_date")
        parsed_end = parse_date_param(end_date, field_name="end_date")
        csv_text = convert_noon_uae_csv(
            content,
            platform_type_col=platform_type_col,
            qty_sold_col=qty_sold_col,
            revenue_col=revenue_col,
            item_id_col=item_id_col,
            start_date=parsed_start,
            end_date=parsed_end,
        )
    except ValueError as exc:
        logger.warning("noon-uae convert rejected: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    row_count = max(0, csv_text.count("\n") - 1)
    logger.info("noon-uae convert ok rows=%d", row_count)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="noon-uae-sales.csv"'},
    )


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "index.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
