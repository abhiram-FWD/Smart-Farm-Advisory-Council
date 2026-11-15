
import os
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4
import secrets
import bcrypt

from dotenv import load_dotenv
from pymongo import MongoClient, DESCENDING
from pymongo.errors import DuplicateKeyError


load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME")
FARM_TOKEN_PEPPER = os.getenv("FARM_TOKEN_PEPPER")

if not MONGODB_URI or not MONGODB_DB_NAME or not FARM_TOKEN_PEPPER:
    raise RuntimeError("MongoDB configuration is missing.")

if MONGODB_DB_NAME != "smart_farm_db":
    raise RuntimeError(
        "MongoDB must be configured to use smart_farm_db."
    )

if len(FARM_TOKEN_PEPPER.encode("utf-8")) < 32:
    raise RuntimeError("FARM_TOKEN_PEPPER must contain at least 32 bytes.")


client = MongoClient(
    MONGODB_URI,
    serverSelectionTimeoutMS=10000
)

database = client[MONGODB_DB_NAME]

farms_collection = database["farms"]
observations_collection = database["farm_observations"]
advisories_collection = database["advisories"]
users_collection = database["users"]
DUMMY_PASSWORD_HASH = bcrypt.hashpw(
    b"constant-time account lookup check",
    bcrypt.gensalt(rounds=12),
).decode("ascii")


class FarmAlreadyExistsError(Exception):
    """Raised when an existing farm cannot be claimed without its token."""


class ActiveFarmMismatchError(Exception):
    """Raised when a browser tries to replace its active farm credential."""


class InvalidFarmTokenError(Exception):
    """Raised when the supplied token is not a registered farm credential."""


class AccountAlreadyExistsError(Exception):
    """Raised when an email address is already registered."""


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False


def create_user(email: str, password: str) -> dict[str, str]:
    user_id = str(uuid4())
    try:
        users_collection.insert_one({
            "user_id": user_id,
            "email": email,
            "password_hash": hash_password(password),
            "created_at": datetime.now(timezone.utc),
        })
    except DuplicateKeyError as error:
        raise AccountAlreadyExistsError from error
    return {"user_id": user_id, "email": email}


def get_user_for_login(email: str) -> dict[str, Any] | None:
    return users_collection.find_one(
        {"email": email},
        {"_id": 0, "user_id": 1, "email": 1, "password_hash": 1},
    )


def create_user_session(user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    users_collection.update_one(
        {"user_id": user_id},
        {"$set": {"session_token_hash": _token_hash(token), "session_expires_at": now + timedelta(days=7)}},
    )
    return token


def get_user_for_session(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    now = datetime.now(timezone.utc)
    user = users_collection.find_one(
        {"session_token_hash": _token_hash(token), "session_expires_at": {"$gt": now}},
        {"_id": 0, "user_id": 1, "email": 1},
    )
    if user and user.get("user_id"):
        return {"user_id": user["user_id"], "email": user.get("email", "")}
    return None


def delete_user_session(token: str | None) -> None:
    if token:
        users_collection.update_one(
            {"session_token_hash": _token_hash(token)},
            {"$unset": {"session_token_hash": "", "session_expires_at": ""}},
        )


def get_farm_owner_id(farm_id: str) -> str | None:
    farm = farms_collection.find_one({"farm_id": farm_id}, {"user_id": 1, "_id": 0})
    return farm.get("user_id") if farm else None


def get_user_farms(user_id: str) -> list[dict[str, Any]]:
    return list(farms_collection.find(
        {"user_id": user_id},
        {"_id": 0, "farm_id": 1, "profile": 1, "created_at": 1, "updated_at": 1},
    ).sort("created_at", 1))


def get_farm_profile(farm_id: str) -> dict[str, Any]:
    farm = farms_collection.find_one({"farm_id": farm_id}, {"_id": 0, "profile": 1})
    return farm.get("profile", {}) if farm else {}


def update_farm_profile(farm_id: str, profile: dict[str, Any]) -> dict[str, Any]:
    farms_collection.update_one(
        {"farm_id": farm_id},
        {"$set": {"profile": profile, "updated_at": datetime.now(timezone.utc)}},
    )
    return profile


def _token_hash(token: str) -> str:
    return hmac.new(
        FARM_TOKEN_PEPPER.encode("utf-8"),
        token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def create_farm(farm_id: str, current_token: str | None = None, user_id: str | None = None) -> str | None:
    """Create a farm and return a one-time token, or validate its active token."""

    if not farm_id or not farm_id.strip():
        raise ValueError("A valid farm_id is required.")

    if user_id:
        if farms_collection.find_one({"farm_id": farm_id}, {"_id": 1}):
            raise FarmAlreadyExistsError
        if observations_collection.find_one({"farm_id": farm_id}, {"_id": 1}):
            raise FarmAlreadyExistsError
        if advisories_collection.find_one({"farm_id": farm_id}, {"_id": 1}):
            raise FarmAlreadyExistsError
        now = datetime.now(timezone.utc)
        try:
            farms_collection.insert_one({
                "farm_id": farm_id,
                "user_id": user_id,
                "created_at": now,
                "updated_at": now,
            })
        except DuplicateKeyError as error:
            raise FarmAlreadyExistsError from error
        return None

    if current_token:
        active_farm = farms_collection.find_one(
            {"access_token_hash": _token_hash(current_token)},
            {"farm_id": 1, "_id": 0},
        )
        if not active_farm:
            raise InvalidFarmTokenError
        if active_farm.get("farm_id") != farm_id:
            raise ActiveFarmMismatchError
        return None

    # Never let a new credential adopt history written before the farm was
    # registered. Those records have no verifiable owner credential.
    if observations_collection.find_one({"farm_id": farm_id}, {"_id": 1}):
        raise FarmAlreadyExistsError
    if advisories_collection.find_one({"farm_id": farm_id}, {"_id": 1}):
        raise FarmAlreadyExistsError

    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    try:
        farms_collection.insert_one({
            "farm_id": farm_id,
            "access_token_hash": _token_hash(token),
            "created_at": now,
            "updated_at": now,
        })
    except DuplicateKeyError as error:
        raise FarmAlreadyExistsError from error

    return token


def get_farm_id_for_token(token: str | None) -> str | None:
    """Resolve a cookie token to its farm without returning token material."""

    if not token:
        return None
    record = farms_collection.find_one(
        {"access_token_hash": _token_hash(token)},
        {"farm_id": 1, "_id": 0},
    )
    return record.get("farm_id") if record else None


def initialize_memory():
    """Create indexes for efficient farm-history retrieval."""

    farms_collection.create_index("farm_id", unique=True)
    farms_collection.create_index("user_id")
    farms_collection.create_index(
        "access_token_hash", unique=True, sparse=True
    )
    users_collection.create_index("email", unique=True)
    users_collection.create_index("session_token_hash", unique=True, sparse=True)

    observations_collection.create_index(
        [("farm_id", 1), ("created_at", DESCENDING)]
    )

    advisories_collection.create_index(
        [("farm_id", 1), ("created_at", DESCENDING)]
    )


def save_farm_observation(
    farm_id: str,
    observation: dict[str, Any]
) -> str:
    """Save a new farm observation."""

    if not farm_id or not farm_id.strip():
        raise ValueError("A valid farm_id is required.")

    if not isinstance(observation, dict):
        raise ValueError("Observation must be a dictionary.")

    now = datetime.now(timezone.utc)

    farms_collection.update_one(
        {"farm_id": farm_id},
        {
            "$set": {"updated_at": now},
            "$setOnInsert": {
                "farm_id": farm_id,
                "created_at": now
            }
        },
        upsert=True
    )

    record = {
        "observation_id": str(uuid4()),
        "farm_id": farm_id,
        "observation": observation,
        "created_at": now
    }

    observations_collection.insert_one(record)

    # The advisory manager uses this ID to exclude the current record from
    # historical context, so return the same ID stored in the document.
    return record["observation_id"]


def get_farm_history(
    farm_id: str,
    limit: int = 10
) -> list[dict[str, Any]]:
    """Retrieve the latest observations for a farm."""

    if not farm_id or not farm_id.strip():
        raise ValueError("A valid farm_id is required.")

    if limit < 1:
        raise ValueError("Limit must be at least 1.")

    records = observations_collection.find(
        {"farm_id": farm_id},
        {"_id": 0}
    ).sort(
        "created_at", DESCENDING
    ).limit(limit)

    return list(records)


def save_advisory(
    farm_id: str,
    advisory: dict[str, Any]
) -> str:
    """Save a completed advisory."""

    if not farm_id or not farm_id.strip():
        raise ValueError("A valid farm_id is required.")

    if not isinstance(advisory, dict):
        raise ValueError("Advisory must be a dictionary.")

    record = {
        "advisory_id": str(uuid4()),
        "farm_id": farm_id,
        "advisory": advisory,
        "created_at": datetime.now(timezone.utc)
    }

    result = advisories_collection.insert_one(record)

    return str(result.inserted_id)


def get_previous_advisories(
    farm_id: str,
    limit: int = 5
) -> list[dict[str, Any]]:
    """Retrieve previous advisories for a farm."""

    if not farm_id or not farm_id.strip():
        raise ValueError("A valid farm_id is required.")

    if limit < 1:
        raise ValueError("Limit must be at least 1.")

    records = advisories_collection.find(
        {"farm_id": farm_id},
        {"_id": 0}
    ).sort(
        "created_at", DESCENDING
    ).limit(limit)

    return list(records)


def get_farm_observations(
    farm_id: str,
    limit: int = 20,
    skip: int = 0,
) -> list[dict[str, Any]]:
    """Return recent stored observations for a farm."""

    if not farm_id or not farm_id.strip():
        raise ValueError("A valid farm_id is required.")
    if limit < 1 or limit > 100 or skip < 0:
        raise ValueError("Limit must be between 1 and 100.")

    return list(observations_collection.find(
        {"farm_id": farm_id},
        {"_id": 0},
    ).sort("created_at", DESCENDING).skip(skip).limit(limit))


def get_farm_advisories(
    farm_id: str,
    limit: int = 20,
    skip: int = 0,
) -> list[dict[str, Any]]:
    """Return recent stored advisories for a farm."""

    if not farm_id or not farm_id.strip():
        raise ValueError("A valid farm_id is required.")
    if limit < 1 or limit > 100 or skip < 0:
        raise ValueError("Limit must be between 1 and 100.")

    return list(advisories_collection.find(
        {"farm_id": farm_id},
        {"_id": 0},
    ).sort("created_at", DESCENDING).skip(skip).limit(limit))


def count_farm_observations(farm_id: str) -> int:
    if not farm_id or not farm_id.strip():
        raise ValueError("A valid farm_id is required.")
    return observations_collection.count_documents({"farm_id": farm_id})


def count_farm_advisories(farm_id: str) -> int:
    if not farm_id or not farm_id.strip():
        raise ValueError("A valid farm_id is required.")
    return advisories_collection.count_documents({"farm_id": farm_id})


def close_connection():
    """Close the MongoDB client."""

    client.close()
