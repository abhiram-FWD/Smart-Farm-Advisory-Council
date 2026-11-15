from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def history_client(monkeypatch):
    # TestClient uses plain HTTP, so Secure cookies would not be sent back by the client.
    monkeypatch.setattr(main, "COOKIE_SECURE", False)
    monkeypatch.setattr(main, "initialize_memory", Mock())
    monkeypatch.setattr(
        main,
        "get_farm_id_for_token",
        lambda token: "farm-owned" if token == "valid-token" else None,
    )
    monkeypatch.setattr(main, "count_farm_observations", lambda farm_id: 1)
    monkeypatch.setattr(main, "count_farm_advisories", lambda farm_id: 1)
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
        "skip": 0,
        "total": 1,
    }
    read.assert_called_once_with("farm-owned", 7, 0)


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
    assert response.json()["skip"] == 0
    assert response.json()["total"] == 1


def test_history_pagination_returns_offset_and_full_farm_count(history_client, monkeypatch):
    page = [{"observation_id": "observation-101", "farm_id": "farm-owned", "observation": {}, "created_at": "2026-01-01T00:00:00+00:00"}]
    read = Mock(return_value=page)
    monkeypatch.setattr(main, "get_farm_observations", read)
    monkeypatch.setattr(main, "count_farm_observations", lambda farm_id: 235)
    response = history_client.get("/api/farms/farm-owned/observations?limit=100&skip=100")
    assert response.status_code == 200
    assert response.json()["skip"] == 100
    assert response.json()["total"] == 235
    read.assert_called_once_with("farm-owned", 100, 100)


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


def test_weather_uses_selected_farm_profile_without_assessment(history_client, monkeypatch):
    monkeypatch.setattr(main, "get_farm_profile", Mock(return_value={"latitude": 12.5, "longitude": 77.2}))
    forecast = {"source": "Open-Meteo", "location": {"latitude": 12.5, "longitude": 77.2}, "daily_forecast": {"time": []}}
    weather = Mock(return_value=forecast)
    monkeypatch.setattr(main, "get_weather_forecast", weather)

    response = history_client.get("/api/farms/farm-owned/weather")

    assert response.status_code == 200
    assert response.json() == forecast
    weather.assert_called_once_with(12.5, 77.2)


def test_weather_rejects_cross_farm_and_missing_coordinates(history_client, monkeypatch):
    weather = Mock()
    monkeypatch.setattr(main, "get_weather_forecast", weather)
    response = history_client.get("/api/farms/farm-other/weather")
    assert response.status_code == 404
    weather.assert_not_called()

    monkeypatch.setattr(main, "get_farm_profile", Mock(return_value={}))
    monkeypatch.setattr(main, "get_farm_observations", Mock(return_value=[]))
    response = history_client.get("/api/farms/farm-owned/weather")
    assert response.status_code == 422


def test_exit_session_expires_access_without_deleting_farm_history(history_client, monkeypatch):
    delete_calls = []
    monkeypatch.setattr(main, "delete_user_session", lambda token: delete_calls.append(("session", token)))
    monkeypatch.setattr(main, "get_farm_observations", Mock(side_effect=AssertionError("exit must not read or delete history")))
    monkeypatch.setattr(main, "get_farm_advisories", Mock(side_effect=AssertionError("exit must not read or delete history")))
    response = history_client.post("/api/farms/session/exit", headers=browser_headers())
    assert response.status_code == 200
    assert response.json() == {"session_ended": True}
    assert main.COOKIE_NAME in response.headers["set-cookie"]
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert delete_calls == []


def test_farm_profile_update_is_scoped_and_returns_saved_values(history_client, monkeypatch):
    saved = Mock(side_effect=lambda farm_id, profile: profile)
    monkeypatch.setattr(main, "update_farm_profile", saved)
    response = history_client.put(
        "/api/farms/farm-owned/profile",
        json={"latitude": 12.5, "longitude": 77.2, "crop_name": "Rice", "growth_stage": "Tillering", "planting_date": "2026-06-01"},
        headers=browser_headers(),
    )
    assert response.status_code == 200
    assert response.json()["crop_name"] == "Rice"
    saved.assert_called_once()

    saved.reset_mock()
    response = history_client.put(
        "/api/farms/farm-other/profile", json={"crop_name": "Rice"}, headers=browser_headers()
    )
    assert response.status_code == 404
    saved.assert_not_called()


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
        "/api/farms/farm-owned/observations?skip=-1",
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
    assert "SameSite=none" in cookie
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
