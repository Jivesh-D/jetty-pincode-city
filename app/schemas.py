from pydantic import BaseModel, Field


class PincodeLookupRequest(BaseModel):
    pincodes: list[str] = Field(..., min_length=1)


class PincodeResult(BaseModel):
    pincode: str
    city: str | None = None
    state: str | None = None
    status: str
    message: str | None = None


class PincodeLookupResponse(BaseModel):
    results: list[PincodeResult]


class NoonUaeHeadersResponse(BaseModel):
    columns: list[str]
