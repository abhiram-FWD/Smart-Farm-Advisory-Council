import logging
import json
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

import main
import agents.advisory_manager as advisory_manager


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "initialize_memory", Mock())
    monkeypatch.setattr(
        main,
        "get_farm_id_for_token",
        lambda token: "route-test-farm" if token == "test-farm-token" else None,
    )
    with TestClient(main.app) as test_client:
        test_client.cookies.set(main.COOKIE_NAME, "test-farm-token")
        yield test_client


def request_headers(origin="http://localhost:5173"):
    return {
        "Origin": origin,
        "X-AgriVision-Request": "same-origin",
    }


def request_payload():
    return {
        "farm_id": "route-test-farm",
        "latitude": 12.9,
        "longitude": 77.6,
        "soil_moisture": 30,
        "soil_ph": 6.5,
        "nitrogen": 40,
        "phosphorus": 20,
        "potassium": 25,
        "crop_name": "maize",
        "growth_stage": "vegetative",
        "symptoms": [],
    }


def test_advisory_route_returns_error_when_advisory_memory_save_warns(
    client, monkeypatch
):
    result = {
        "status": "completed_with_memory_warning",
        "farm_id": "route-test-farm",
        "memory_warning": "Advisory generated but persistence failed.",
        "weekly_action_list": ["Check soil moisture"],
    }
    generate = Mock(return_value=result)
    monkeypatch.setattr(main, "generate_farm_advisory", generate)

    response = client.post("/api/advisory", json=request_payload(), headers=request_headers())

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Farm advisory could not be saved to farm history."
    }
    generate.assert_called_once()


def test_weather_route_uses_saved_farm_coordinates_not_client_coordinates(client, monkeypatch):
    monkeypatch.setattr(main, "get_farm_profile", Mock(return_value={"latitude": 12.9, "longitude": 77.6}))
    forecast = {"source": "Open-Meteo", "location": {"latitude": 12.9, "longitude": 77.6}}
    weather = Mock(return_value=forecast)
    monkeypatch.setattr(main, "get_weather_forecast", weather)

    response = client.get("/api/farms/route-test-farm/weather?latitude=51&longitude=3")

    assert response.status_code == 200
    assert response.json() == forecast
    weather.assert_called_once_with(12.9, 77.6)


def test_weather_route_does_not_fall_back_to_unsaved_client_coordinates(client, monkeypatch):
    monkeypatch.setattr(main, "get_farm_profile", Mock(return_value={"latitude": None, "longitude": None}))
    weather = Mock()
    monkeypatch.setattr(main, "get_weather_forecast", weather)

    response = client.get("/api/farms/route-test-farm/weather?latitude=51&longitude=3")

    assert response.status_code == 422
    weather.assert_not_called()


def test_advisory_route_keeps_generation_failure_as_502(client, monkeypatch):
    monkeypatch.setattr(
        main,
        "generate_farm_advisory",
        Mock(return_value={"status": "failed", "error": "Weather agent failed."}),
    )

    response = client.post("/api/advisory", json=request_payload(), headers=request_headers())

    assert response.status_code == 502
    assert response.json()["detail"] == "Farm advisory generation failed."


def test_advisory_route_returns_503_for_redacted_storage_failure(client, monkeypatch):
    monkeypatch.setattr(
        main,
        "generate_farm_advisory",
        Mock(return_value={
            "status": "failed",
            "error": "Farm data storage is temporarily unavailable.",
        }),
    )

    response = client.post("/api/advisory", json=request_payload(), headers=request_headers())

    assert response.status_code == 503
    assert response.json() == {"detail": "Farm data storage is temporarily unavailable."}


def test_advisory_route_redacts_unexpected_exception(client, monkeypatch, caplog):
    secret_detail = "mongodb://user:password@private-host/database"
    monkeypatch.setattr(
        main,
        "generate_farm_advisory",
        Mock(side_effect=RuntimeError(secret_detail)),
    )

    with caplog.at_level(logging.ERROR):
        response = client.post("/api/advisory", json=request_payload(), headers=request_headers())

    assert response.status_code == 500
    assert response.json() == {"detail": "Advisory generation failed."}
    assert secret_detail not in response.text
    assert secret_detail not in caplog.text
    assert "exception_type=RuntimeError" in caplog.text


def test_advisory_route_keeps_completed_result(client, monkeypatch):
    result = {"status": "completed", "farm_id": "route-test-farm"}
    monkeypatch.setattr(main, "generate_farm_advisory", Mock(return_value=result))

    response = client.post("/api/advisory", json=request_payload(), headers=request_headers())

    assert response.status_code == 200
    assert response.json() == result


def test_advisory_route_returns_partial_result_as_successful_assessment(client, monkeypatch):
    result = {
        "status": "partial",
        "agent_failures": [{"agent": "Weather Agent", "message": "Weather output was unavailable."}],
        "agents": {"soil": {"status": "completed", "recommendations": ["Inspect soil"]}},
        "weekly_action_list": ["Inspect soil"],
    }
    monkeypatch.setattr(main, "generate_farm_advisory", Mock(return_value=result))
    response = client.post("/api/advisory", json=request_payload(), headers=request_headers())
    assert response.status_code == 200
    assert response.json() == result


def test_advisory_route_requires_farm_access(client, monkeypatch):
    client.cookies.clear()
    generate = Mock()
    monkeypatch.setattr(main, "generate_farm_advisory", generate)

    response = client.post(
        "/api/advisory",
        json=request_payload(),
        headers=request_headers(),
    )

    assert response.status_code == 401
    generate.assert_not_called()


def test_advisory_route_rejects_disallowed_origin(client, monkeypatch):
    generate = Mock()
    monkeypatch.setattr(main, "generate_farm_advisory", generate)

    response = client.post(
        "/api/advisory",
        json=request_payload(),
        headers=request_headers("https://attacker.invalid"),
    )

    assert response.status_code == 403
    generate.assert_not_called()


@pytest.mark.parametrize(
    "field",
    [
        "latitude",
        "longitude",
        "soil_moisture",
        "soil_ph",
        "nitrogen",
        "phosphorus",
        "potassium",
    ],
)
@pytest.mark.parametrize("invalid_value", [float("nan"), float("inf"), float("-inf")])
def test_advisory_route_rejects_non_finite_numeric_fields(
    client, monkeypatch, field, invalid_value
):
    generate = Mock()
    save_observation = Mock()
    monkeypatch.setattr(main, "generate_farm_advisory", generate)
    monkeypatch.setattr(advisory_manager, "save_farm_observation", save_observation)
    payload = request_payload()
    payload[field] = invalid_value

    response = client.post(
        "/api/advisory",
        content=json.dumps(payload, allow_nan=True),
        headers={**request_headers(), "Content-Type": "application/json"},
    )

    assert response.status_code == 422
    generate.assert_not_called()
    save_observation.assert_not_called()


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("latitude", -90.01),
        ("latitude", 90.01),
        ("longitude", -180.01),
        ("longitude", 180.01),
        ("soil_moisture", -0.01),
        ("soil_moisture", 100.01),
        ("soil_ph", -0.01),
        ("soil_ph", 14.01),
        ("nitrogen", -0.01),
        ("phosphorus", -0.01),
        ("potassium", -0.01),
    ],
)
def test_advisory_route_rejects_out_of_range_measurements(
    client, monkeypatch, field, invalid_value
):
    generate = Mock()
    save_observation = Mock()
    monkeypatch.setattr(main, "generate_farm_advisory", generate)
    monkeypatch.setattr(advisory_manager, "save_farm_observation", save_observation)
    payload = request_payload()
    payload[field] = invalid_value

    response = client.post("/api/advisory", json=payload, headers=request_headers())

    assert response.status_code == 422
    generate.assert_not_called()
    save_observation.assert_not_called()


def test_assessment_text_is_trimmed_without_changing_internal_spacing():
    payload = request_payload()
    payload.update({
        "crop_name": "  Sweet  corn  ",
        "growth_stage": "  Early  growth  ",
        "symptoms": ["  Yellow  leaves  ", " Wilting "],
    })

    request = main.FarmRequest(**payload)

    assert request.crop_name == "Sweet  corn"
    assert request.growth_stage == "Early  growth"
    assert request.symptoms == ["Yellow  leaves", "Wilting"]


@pytest.mark.parametrize(
    "updates",
    [
        {"crop_name": "   "},
        {"growth_stage": "\t "},
        {"crop_name": "c" * 101},
        {"growth_stage": "g" * 61},
        {"symptoms": ["x"] * 11},
        {"symptoms": ["   "]},
        {"symptoms": ["s" * 201]},
    ],
)
def test_advisory_route_rejects_invalid_text_without_saving(
    client, monkeypatch, updates
):
    generate = Mock()
    save_observation = Mock()
    monkeypatch.setattr(main, "generate_farm_advisory", generate)
    monkeypatch.setattr(advisory_manager, "save_farm_observation", save_observation)
    payload = request_payload()
    payload.update(updates)

    response = client.post("/api/advisory", json=payload, headers=request_headers())

    assert response.status_code == 422
    generate.assert_not_called()
    save_observation.assert_not_called()


@pytest.mark.parametrize(
    "updates",
    [
        {"crop_name": "   "},
        {"growth_stage": "\t "},
        {"crop_name": "c" * 101},
        {"growth_stage": "g" * 61},
        {"symptoms": ["x"] * 11},
        {"symptoms": ["   "]},
        {"symptoms": ["s" * 201]},
    ],
)
def test_assessment_rejects_blank_or_overlong_text(updates):
    payload = request_payload()
    payload.update(updates)

    with pytest.raises(ValueError):
        main.FarmRequest(**payload)


def test_nutrient_values_have_no_unsupported_upper_limit():
    payload = request_payload()
    payload.update({"nitrogen": 1e100, "phosphorus": 1e100, "potassium": 1e100})

    request = main.FarmRequest(**payload)

    assert request.nitrogen == 1e100
    assert request.phosphorus == 1e100
    assert request.potassium == 1e100


def test_documented_numeric_boundaries_are_inclusive():
    payload = request_payload()
    payload.update({
        "latitude": -90,
        "longitude": 180,
        "soil_moisture": 100,
        "soil_ph": 14,
        "nitrogen": 0,
        "phosphorus": 0,
        "potassium": 0,
    })

    request = main.FarmRequest(**payload)

    assert request.latitude == -90
    assert request.longitude == 180
    assert request.soil_moisture == 100
    assert request.soil_ph == 14


def test_lifespan_initializes_mongodb_indexes(monkeypatch):
    initialize = Mock()
    monkeypatch.setattr(main, "initialize_memory", initialize)

    with TestClient(main.app) as test_client:
        assert test_client.get("/health").status_code == 200

    initialize.assert_called_once_with()


def test_lifespan_mongodb_initialization_failure_does_not_block_startup(
    monkeypatch, caplog
):
    monkeypatch.setattr(
        main,
        "initialize_memory",
        Mock(side_effect=RuntimeError("database unavailable")),
    )

    with caplog.at_level(logging.ERROR):
        with TestClient(main.app) as test_client:
            response = test_client.get("/health")

    assert response.status_code == 200
    assert "MongoDB index initialization failed" in caplog.text
