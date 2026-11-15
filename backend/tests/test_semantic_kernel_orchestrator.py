
import pytest

from agents.semantic_kernel_orchestrator import (
    run_semantic_kernel_orchestration
)
import agents.farm_agents_plugin as plugin_module


@pytest.mark.asyncio
async def test_semantic_kernel_orchestration(monkeypatch):
    monkeypatch.setattr(plugin_module, "weather_agent", lambda *args, **kwargs: {
        "status": "completed", "agent": "Weather Agent",
        "forecast": {"source": "isolated fixture", "daily_forecast": {
            "precipitation_sum": [0, 0, 0],
            "precipitation_probability_max": [0, 0, 0],
        }, "recent_observed_rainfall": {"date": "2026-06-09", "precipitation_mm": 2.5}},
        "identified_risks": [],
    })
    monkeypatch.setattr(plugin_module, "soil_agent", lambda *args, **kwargs: {
        "status": "completed", "identified_risks": [], "recommendations": [],
    })
    monkeypatch.setattr(plugin_module, "crop_health_agent", lambda *args, **kwargs: {
        "status": "success", "possible_pest_risks": [], "possible_disease_risks": [],
        "recommendations": [], "expert_inspection_required": True,
    })
    irrigation_calls = []
    def irrigation_fixture(**kwargs):
        irrigation_calls.append(kwargs)
        return {"status": "completed", "recommended_action": "fixture action"}
    monkeypatch.setattr(plugin_module, "irrigation_agent", irrigation_fixture)

    # Demo inputs only, not actual farm readings.
    result = await run_semantic_kernel_orchestration(
        latitude=31.22,
        longitude=75.77,
        soil_moisture=20.0,
        soil_ph=5.0,
        nitrogen=30.0,
        phosphorus=15.0,
        potassium=25.0,
        crop_name="Wheat",
        growth_stage="Vegetative",
        symptoms=["Yellow leaves", "Wilting"]
    )

    expected_agents = {
        "weather",
        "soil",
        "pest_disease",
        "irrigation"
    }

    assert result.get("status") == "completed"
    assert set(result["agents"].keys()) == expected_agents

    for agent_name, agent_result in result["agents"].items():
        assert agent_result.get("status") in ("completed", "success"), (
            f"{agent_name} did not complete successfully"
        )

    assert result["expected_rainfall_next_3_days_mm"] >= 0
    assert irrigation_calls[0]["precipitation_probability_max"] == [0, 0, 0]
    assert irrigation_calls[0]["recent_rainfall_mm"] == 2.5
    assert irrigation_calls[0]["recent_rainfall_date"] == "2026-06-09"


@pytest.mark.asyncio
async def test_semantic_kernel_passes_incomplete_rainfall_as_unavailable(monkeypatch):
    monkeypatch.setattr(plugin_module, "weather_agent", lambda *args, **kwargs: {
        "status": "completed", "agent": "Weather Agent",
        "forecast": {"source": "isolated fixture", "daily_forecast": {
            "precipitation_sum": [1, None, 3],
        }},
        "identified_risks": [],
    })
    monkeypatch.setattr(plugin_module, "soil_agent", lambda *args, **kwargs: {
        "status": "completed", "identified_risks": [], "recommendations": [],
    })
    monkeypatch.setattr(plugin_module, "crop_health_agent", lambda *args, **kwargs: {
        "status": "success", "possible_pest_risks": [], "possible_disease_risks": [],
        "recommendations": [], "expert_inspection_required": True,
    })

    result = await run_semantic_kernel_orchestration(
        latitude=31.22, longitude=75.75, soil_moisture=20.0, soil_ph=6.5,
        nitrogen=10.0, phosphorus=10.0, potassium=10.0, crop_name="Wheat",
        growth_stage="Vegetative", symptoms=[],
    )

    assert result["expected_rainfall_next_3_days_mm"] is None
    assert result["agents"]["irrigation"]["recommended_action"] == "Check local forecast before deciding"


@pytest.mark.asyncio
async def test_failed_specialist_is_reported_and_other_outputs_are_preserved(monkeypatch):
    def unavailable_weather(*args):
        raise RuntimeError("provider detail must not leak")

    monkeypatch.setattr(plugin_module, "weather_agent", unavailable_weather)
    monkeypatch.setattr(plugin_module, "soil_agent", lambda *args, **kwargs: {
        "status": "completed", "soil_report": {"moisture": 35}, "recommendations": [],
    })
    monkeypatch.setattr(plugin_module, "crop_health_agent", lambda *args, **kwargs: {
        "status": "success", "evidence_summary": "No supported finding.",
    })
    result = await run_semantic_kernel_orchestration(
        latitude=12, longitude=77, soil_moisture=35, soil_ph=6.5,
        nitrogen=10, phosphorus=10, potassium=10, crop_name="Rice",
        growth_stage="Tillering", symptoms=[],
    )
    assert result["status"] == "partial"
    assert result["agents"]["weather"]["status"] == "failed"
    assert result["agents"]["weather"]["execution_status"] == "failed"
    assert result["agents"]["soil"]["soil_report"]["moisture"] == 35
    assert result["agents"]["pest_disease"]["evidence_summary"] == "No supported finding."
    assert result["agents"]["irrigation"]["status"] == "completed"
    assert {failure["agent"] for failure in result["agent_failures"]} == {"weather"}
    assert "provider detail" not in str(result)
    assert result["agent_failures"][0]["message"]


@pytest.mark.asyncio
async def test_provider_degradation_is_not_reported_as_a_fully_validated_assessment(monkeypatch):
    monkeypatch.setattr(plugin_module, "weather_agent", lambda *args, **kwargs: {
        "status": "completed", "identified_risks": [],
    })
    monkeypatch.setattr(plugin_module, "soil_agent", lambda *args, **kwargs: {
        "status": "completed", "execution_status": "completed",
        "quality_status": "degraded", "quality_reason": "provider_error",
        "evidence_status": "insufficient", "recommendations": [],
    })
    monkeypatch.setattr(plugin_module, "crop_health_agent", lambda *args, **kwargs: {
        "status": "success", "quality_status": "validated",
    })
    monkeypatch.setattr(plugin_module, "irrigation_agent", lambda **kwargs: {
        "status": "completed", "recommended_action": "Monitor field conditions",
    })

    result = await run_semantic_kernel_orchestration(
        latitude=12, longitude=77, soil_moisture=35, soil_ph=6.5,
        nitrogen=10, phosphorus=10, potassium=10, crop_name="Rice",
        growth_stage="Tillering", symptoms=[],
    )

    assert result["status"] == "partial"
    assert result["agent_failures"] == []
    assert result["agents"]["soil"]["evidence_status"] == "insufficient"
    assert result["agents"]["soil"]["status"] == "partial"
    assert result["agents"]["soil"]["execution_status"] == "completed"
    assert result["agent_degradations"] == [{
        "agent": "soil", "reason": "provider_error",
        "message": "Agent execution completed, but validated analysis was limited.",
    }]
