from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def history_client(monkeypatch):
    monkeypatch.setattr(main, "initialize_memory", Mock())
    monkeypatch.setattr(
        main,
        "get_farm_id_for_token",
        lambda token: "farm-owned" if token == "valid-token" else None,
    )
    with TestClient(main.app) as client:
        client.cookies.set(main.COOKIE_NAME, "valid-token")
        yield client


def browser_headers(origin="http://localhost:5173"):
    return {"Origin": origin, "X-AgriVision-Request": "same-origin"}


def test_observation_history_returns_real_document_shape_and_iso_date(
    history_client, monkeypatch
):
    created_at = datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc)
    stored_record = {
        "observation_id": "observation-real-id",
        "farm_id": "farm-owned",
        "observation": {"crop_name": "maize", "soil_moisture": 31},
        "created_at": created_at,
    }
    read = Mock(return_value=[stored_record])
    monkeypatch.setattr(main, "get_farm_observations", read)

    response = history_client.get("/api/farms/farm-owned/observations?limit=7")

    assert response.status_code == 200
    assert response.json() == {
        "farm_id": "farm-owned",
        "items": [{
            "observation_id": "observation-real-id",
            "farm_id": "farm-owned",
            "observation": {"crop_name": "maize", "soil_moisture": 31},
            "created_at": "2026-01-02T03:04:00+00:00",
        }],
        "limit": 7,
    }
    read.assert_called_once_with("farm-owned", 7)


def test_advisory_history_returns_saved_advisory_payload(history_client, monkeypatch):
    record = {
        "advisory_id": "advisory-real-id",
        "farm_id": "farm-owned",
        "advisory": {"weekly_action_list": ["Inspect the crop"]},
        "created_at": "2026-01-02T03:04:00+00:00",
    }
    monkeypatch.setattr(main, "get_farm_advisories", Mock(return_value=[record]))

    response = history_client.get("/api/farms/farm-owned/advisories")

    assert response.status_code == 200
    assert response.json()["items"] == [record]
    assert response.json()["limit"] == 20


@pytest.mark.parametrize(
    ("route", "reader"),
    [
        ("observations", "get_farm_observations"),
        ("advisories", "get_farm_advisories"),
    ],
)
def test_empty_history_returns_empty_items(history_client, monkeypatch, route, reader):
    monkeypatch.setattr(main, reader, Mock(return_value=[]))

    response = history_client.get(f"/api/farms/farm-owned/{route}")

    assert response.status_code == 200
    assert response.json()["items"] == []


def test_history_requires_credential(history_client, monkeypatch):
    history_client.cookies.clear()
    read = Mock()
    monkeypatch.setattr(main, "get_farm_observations", read)

    response = history_client.get("/api/farms/farm-owned/observations")

    assert response.status_code == 401
    read.assert_not_called()


def test_credential_for_another_farm_cannot_read_history(history_client, monkeypatch):
    read = Mock()
    monkeypatch.setattr(main, "get_farm_observations", read)

    response = history_client.get("/api/farms/farm-other/observations")

    assert response.status_code == 404
    read.assert_not_called()


@pytest.mark.parametrize(
    "url",
    [
        "/api/farms/bad%20farm/observations",
        "/api/farms/farm-owned/observations?limit=0",
        "/api/farms/farm-owned/observations?limit=101",
    ],
)
def test_history_rejects_invalid_ids_and_limits(history_client, url):
    response = history_client.get(url)
    assert response.status_code == 422


def test_registration_returns_cookie_without_token_in_response(
    history_client, monkeypatch
):
    history_client.cookies.clear()
    monkeypatch.setattr(main, "create_farm", Mock(return_value="raw-token-for-cookie"))

    response = history_client.post(
        "/api/farms",
        json={"farm_id": "farm-created"},
        headers=browser_headers(),
    )

    assert response.status_code == 200
    assert response.json() == {"farm_id": "farm-created", "registered": True}
    assert "raw-token-for-cookie" not in response.text
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Path=/api" in cookie
    assert "Secure" not in cookie


def test_registration_refuses_to_overwrite_active_farm_cookie(
    history_client, monkeypatch
):
    create = Mock(side_effect=main.ActiveFarmMismatchError())
    monkeypatch.setattr(main, "create_farm", create)

    response = history_client.post(
        "/api/farms",
        json={"farm_id": "farm-other"},
        headers=browser_headers(),
    )

    assert response.status_code == 409
    assert "different farm" in response.json()["detail"]
    assert history_client.cookies.get(main.COOKIE_NAME) == "valid-token"


def test_registration_requires_allowed_origin(history_client, monkeypatch):
    create = Mock(return_value="unused-token")
    monkeypatch.setattr(main, "create_farm", create)

    response = history_client.post(
        "/api/farms",
        json={"farm_id": "farm-created"},
        headers=browser_headers("https://attacker.invalid"),
    )

    assert response.status_code == 403
    create.assert_not_called()


def test_registration_marks_cookie_secure_when_production_requires_it(
    history_client, monkeypatch
):
    history_client.cookies.clear()
    monkeypatch.setattr(main, "COOKIE_SECURE", True)
    monkeypatch.setattr(main, "create_farm", Mock(return_value="production-token"))

    response = history_client.post(
        "/api/farms",
        json={"farm_id": "farm-created"},
        headers=browser_headers(),
    )

    assert response.status_code == 200
    assert "Secure" in response.headers["set-cookie"]
