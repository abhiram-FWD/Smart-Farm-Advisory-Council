
import asyncio

from semantic_kernel import Kernel
from semantic_kernel.functions import KernelArguments

from agents.farm_agents_plugin import FarmAgentsPlugin
from tools.weather_tool import aggregate_rainfall_if_complete


async def invoke_agent(kernel, function_name, **arguments):
    """Invoke a Semantic Kernel function without blocking the event loop."""

    def run_invocation():
        return asyncio.run(
            kernel.invoke(
                plugin_name="FarmAgents",
                function_name=function_name,
                arguments=KernelArguments(**arguments)
            )
        )

    result = await asyncio.to_thread(run_invocation)
    return result.value


async def run_semantic_kernel_orchestration(
    latitude,
    longitude,
    soil_moisture,
    soil_ph,
    nitrogen,
    phosphorus,
    potassium,
    crop_name,
    growth_stage,
    symptoms,
    historical_context=""
):
    """
    Coordinate farm agents using Semantic Kernel fan-out/fan-in.

    Historical farm observations are shared with the Soil
    Agent and Pest and Disease Retrieval Agent.
    """

    kernel = Kernel()

    kernel.add_plugin(
        FarmAgentsPlugin(),
        plugin_name="FarmAgents"
    )

    print("\nSEMANTIC KERNEL ORCHESTRATOR")
    print("============================")
    print("\nStarting parallel agent execution...")

    # 1. FAN-OUT: Run independent agents concurrently.

    weather_task = invoke_agent(
        kernel,
        "get_weather_advisory",
        latitude=latitude,
        longitude=longitude
    )

    soil_task = invoke_agent(
        kernel,
        "get_soil_advisory",
        soil_moisture=soil_moisture,
        soil_ph=soil_ph,
        nitrogen=nitrogen,
        phosphorus=phosphorus,
        potassium=potassium,
        crop_name=crop_name,
        historical_context=historical_context
    )

    crop_task = invoke_agent(
        kernel,
        "get_pest_disease_advisory",
        crop_name=crop_name,
        growth_stage=growth_stage,
        symptoms=symptoms,
        historical_context=historical_context
    )

    results = await asyncio.gather(
        weather_task,
        soil_task,
        crop_task,
        return_exceptions=True
    )

    weather_result, soil_result, crop_result = results

    agent_results = {
        "weather": weather_result,
        "soil": soil_result,
        "pest_disease": crop_result
    }

    # 2. Validate the three parallel agent responses.

    successful_statuses = {"completed", "success"}

    for agent_name, result in agent_results.items():

        if isinstance(result, Exception):
            raise RuntimeError(
                f"{agent_name} agent execution error: {result}"
            )

        if not isinstance(result, dict):
            raise RuntimeError(
                f"{agent_name} agent returned an invalid response: "
                f"{result!r}"
            )

        if result.get("error"):
            raise RuntimeError(
                f"{agent_name} agent error: {result['error']}"
            )

        if result.get("status") not in successful_statuses:
            raise RuntimeError(
                f"{agent_name} agent failed. "
                f"Received status: {result.get('status', 'missing')}. "
                f"Response: {result}"
            )

    print("Weather Agent:", weather_result.get("status"))
    print("Soil Agent:", soil_result.get("status"))
    print("Pest and Disease Agent:", crop_result.get("status"))

    print("\nFan-out completed. All results collected.")

    print(
        "Historical context supplied:",
        bool(historical_context)
    )

    # 3. FAN-IN: Extract the rainfall forecast.

    forecast = weather_result.get("forecast", {}).get(
        "daily_forecast", {}
    )

    rainfall = forecast.get("precipitation_sum")
    precipitation_probabilities = forecast.get("precipitation_probability_max")

    expected_rainfall = aggregate_rainfall_if_complete(rainfall)

    print(
        "Expected rainfall for next 3 days:",
        expected_rainfall,
        "mm"
    )

    # 4. Run Irrigation Planner after fan-in.

    print("\nStarting Irrigation Planner...")

    irrigation_result = await invoke_agent(
        kernel,
        "get_irrigation_advisory",
        soil_moisture=soil_moisture,
        expected_rainfall=expected_rainfall,
        crop_name=crop_name,
        precipitation_probability_max=precipitation_probabilities,
    )

    if not isinstance(irrigation_result, dict):
        raise RuntimeError(
            f"Irrigation Planner returned an invalid response: "
            f"{irrigation_result!r}"
        )

    if irrigation_result.get("error"):
        raise RuntimeError(
            f"Irrigation Planner error: "
            f"{irrigation_result['error']}"
        )

    if irrigation_result.get("status") not in successful_statuses:
        raise RuntimeError(
            "Irrigation Planner execution failed: "
            f"{irrigation_result}"
        )

    print("Irrigation Planner:", irrigation_result.get("status"))

    # 5. Return the unified result.

    final_result = {
        "status": "completed",
        "coordination": "Semantic Kernel Fan-out/Fan-in",
        "historical_context_available": bool(historical_context),
        "agents": {
            "weather": weather_result,
            "soil": soil_result,
            "pest_disease": crop_result,
            "irrigation": irrigation_result
        },
        "expected_rainfall_next_3_days_mm": expected_rainfall
    }

    print("\nAll agents completed successfully.")
    print("Unified farm advisory generated.")

    return final_result
