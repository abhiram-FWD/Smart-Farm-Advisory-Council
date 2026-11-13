
import pytest

from agents.semantic_kernel_orchestrator import (
    run_semantic_kernel_orchestration
)
import agents.farm_agents_plugin as plugin_module


@pytest.mark.asyncio
async def test_semantic_kernel_orchestration(monkeypatch):
    monkeypatch.setattr(plugin_module, "weather_agent", lambda latitude, longitude: {
        "status": "completed", "agent": "Weather Agent",
        "forecast": {"source": "isolated fixture", "daily_forecast": {
            "precipitation_sum": [0, 0, 0],
            "precipitation_probability_max": [0, 0, 0],
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


@pytest.mark.asyncio
async def test_semantic_kernel_passes_incomplete_rainfall_as_unavailable(monkeypatch):
    monkeypatch.setattr(plugin_module, "weather_agent", lambda *args: {
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
    assert result["agents"]["irrigation"]["recommended_action"] == "Irrigation guidance unavailable"
