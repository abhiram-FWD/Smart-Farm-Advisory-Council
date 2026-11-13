
import pytest

from semantic_kernel import Kernel
from semantic_kernel.functions import KernelArguments

from agents.farm_agents_plugin import FarmAgentsPlugin
import agents.farm_agents_plugin as plugin_module


@pytest.mark.asyncio
async def test_semantic_kernel_agent_invocation(monkeypatch):
    monkeypatch.setattr(plugin_module, "weather_agent", lambda latitude, longitude: {
        "status": "completed", "agent": "Weather Agent",
        "forecast": {"source": "isolated fixture", "daily_forecast": {
            "precipitation_sum": [0, 0, 0], "time": ["2026-01-01"],
            "temperature_2m_max": [20], "temperature_2m_min": [10],
            "precipitation_probability_max": [0],
        }}, "identified_risks": [],
    })
    monkeypatch.setattr(plugin_module, "soil_agent", lambda *args, **kwargs: {
        "status": "completed", "identified_risks": [], "recommendations": [],
    })
    monkeypatch.setattr(plugin_module, "crop_health_agent", lambda *args, **kwargs: {
        "status": "success", "possible_pest_risks": [], "possible_disease_risks": [],
        "recommendations": [], "expert_inspection_required": True,
    })
    monkeypatch.setattr(plugin_module, "irrigation_agent", lambda **kwargs: {
        "status": "completed", "recommended_action": "fixture action",
    })

    kernel = Kernel()

    kernel.add_plugin(
        FarmAgentsPlugin(),
        plugin_name="FarmAgents"
    )

    # Demo inputs only, not actual farm readings.
    farm_data = {
        "latitude": 31.22,
        "longitude": 75.77,
        "soil_moisture": 20.0,
        "soil_ph": 5.0,
        "nitrogen": 30.0,
        "phosphorus": 15.0,
        "potassium": 25.0,
        "crop_name": "Wheat",
        "growth_stage": "Vegetative",
        "symptoms": ["Yellow leaves", "Wilting"]
    }

    # 1. Weather Agent
    weather = await kernel.invoke(
        plugin_name="FarmAgents",
        function_name="get_weather_advisory",
        arguments=KernelArguments(
            latitude=farm_data["latitude"],
            longitude=farm_data["longitude"]
        )
    )

    weather_result = weather.value

    assert weather_result.get("status") == "completed"

    forecast = weather_result["forecast"]["daily_forecast"]
    rainfall = forecast.get("precipitation_sum")

    assert isinstance(rainfall, list)
    assert rainfall

    expected_rainfall = sum(
        value
        for value in rainfall[:3]
        if isinstance(value, (int, float))
    )

    # 2. Soil Agent
    soil = await kernel.invoke(
        plugin_name="FarmAgents",
        function_name="get_soil_advisory",
        arguments=KernelArguments(
            soil_moisture=farm_data["soil_moisture"],
            soil_ph=farm_data["soil_ph"],
            nitrogen=farm_data["nitrogen"],
            phosphorus=farm_data["phosphorus"],
            potassium=farm_data["potassium"]
            ,crop_name=farm_data["crop_name"]
        )
    )

    soil_result = soil.value

    # 3. Pest and Disease Agent
    crop = await kernel.invoke(
        plugin_name="FarmAgents",
        function_name="get_pest_disease_advisory",
        arguments=KernelArguments(
            crop_name=farm_data["crop_name"],
            growth_stage=farm_data["growth_stage"],
            symptoms=farm_data["symptoms"]
        )
    )

    crop_result = crop.value

    # 4. Irrigation Planner
    irrigation = await kernel.invoke(
        plugin_name="FarmAgents",
        function_name="get_irrigation_advisory",
        arguments=KernelArguments(
            soil_moisture=farm_data["soil_moisture"],
            expected_rainfall=expected_rainfall,
            crop_name=farm_data["crop_name"]
        )
    )

    irrigation_result = irrigation.value

    results = {
        "Weather Agent": weather_result,
        "Soil Agent": soil_result,
        "Pest and Disease Agent": crop_result,
        "Irrigation Planner": irrigation_result
    }

    successful_statuses = {"completed", "success"}

    for agent_name, result in results.items():
        assert result.get("status") in successful_statuses, (
            f"{agent_name} failed: {result}"
        )

    assert set(results.keys()) == {
        "Weather Agent",
        "Soil Agent",
        "Pest and Disease Agent",
        "Irrigation Planner"
    }
