from types import SimpleNamespace
from unittest.mock import Mock

from agents import advisory_manager
from memory import mongodb_memory


def test_save_observation_returns_id_stored_in_document(monkeypatch):
    inserted_records = []

    monkeypatch.setattr(
        mongodb_memory.farms_collection,
        "update_one",
        Mock(),
    )

    def insert_one(record):
        inserted_records.append(record)
        return SimpleNamespace(inserted_id="different-mongodb-object-id")

    monkeypatch.setattr(
        mongodb_memory.observations_collection,
        "insert_one",
        insert_one,
    )

    observation_id = mongodb_memory.save_farm_observation(
        "observation-id-test-farm",
        {"crop_name": "maize"},
    )

    assert observation_id == inserted_records[0]["observation_id"]
    assert observation_id != "different-mongodb-object-id"


def test_first_assessment_excludes_its_observation_from_history(monkeypatch):
    current_observation_id = "current-observation-uuid"
    orchestration_inputs = {}

    monkeypatch.setattr(
        advisory_manager,
        "save_farm_observation",
        Mock(return_value=current_observation_id),
    )
    monkeypatch.setattr(
        advisory_manager,
        "get_farm_history",
        Mock(return_value=[{"observation_id": current_observation_id}]),
    )
    monkeypatch.setattr(
        advisory_manager,
        "save_advisory",
        Mock(return_value="advisory-id"),
    )

    async def fake_orchestration(**kwargs):
        orchestration_inputs.update(kwargs)
        return {
            "status": "completed",
            "agents": {
                "weather": {"status": "completed", "forecast": {}},
                "soil": {"status": "completed"},
                "pest_disease": {"status": "completed"},
                "irrigation": {
                    "status": "completed",
                    "recommended_action": "Monitor soil moisture",
                },
            },
        }

    monkeypatch.setattr(
        advisory_manager,
        "run_semantic_kernel_orchestration",
        fake_orchestration,
    )

    result = advisory_manager.generate_farm_advisory(
        latitude=12.9,
        longitude=77.6,
        soil_moisture=30,
        soil_ph=6.5,
        nitrogen=40,
        phosphorus=20,
        potassium=25,
        crop_name="maize",
        growth_stage="vegetative",
        symptoms=[],
        farm_id="first-assessment-test-farm",
    )

    assert result["status"] == "completed"
    assert result["memory"]["previous_observations_count"] == 0
    assert result["historical_context_available"] is False
    assert orchestration_inputs["historical_context"] == ""
