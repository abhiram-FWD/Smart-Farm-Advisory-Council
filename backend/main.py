import logging
import math
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, List

from fastapi import FastAPI, HTTPException, Path, Query, Request, Response
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from agents.advisory_manager import generate_farm_advisory
from tools.weather_tool import get_weather_forecast
from memory.mongodb_memory import (
    ActiveFarmMismatchError,
    AccountAlreadyExistsError,
    DUMMY_PASSWORD_HASH,
    FarmAlreadyExistsError,
    InvalidFarmTokenError,
    create_user,
    create_farm,
    create_user_session,
    delete_user_session,
    get_farm_advisories,
    count_farm_advisories,
    count_farm_observations,
    get_farm_owner_id,
    get_farm_id_for_token,
    get_farm_observations,
    get_farm_profile,
    update_farm_profile,
    get_user_farms,
    get_user_for_login,
    get_user_for_session,
    verify_password,
    initialize_memory,
)


logger = logging.getLogger(__name__)
COOKIE_NAME = "agrivision_farm_access"
COOKIE_MAX_AGE = 60 * 60 * 24 * 365
AUTH_COOKIE_NAME = "agrivision_account_session"
AUTH_COOKIE_MAX_AGE = 60 * 60 * 24 * 7
APP_ENV = os.getenv("APP_ENV", "development").lower()
IS_PRODUCTION = APP_ENV == "production" or os.getenv("RENDER", "").lower() == "true"
COOKIE_SECURE = IS_PRODUCTION or os.getenv("COOKIE_SECURE", "false").lower() == "true"

_configured_origins = os.getenv("ALLOWED_ORIGINS")
if IS_PRODUCTION and not _configured_origins:
    raise RuntimeError("ALLOWED_ORIGINS must be configured in production.")
ALLOWED_ORIGINS = {
    origin.strip().rstrip("/")
    for origin in (_configured_origins or "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if origin.strip()
}


def log_failure(event: str, error: Exception) -> None:
    """Log a stable event and exception type without exception contents."""
    logger.error("%s (exception_type=%s)", event, type(error).__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize MongoDB indexes without preventing API startup."""

    try:
        initialize_memory()
    except Exception as error:
        log_failure(
            "MongoDB index initialization failed; API startup will continue.",
            error,
        )
    yield


app = FastAPI(
    title="Smart Farm Advisory Council",
    description=(
        "AI-powered multi-agent agricultural "
        "advisory system using Semantic Kernel and RAG"
    ),
    version="1.1.0",
    lifespan=lifespan,
)


@app.exception_handler(RequestValidationError)
async def handle_request_validation_error(request: Request, exc: RequestValidationError):
    """Keep invalid non-finite numbers JSON-safe in normal 422 details."""
    for error in exc.errors():
        value = error.get("input")
        if isinstance(value, float) and not math.isfinite(value):
            if math.isnan(value):
                error["input"] = "NaN"
            elif value > 0:
                error["input"] = "Infinity"
            else:
                error["input"] = "-Infinity"
    return await request_validation_exception_handler(request, exc)

app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(ALLOWED_ORIGINS),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["Content-Type", "X-AgriVision-Request"],
)


MAX_SYMPTOMS = 10
MAX_SYMPTOM_LENGTH = 200


class FarmRequest(BaseModel):

    farm_id: str | None = Field(default=None, min_length=1, max_length=64)
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    soil_moisture: float = Field(ge=0, le=100, allow_inf_nan=False)
    soil_ph: float = Field(ge=0, le=14, allow_inf_nan=False)
    nitrogen: float = Field(ge=0, allow_inf_nan=False)
    phosphorus: float = Field(ge=0, allow_inf_nan=False)
    potassium: float = Field(ge=0, allow_inf_nan=False)
    crop_name: str = Field(min_length=1, max_length=100)
    growth_stage: str = Field(min_length=1, max_length=60)
    soil_type: str = Field(default="", max_length=100)
    symptoms: List[Annotated[str, Field(min_length=1, max_length=MAX_SYMPTOM_LENGTH)]] = Field(
        default_factory=list,
        max_length=MAX_SYMPTOMS,
    )

    @field_validator("crop_name", "growth_stage", "soil_type", mode="before")
    @classmethod
    def trim_text_edges(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("symptoms", mode="before")
    @classmethod
    def trim_symptom_edges(cls, value):
        if isinstance(value, list):
            return [item.strip() if isinstance(item, str) else item for item in value]
        return value


class FarmRegistration(BaseModel):
    farm_id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$",
    )


class FarmProfile(BaseModel):
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    crop_name: str = Field(default="", max_length=100)
    crop_variety: str = Field(default="", max_length=100)
    growth_stage: str = Field(default="", max_length=100)
    growth_stage_source: str = Field(default="farmer_reported", pattern="^farmer_reported$")
    planting_date: str = Field(default="", max_length=10)
    area: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    area_unit: str = Field(default="", max_length=20)
    soil_type: str = Field(default="", max_length=100)
    irrigation_method: str = Field(default="", max_length=100)

    @field_validator("crop_name", "crop_variety", "growth_stage", "planting_date", "area_unit", "soil_type", "irrigation_method")
    @classmethod
    def trim_profile_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("planting_date")
    @classmethod
    def validate_planting_date(cls, value):
        if value:
            try:
                datetime.strptime(value, "%Y-%m-%d")
            except ValueError as error:
                raise ValueError("Use a valid planting date in YYYY-MM-DD format.") from error
        return value


class AccountCredentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=72)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value):
        if not isinstance(value, str):
            return value
        value = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("Enter a valid email address.")
        return value

    @field_validator("password")
    @classmethod
    def limit_password_bytes(cls, value):
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be at most 72 UTF-8 bytes.")
        return value


def require_allowed_origin(request: Request) -> None:
    """Reject cross-site state changes independently of CORS behavior."""

    origin = request.headers.get("origin", "").rstrip("/")
    request_marker = request.headers.get("x-agrivision-request")
    if origin not in ALLOWED_ORIGINS or request_marker != "same-origin":
        raise HTTPException(
            status_code=403,
            detail="Request origin was not allowed.",
        )


def _current_user(request: Request) -> dict | None:
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if not token:
        return None
    try:
        user = get_user_for_session(token)
    except Exception as error:
        log_failure("Account session verification failed.", error)
        raise HTTPException(status_code=503, detail="Account service is temporarily unavailable.")
    if not user:
        raise HTTPException(status_code=401, detail="Account session is invalid or expired.")
    return user


def _set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        max_age=AUTH_COOKIE_MAX_AGE,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path="/api",
    )


def _public_user(user: dict) -> dict[str, str]:
    return {"user_id": user["user_id"], "email": user["email"]}


def require_farm_access(farm_id: str, request: Request) -> None:
    account_token = request.cookies.get(AUTH_COOKIE_NAME)
    if account_token:
        user = _current_user(request)
        try:
            owner_id = get_farm_owner_id(farm_id)
        except Exception as error:
            log_failure("Farm ownership verification failed.", error)
            raise HTTPException(status_code=503, detail="Farm access is temporarily unavailable.")
        if owner_id != user["user_id"]:
            raise HTTPException(status_code=404, detail="Farm was not found for this account.")
        return

    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Farm access is required.")

    try:
        token_farm_id = get_farm_id_for_token(token)
    except Exception as error:
        log_failure("Farm credential verification failed.", error)
        raise HTTPException(status_code=503, detail="Farm access is temporarily unavailable.")

    if not token_farm_id:
        raise HTTPException(status_code=401, detail="Farm access is invalid or expired.")
    if token_farm_id != farm_id:
        # Use the same response for another farm and an unknown farm ID.
        raise HTTPException(status_code=404, detail="Farm was not found for this access.")


def serialize_records(records):
    serialized = []
    for record in records:
        item = dict(record)
        created_at = item.get("created_at")
        if isinstance(created_at, datetime):
            item["created_at"] = created_at.isoformat()
        serialized.append(item)
    return serialized


@app.get("/")
def home():
    return {
        "message": "Welcome to Smart Farm Advisory Council API",
        "status": "running",
        "version": "1.1.0",
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "application": "Smart Farm Advisory Council",
    }


@app.post("/api/auth/register", status_code=201)
def register_account(credentials: AccountCredentials, request: Request, response: Response):
    require_allowed_origin(request)
    try:
        user = create_user(credentials.email, credentials.password)
        session_token = create_user_session(user["user_id"])
    except AccountAlreadyExistsError:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    except Exception as error:
        log_failure("Account registration failed.", error)
        raise HTTPException(status_code=503, detail="Account registration is temporarily unavailable.")
    _set_auth_cookie(response, session_token)
    return {"user": _public_user(user)}


@app.post("/api/auth/login")
def login_account(credentials: AccountCredentials, request: Request, response: Response):
    require_allowed_origin(request)
    try:
        user = get_user_for_login(credentials.email)
        password_hash = user.get("password_hash", "") if user else DUMMY_PASSWORD_HASH
        valid_password = verify_password(credentials.password, password_hash)
        if not user or not valid_password:
            raise HTTPException(status_code=401, detail="Email or password is incorrect.")
        session_token = create_user_session(user["user_id"])
    except HTTPException:
        raise
    except Exception as error:
        log_failure("Account login failed.", error)
        raise HTTPException(status_code=503, detail="Account service is temporarily unavailable.")
    _set_auth_cookie(response, session_token)
    return {"user": _public_user(user)}


@app.post("/api/auth/logout")
def logout_account(request: Request, response: Response):
    require_allowed_origin(request)
    try:
        delete_user_session(request.cookies.get(AUTH_COOKIE_NAME))
    except Exception as error:
        log_failure("Account logout failed.", error)
        raise HTTPException(status_code=503, detail="Could not end the account session.")
    response.delete_cookie(AUTH_COOKIE_NAME, path="/api", secure=COOKIE_SECURE, httponly=True, samesite="lax")
    response.delete_cookie(COOKIE_NAME, path="/api", secure=COOKIE_SECURE, httponly=True, samesite="lax")
    return {"logged_out": True}


@app.get("/api/auth/me")
def current_account(request: Request):
    user = _current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication is required.")
    return {"user": _public_user(user)}


@app.post("/api/farms")
def register_farm(
    registration: FarmRegistration,
    request: Request,
    response: Response,
):
    require_allowed_origin(request)
    if request.cookies.get(AUTH_COOKIE_NAME):
        user = _current_user(request)
        try:
            create_farm(registration.farm_id, user_id=user["user_id"])
        except FarmAlreadyExistsError:
            raise HTTPException(status_code=409, detail="This farm ID is already registered.")
        except Exception as error:
            log_failure("Account farm registration failed.", error)
            raise HTTPException(status_code=503, detail="Farm registration is temporarily unavailable.")
        return {"farm_id": registration.farm_id, "registered": True}

    current_token = request.cookies.get(COOKIE_NAME)
    try:
        token = create_farm(registration.farm_id, current_token=current_token)
    except ActiveFarmMismatchError:
        raise HTTPException(
            status_code=409,
            detail=(
                "This browser already has access to a different farm. "
                "Farm credentials were not changed. Return to that farm to continue."
            ),
        )
    except InvalidFarmTokenError:
        raise HTTPException(
            status_code=401,
            detail=(
                "The saved farm credential is invalid. Farm access was not changed."
            ),
        )
    except FarmAlreadyExistsError:
        raise HTTPException(
            status_code=409,
            detail=(
                "This farm ID is already registered and cannot be claimed without "
                "its existing credential. Choose a new farm ID."
            ),
        )
    except Exception as error:
        log_failure("Farm registration failed.", error)
        raise HTTPException(status_code=503, detail="Farm registration is temporarily unavailable.")

    if token:
        response.set_cookie(
            key=COOKIE_NAME,
            value=token,
            max_age=COOKIE_MAX_AGE,
            httponly=True,
            secure=COOKIE_SECURE,
            samesite="lax",
            path="/api",
        )

    return {"farm_id": registration.farm_id, "registered": True}


@app.get("/api/farms")
def list_farms(request: Request):
    account_token = request.cookies.get(AUTH_COOKIE_NAME)
    if account_token:
        user = _current_user(request)
        try:
            farms = get_user_farms(user["user_id"])
        except Exception as error:
            log_failure("Account farm list retrieval failed.", error)
            raise HTTPException(status_code=503, detail="Farm list is temporarily unavailable.")
        return {"items": serialize_records(farms)}
    farm_id = get_farm_id_for_token(request.cookies.get(COOKIE_NAME))
    if not farm_id:
        raise HTTPException(status_code=401, detail="Farm access is required.")
    return {"items": [{"farm_id": farm_id}]}


@app.post("/api/farms/session/exit")
def exit_farm_session(request: Request, response: Response):
    """Expire this browser's farm access cookie without changing farm records."""

    require_allowed_origin(request)
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/api",
        secure=COOKIE_SECURE,
        httponly=True,
        samesite="lax",
    )
    return {"session_ended": True}


@app.get("/api/farms/{farm_id}/observations")
def farm_observations(
    request: Request,
    farm_id: str = Path(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$",
    ),
    limit: int = Query(default=20, ge=1, le=100),
    skip: int = Query(default=0, ge=0, le=10000000),
):
    require_farm_access(farm_id, request)
    try:
        items = get_farm_observations(farm_id, limit, skip)
        total = count_farm_observations(farm_id)
    except Exception as error:
        log_failure("Farm observation history retrieval failed.", error)
        raise HTTPException(status_code=503, detail="Farm history is temporarily unavailable.")
    return {"farm_id": farm_id, "items": serialize_records(items), "limit": limit, "skip": skip, "total": total}


@app.get("/api/farms/{farm_id}/profile")
def read_farm_profile(request: Request, farm_id: str = Path(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")):
    require_farm_access(farm_id, request)
    try:
        profile = get_farm_profile(farm_id)
    except Exception as error:
        log_failure("Farm profile retrieval failed.", error)
        raise HTTPException(status_code=503, detail="Farm profile is temporarily unavailable.")
    return {"farm_id": farm_id, **profile}


@app.put("/api/farms/{farm_id}/profile")
def save_farm_profile(profile: FarmProfile, request: Request, farm_id: str = Path(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")):
    require_allowed_origin(request)
    require_farm_access(farm_id, request)
    try:
        saved = update_farm_profile(farm_id, profile.model_dump())
    except Exception as error:
        log_failure("Farm profile update failed.", error)
        raise HTTPException(status_code=503, detail="Farm profile could not be saved.")
    return {"farm_id": farm_id, **saved}


@app.get("/api/farms/{farm_id}/weather")
def farm_weather(
    request: Request,
    farm_id: str = Path(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"),
    latitude: float | None = Query(default=None, ge=-90, le=90),
    longitude: float | None = Query(default=None, ge=-180, le=180),
):
    require_farm_access(farm_id, request)
    try:
        profile = get_farm_profile(farm_id)
        latitude, longitude = profile.get("latitude"), profile.get("longitude")
        if latitude is None or longitude is None:
            raise HTTPException(status_code=422, detail="Add farm coordinates to view its weather forecast.")
        forecast = get_weather_forecast(latitude, longitude)
        if forecast.get("error"):
            raise HTTPException(status_code=503, detail="Weather forecast is temporarily unavailable.")
        return forecast
    except HTTPException:
        raise
    except Exception as error:
        log_failure("Farm weather retrieval failed.", error)
        raise HTTPException(status_code=503, detail="Weather forecast is temporarily unavailable.")


@app.get("/api/farms/{farm_id}/advisories")
def farm_advisories(
    request: Request,
    farm_id: str = Path(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$",
    ),
    limit: int = Query(default=20, ge=1, le=100),
    skip: int = Query(default=0, ge=0, le=10000000),
):
    require_farm_access(farm_id, request)
    try:
        items = get_farm_advisories(farm_id, limit, skip)
        total = count_farm_advisories(farm_id)
    except Exception as error:
        log_failure("Farm advisory history retrieval failed.", error)
        raise HTTPException(status_code=503, detail="Farm history is temporarily unavailable.")
    return {"farm_id": farm_id, "items": serialize_records(items), "limit": limit, "skip": skip, "total": total}


@app.post("/api/advisory")
def generate_advisory(request: FarmRequest, http_request: Request):
    require_allowed_origin(http_request)
    if not request.farm_id:
        raise HTTPException(
            status_code=422,
            detail="Register a farm before submitting an assessment.",
        )
    require_farm_access(request.farm_id, http_request)

    try:
        result = generate_farm_advisory(
            latitude=request.latitude,
            longitude=request.longitude,
            soil_moisture=request.soil_moisture,
            soil_ph=request.soil_ph,
            nitrogen=request.nitrogen,
            phosphorus=request.phosphorus,
            potassium=request.potassium,
            crop_name=request.crop_name,
            growth_stage=request.growth_stage,
            soil_type=request.soil_type,
            symptoms=request.symptoms,
            farm_id=request.farm_id,
        )

        if result.get("status") not in {
            "completed",
            "partial",
            "completed_with_memory_warning",
        }:
            detail = result.get("error")
            safe_details = {
                "Farm data storage is temporarily unavailable.",
                "Farm advisory orchestration could not be completed.",
                "The AI advisory service could not complete the analysis.",
            }
            status_code = 503 if detail == "Farm data storage is temporarily unavailable." else 502
            raise HTTPException(
                status_code=status_code,
                detail=detail if isinstance(detail, str) and detail in safe_details
                else "Farm advisory generation failed.",
            )
        if result.get("status") == "completed_with_memory_warning":
            raise HTTPException(
                status_code=503,
                detail="Farm advisory could not be saved to farm history.",
            )
        return result
    except HTTPException:
        raise
    except Exception as error:
        log_failure("Advisory generation failed.", error)
        raise HTTPException(status_code=500, detail="Advisory generation failed.")
