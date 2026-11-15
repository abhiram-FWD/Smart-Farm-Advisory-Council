from unittest.mock import AsyncMock, Mock

import pytest

import agents.advisory_manager as advisory_manager


def assessment_kwargs():
    return {
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
        "farm_id": "safe-error-test-farm",
        "llm_json": Mock(side_effect=RuntimeError("offline test")),
    }


@pytest.fixture
def memory_stubs(monkeypatch):
    monkeypatch.setattr(advisory_manager, "save_farm_observation", Mock(return_value="observation-id"))
    monkeypatch.setattr(advisory_manager, "get_farm_history", Mock(return_value=[]))
    monkeypatch.setattr(advisory_manager, "count_farm_observations", Mock(return_value=1))
    monkeypatch.setattr(advisory_manager, "save_advisory", Mock(return_value="advisory-id"))


def test_database_exception_is_redacted_and_logged_without_exception_text(
    monkeypatch, caplog
):
    private_detail = "mongodb://user:password@private-host/database"
    monkeypatch.setattr(
        advisory_manager,
        "save_farm_observation",
        Mock(side_effect=RuntimeError(private_detail)),
    )

    with caplog.at_level("ERROR"):
        result = advisory_manager.generate_farm_advisory(**assessment_kwargs())

    assert result["status"] == "failed"
    assert result["error"] == "Farm data storage is temporarily unavailable."
    assert private_detail not in str(result)
    assert private_detail not in caplog.text


def test_orchestration_exception_is_redacted_and_remains_failure(
    monkeypatch, memory_stubs, caplog
):
    private_detail = "provider response with api_key=do-not-log"
    monkeypatch.setattr(
        advisory_manager,
        "run_semantic_kernel_orchestration",
        Mock(side_effect=RuntimeError(private_detail)),
    )

    with caplog.at_level("ERROR"):
        result = advisory_manager.generate_farm_advisory(**assessment_kwargs())

    assert result["status"] == "failed"
    assert result["error"] == "Farm advisory orchestration could not be completed."
    assert result["observation_saved"] is True
    assert private_detail not in str(result)
    assert private_detail not in caplog.text


@pytest.mark.parametrize(
    "orchestration_result",
    [
        {"status": "failed", "error": "private provider response"},
        {
            "status": "completed",
            "agents": {
                "weather": {"status": "completed"},
                "soil": {"status": "failed", "error": "private AI response"},
                "pest_disease": {"status": "success"},
                "irrigation": {"status": "completed"},
            },
        },
    ],
)
def test_agent_and_orchestration_error_payloads_are_not_returned(
    monkeypatch, memory_stubs, orchestration_result
):
    monkeypatch.setattr(
        advisory_manager,
        "run_semantic_kernel_orchestration",
        Mock(return_value=orchestration_result),
    )

    result = advisory_manager.generate_farm_advisory(**assessment_kwargs())

    assert result["status"] == "failed"
    assert "private" not in str(result)
    assert "agent_result" not in result
    assert "orchestration" not in result


def test_non_dictionary_orchestration_failure_does_not_return_farm_id(
    monkeypatch, memory_stubs
):
    monkeypatch.setattr(
        advisory_manager,
        "run_semantic_kernel_orchestration",
        AsyncMock(return_value=None),
    )

    result = advisory_manager.generate_farm_advisory(**assessment_kwargs())

    assert result == {
        "project": "Smart Farm Advisory Council",
        "status": "failed",
        "error": "Invalid orchestration result.",
    }
    assert "farm_id" not in result


def test_persistence_warning_is_safe_and_preserves_generated_advisory(
    monkeypatch, memory_stubs, caplog
):
    generated = {
        "status": "completed",
        "coordination": "Semantic Kernel Fan-out/Fan-in",
        "agents": {
            "weather": {"status": "completed"},
            "soil": {"status": "completed", "identified_risks": [], "recommendations": []},
            "pest_disease": {
                "status": "success",
                "possible_pest_risks": [],
                "possible_disease_risks": [],
                "recommendations": [],
            },
            "irrigation": {"status": "completed", "recommended_action": "No action"},
        },
        "expected_rainfall_next_3_days_mm": 0,
    }
    private_detail = "private database URI details"
    monkeypatch.setattr(
        advisory_manager,
        "run_semantic_kernel_orchestration",
        AsyncMock(return_value=generated),
    )
    monkeypatch.setattr(
        advisory_manager,
        "save_advisory",
        Mock(side_effect=RuntimeError(private_detail)),
    )

    with caplog.at_level("ERROR"):
        result = advisory_manager.generate_farm_advisory(**assessment_kwargs())

    assert result["status"] == "completed_with_memory_warning"
    assert result["agents"] == generated["agents"]
    assert result["weekly_action_list"] == ["No action"]
    assert result["memory_warning"] == "Advisory generated, but it could not be saved to farm history."
    assert private_detail not in str(result)
    assert private_detail not in caplog.text
