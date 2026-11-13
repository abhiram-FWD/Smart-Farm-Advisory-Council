
import asyncio
from tools.weather_tool import aggregate_rainfall_if_complete

from agents.weather_agent import weather_agent
from agents.soil_agent import soil_agent
from agents.crop_health_agent import crop_health_agent
from agents.irrigation_agent import irrigation_agent


async def run_agent(agent_function, *args):
    """
    Run a synchronous agent in a separate thread.

    This allows independent agents to execute concurrently
    without blocking the asyncio event loop.
    """
    return await asyncio.to_thread(agent_function, *args)


async def coordinate_farm_agents(
    latitude,
    longitude,
    soil_moisture,
    soil_ph,
    nitrogen,
    phosphorus,
    potassium,
    crop_name,
    growth_stage,
    symptoms
):
    """
    Coordinates independent farm agents using fan-out/fan-in.

    Fan-out:
        Weather, Soil and Crop Health execute concurrently.

    Fan-in:
        Collect their results and pass relevant information
        to the Irrigation Planner.
    """

    # 1. FAN-OUT: Start independent agents concurrently
    weather_task = run_agent(
        weather_agent,
        latitude,
        longitude
    )

    soil_task = run_agent(
        soil_agent,
        soil_moisture,
        soil_ph,
        nitrogen,
        phosphorus,
        potassium
    )

    crop_task = run_agent(
        crop_health_agent,
        crop_name,
        growth_stage,
        symptoms
    )

    # 2. FAN-IN: Wait for all three agents
    weather_result, soil_result, crop_result = await asyncio.gather(
        weather_task,
        soil_task,
        crop_task
    )

    # 3. Validate weather response
    if weather_result.get("error"):
        return {
            "status": "failed",
            "error": weather_result["error"]
        }

    forecast = weather_result.get("forecast", {})
    daily_forecast = forecast.get("daily_forecast", {})

    # 4. Calculate a total only when all three daily values are available.
    expected_rainfall = aggregate_rainfall_if_complete(
        daily_forecast.get("precipitation_sum")
    )
    precipitation_probabilities = daily_forecast.get(
        "precipitation_probability_max"
    )

    # 5. Run Irrigation Planner after collecting soil and weather
    irrigation_result = await run_agent(
        irrigation_agent,
        soil_moisture,
        expected_rainfall,
        crop_name,
        precipitation_probabilities,
    )

    # 6. Return all agent results
    return {
        "coordination": "Fan-out/Fan-in",
        "status": "completed",
        "agents": {
            "weather": weather_result,
            "soil": soil_result,
            "crop_health": crop_result,
            "irrigation": irrigation_result
        },
        "expected_rainfall_next_3_days_mm": expected_rainfall
    }


def run_farm_coordination(*args):
    """
    Synchronous entry point for existing Python code
    and FastAPI integration.
    """
    return asyncio.run(coordinate_farm_agents(*args))
