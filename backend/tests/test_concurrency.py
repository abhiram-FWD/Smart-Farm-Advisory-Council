import asyncio
import time
from unittest.mock import patch

import pytest

from agents import coordinator


def fake_weather_agent(latitude, longitude):
    time.sleep(2)
    return {
        "agent": "Weather Agent",
        "forecast": {
            "daily_forecast": {
                "precipitation_sum": [0, 0, 0]
            }
        },
        "status": "completed"
    }


def fake_soil_agent(moisture, ph, nitrogen, phosphorus, potassium):
    time.sleep(2)
    return {
        "agent": "Soil Agent",
        "identified_risks": [],
        "recommendations": [],
        "status": "completed"
    }


def fake_crop_agent(crop_name, growth_stage, symptoms):
    time.sleep(2)
    return {
        "agent": "Crop Health Agent",
        "identified_risks": [],
        "recommendations": [],
        "status": "completed"
    }


def fake_irrigation_agent(
    soil_moisture, expected_rainfall, crop_name, precipitation_probabilities=None
):
    return {
        "agent": "Irrigation Planner",
        "recommended_action": "Test completed",
        "status": "completed"
    }


@pytest.mark.asyncio
async def test_concurrent_execution():

    with (
        patch.object(coordinator, "weather_agent", fake_weather_agent),
        patch.object(coordinator, "soil_agent", fake_soil_agent),
        patch.object(coordinator, "crop_health_agent", fake_crop_agent),
        patch.object(coordinator, "irrigation_agent", fake_irrigation_agent)
    ):

        start_time = time.perf_counter()

        result = await coordinator.coordinate_farm_agents(
            31.22,
            75.77,
            20,
            5.0,
            30,
            15,
            25,
            "Wheat",
            "Vegetative",
            ["Yellow leaves"]
        )

        elapsed_time = time.perf_counter() - start_time

        print("\nExecution time:", round(elapsed_time, 2), "seconds")
        print("Coordination status:", result["status"])

        assert result["status"] == "completed"
        assert elapsed_time < 4.5

        print("\nCONCURRENT EXECUTION TEST PASSED")
