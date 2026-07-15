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


class CityLookupRequest(BaseModel):
    coordinates: list[str] = Field(..., min_length=1)


class CityResult(BaseModel):
    input: str
    latitude: str
    longitude: str
    city: str | None = None
    locality: str | None = None
    postcode: str | None = None
    plus_code: str | None = None
    principal_subdivision: str | None = None
    status: str
    message: str | None = None


class CityLookupResponse(BaseModel):
    results: list[CityResult]


class NoonUaeHeadersResponse(BaseModel):
    columns: list[str]
