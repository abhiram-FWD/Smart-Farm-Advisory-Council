from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pymongo.errors import DuplicateKeyError

import main
from memory import mongodb_memory


class Cursor(list):
    def sort(self, key, direction):
        return Cursor(sorted(self, key=lambda row: row.get(key), reverse=direction < 0))


class MemoryCollection:
    def __init__(self, unique=()):
        self.rows = []
        self.unique = unique

    def insert_one(self, row):
        for key in self.unique:
            if row.get(key) is not None and any(item.get(key) == row[key] for item in self.rows):
                raise DuplicateKeyError(f"duplicate {key}")
        self.rows.append(deepcopy(row))

    def _matches(self, row, query):
        for key, value in query.items():
            actual = row.get(key)
            if isinstance(value, dict) and "$gt" in value:
                if actual is None or actual <= value["$gt"]:
                    return False
            elif actual != value:
                return False
        return True

    def find_one(self, query, projection=None):
        row = next((item for item in self.rows if self._matches(item, query)), None)
        if row is None:
            return None
        row = deepcopy(row)
        if projection:
            included = [key for key, value in projection.items() if value and key != "_id"]
            excluded = [key for key, value in projection.items() if not value]
            if included:
                row = {key: row[key] for key in included if key in row}
            for key in excluded:
                row.pop(key, None)
        return row

    def find(self, query, projection=None):
        return Cursor([self.find_one({"user_id": row.get("user_id"), "farm_id": row.get("farm_id")}, projection) for row in self.rows if self._matches(row, query)])

    def update_one(self, query, update, upsert=False):
        row = next((item for item in self.rows if self._matches(item, query)), None)
        if row is None:
            return None
        row.update(deepcopy(update.get("$set", {})))
        for key in update.get("$unset", {}):
            row.pop(key, None)
        return None


@pytest.fixture
def auth_client(monkeypatch):
    users = MemoryCollection(unique=("email", "session_token_hash"))
    farms = MemoryCollection(unique=("farm_id", "access_token_hash"))
    history = MemoryCollection()
    advisories = MemoryCollection()
    monkeypatch.setattr(mongodb_memory, "users_collection", users)
    monkeypatch.setattr(mongodb_memory, "farms_collection", farms)
    monkeypatch.setattr(mongodb_memory, "observations_collection", history)
    monkeypatch.setattr(mongodb_memory, "advisories_collection", advisories)
    monkeypatch.setattr(main, "initialize_memory", lambda: None)
    with TestClient(main.app) as client:
        yield client, users, farms


def headers():
    return {"Origin": "http://localhost:5173", "X-AgriVision-Request": "same-origin"}


def register(client, email, password="correct horse battery staple"):
    return client.post("/api/auth/register", json={"email": email, "password": password}, headers=headers())


def test_registration_hashes_password_and_sets_http_only_session(auth_client):
    client, users, _ = auth_client
    response = register(client, "Farmer@Example.com")

    assert response.status_code == 201
    assert response.json()["user"]["email"] == "farmer@example.com"
    stored = users.rows[0]
    assert stored["password_hash"] != "correct horse battery staple"
    assert mongodb_memory.verify_password("correct horse battery staple", stored["password_hash"])
    assert "password" not in response.text
    cookie = response.headers["set-cookie"]
    assert main.AUTH_COOKIE_NAME in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie
    assert client.get("/api/auth/me").json()["user"]["user_id"] == response.json()["user"]["user_id"]


def test_duplicate_registration_and_invalid_credentials_are_generic(auth_client):
    client, _, _ = auth_client
    register(client, "farmer@example.com")
    duplicate = register(client, "FARMER@example.com")
    wrong = client.post("/api/auth/login", json={"email": "farmer@example.com", "password": "wrong password"}, headers=headers())
    missing_user = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "wrong password"}, headers=headers())

    assert duplicate.status_code == 409
    assert wrong.status_code == missing_user.status_code == 401
    assert wrong.json() == missing_user.json() == {"detail": "Email or password is incorrect."}


@pytest.mark.parametrize("payload", [{"email": "", "password": ""}, {"email": "bad", "password": "long enough"}, {"email": "a@b.com", "password": "short"}])
def test_registration_and_login_validate_inputs(auth_client, payload):
    client, _, _ = auth_client
    assert client.post("/api/auth/register", json=payload, headers=headers()).status_code == 422
    assert client.post("/api/auth/login", json=payload, headers=headers()).status_code == 422


def test_login_persists_session_and_logout_revokes_it(auth_client):
    client, _, _ = auth_client
    register(client, "farmer@example.com")
    client.cookies.clear()
    login = client.post("/api/auth/login", json={"email": "farmer@example.com", "password": "correct horse battery staple"}, headers=headers())
    assert login.status_code == 200
    token = client.cookies.get(main.AUTH_COOKIE_NAME)
    assert token and client.get("/api/auth/me").status_code == 200

    logout = client.post("/api/auth/logout", headers=headers())

    assert logout.status_code == 200
    client.cookies.set(main.AUTH_COOKIE_NAME, token)
    assert client.get("/api/auth/me").status_code == 401
    assert "Max-Age=0" in logout.headers["set-cookie"]


def test_expired_account_session_is_rejected(auth_client):
    client, users, _ = auth_client
    register(client, "farmer@example.com")
    users.rows[0]["session_expires_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)

    assert client.get("/api/auth/me").status_code == 401


def test_account_owns_multiple_farms_and_cannot_access_another_users_farm(auth_client):
    client_a, _, farms = auth_client
    user_a = register(client_a, "farmer-a@example.com").json()["user"]
    client_a.post("/api/farms", json={"farm_id": "farm-a-one"}, headers=headers())
    client_a.post("/api/farms", json={"farm_id": "farm-a-two"}, headers=headers())
    assert [row["farm_id"] for row in client_a.get("/api/farms").json()["items"]] == ["farm-a-one", "farm-a-two"]
    assert all(row["user_id"] == user_a["user_id"] for row in farms.rows)

    client_b = TestClient(main.app)
    register(client_b, "farmer-b@example.com")
    denied_observations = client_b.get("/api/farms/farm-a-one/observations")
    denied_advisories = client_b.get("/api/farms/farm-a-one/advisories")
    denied_write = client_b.post("/api/advisory", json={
        "farm_id": "farm-a-one", "latitude": 1, "longitude": 1,
        "soil_moisture": 20, "soil_ph": 6, "nitrogen": 1,
        "phosphorus": 1, "potassium": 1, "crop_name": "Rice",
        "growth_stage": "Flowering", "symptoms": [],
    }, headers=headers())

    assert client_b.get("/api/farms").json()["items"] == []
    assert denied_observations.status_code == denied_advisories.status_code == denied_write.status_code == 404


def test_account_session_does_not_break_demo_farm_cookie(auth_client, monkeypatch):
    client, _, _ = auth_client
    client.cookies.clear()
    monkeypatch.setattr(main, "create_farm", lambda farm_id, current_token=None, user_id=None: "demo-token")
    demo = client.post("/api/farms", json={"farm_id": "demo-farm"}, headers=headers())
    assert demo.status_code == 200
    assert client.cookies.get(main.COOKIE_NAME) == "demo-token"
    client.cookies.clear()
    monkeypatch.setattr(main, "get_farm_id_for_token", lambda token: "demo-farm" if token == "demo-token" else None)
    client.cookies.set(main.COOKIE_NAME, "demo-token")
    assert client.get("/api/farms").json()["items"] == [{"farm_id": "demo-farm"}]
