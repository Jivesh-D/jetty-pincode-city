import logging
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from app.pincode_service import lookup_pincodes
from app.sales_converter import convert_sales_xlsx_to_csv
from app.schemas import PincodeLookupRequest, PincodeLookupResponse, PincodeResult

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


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
