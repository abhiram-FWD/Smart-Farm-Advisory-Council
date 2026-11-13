import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient

import main
from agents import advisory_manager
from memory import mongodb_memory


def test_history_api_with_disposable_mongodb(monkeypatch):
    uri = os.getenv("AGRIVISION_TEST_MONGODB_URI")
    db_name = os.getenv("AGRIVISION_TEST_DB_NAME")
    if not uri or not db_name:
        pytest.skip("Disposable MongoDB integration settings are not configured.")
    if db_name != "agrivision_test_db":
        pytest.fail("Integration tests require the isolated agrivision_test_db database.")

    test_client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    test_database = test_client[db_name]
    farms = test_database["farms"]
    observations = test_database["farm_observations"]
    advisories = test_database["advisories"]
    monkeypatch.setattr(mongodb_memory, "farms_collection", farms)
    monkeypatch.setattr(mongodb_memory, "observations_collection", observations)
    monkeypatch.setattr(mongodb_memory, "advisories_collection", advisories)
    mongodb_memory.initialize_memory()
    monkeypatch.setattr(main, "initialize_memory", lambda: None)

    async def test_orchestration(**inputs):
        return {
            "status": "completed",
            "expected_rainfall_next_3_days_mm": 3,
            "agents": {
                "weather": {
                    "status": "completed",
                    "forecast": {"source": "test fixture", "daily_forecast": {}},
                    "identified_risks": [],
                },
                "soil": {
                    "status": "completed",
                    "identified_risks": [],
                    "recommendations": ["Test-only soil action"],
                    "retrieved_sources": [],
                },
                "pest_disease": {
                    "status": "success",
                    "crop_report": {
                        "crop_name": inputs["crop_name"],
                        "growth_stage": inputs["growth_stage"],
                    },
                    "possible_pest_risks": [],
                    "possible_disease_risks": [],
                    "recommendations": [],
                    "retrieved_sources": [],
                },
                "irrigation": {
                    "status": "completed",
                    "recommended_action": "Test-only irrigation action",
                    "reason": "Integration test fixture.",
                },
            },
        }

    monkeypatch.setattr(
        advisory_manager,
        "run_semantic_kernel_orchestration",
        test_orchestration,
    )

    farm_id = f"integration-{uuid4()}"
    headers = {
        "Origin": "http://localhost:5173",
        "X-AgriVision-Request": "same-origin",
    }
    try:
        with TestClient(main.app) as api_client:
            registration = api_client.post(
                "/api/farms",
                json={"farm_id": farm_id},
                headers=headers,
            )
            assert registration.status_code == 200
            assert registration.json() == {"farm_id": farm_id, "registered": True}
            assert "HttpOnly" in registration.headers["set-cookie"]
            assert "Path=/api" in registration.headers["set-cookie"]
            assert "SameSite=lax" in registration.headers["set-cookie"]

            raw_token = api_client.cookies.get(main.COOKIE_NAME)
            assert raw_token
            farm_record = farms.find_one({"farm_id": farm_id})
            assert farm_record["access_token_hash"] == mongodb_memory._token_hash(raw_token)
            assert raw_token not in farm_record.values()
            assert raw_token not in registration.text

            assessment_response = api_client.post(
                "/api/advisory",
                json={
                    "farm_id": farm_id,
                    "latitude": 12.9,
                    "longitude": 77.6,
                    "soil_moisture": 28,
                    "soil_ph": 6.4,
                    "nitrogen": 40,
                    "phosphorus": 20,
                    "potassium": 25,
                    "crop_name": "test-only crop",
                    "growth_stage": "test-only stage",
                    "symptoms": ["test-only symptom"],
                },
                headers=headers,
            )
            assert assessment_response.status_code == 200
            assert assessment_response.json()["memory"]["previous_observations_count"] == 0

            observation_response = api_client.get(
                f"/api/farms/{farm_id}/observations"
            )
            advisory_response = api_client.get(
                f"/api/farms/{farm_id}/advisories"
            )
            cross_farm_response = api_client.get(
                f"/api/farms/{farm_id}-other/observations"
            )

        assert observation_response.status_code == 200
        assert observation_response.json()["items"][0]["observation"] == {
            "latitude": 12.9,
            "longitude": 77.6,
            "soil_moisture": 28,
            "soil_ph": 6.4,
            "nitrogen": 40,
            "phosphorus": 20,
            "potassium": 25,
            "crop_name": "test-only crop",
            "growth_stage": "test-only stage",
            "symptoms": ["test-only symptom"],
        }
        assert advisory_response.status_code == 200
        assert advisory_response.json()["items"][0]["advisory"]["weekly_action_list"] == [
            "Test-only soil action",
            "Test-only irrigation action",
        ]
        assert cross_farm_response.status_code == 404

        with TestClient(main.app) as unauthenticated_client:
            unauthorized_response = unauthenticated_client.get(
                f"/api/farms/{farm_id}/observations"
            )
        assert unauthorized_response.status_code == 401
    finally:
        farms.delete_many({"farm_id": farm_id})
        observations.delete_many({"farm_id": farm_id})
        advisories.delete_many({"farm_id": farm_id})
        test_client.close()
