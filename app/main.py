import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.pincode_service import lookup_pincodes
from app.schemas import PincodeLookupRequest, PincodeLookupResponse, PincodeResult

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

logger = logging.getLogger(__name__)

app = FastAPI(title="Pincode City Lookup", version="1.0.0")


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


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
