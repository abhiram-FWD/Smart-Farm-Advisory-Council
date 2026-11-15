
import asyncio

from semantic_kernel import Kernel
from semantic_kernel.functions import KernelArguments

from agents.farm_agents_plugin import FarmAgentsPlugin
from tools.weather_tool import aggregate_rainfall_if_complete


async def invoke_agent(function_name, **arguments):
    """Invoke a Semantic Kernel function without blocking the event loop."""

    def run_invocation():
        # Each fan-out worker gets its own Kernel instance. Kernel invocation
        # state is not shared between the concurrently running agent threads.
        kernel = Kernel()
        kernel.add_plugin(FarmAgentsPlugin(), plugin_name="FarmAgents")
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
    historical_context="",
    soil_type="",
):
    """
    Coordinate farm agents using Semantic Kernel fan-out/fan-in.

    Historical farm observations are shared with the Soil
    Agent and Pest and Disease Retrieval Agent.
    """

    print("\nSEMANTIC KERNEL ORCHESTRATOR")
    print("============================")
    print("\nStarting parallel agent execution...")

    # 1. FAN-OUT: Run independent agents concurrently.

    weather_task = invoke_agent(
        "get_weather_advisory",
        latitude=latitude,
        longitude=longitude,
        crop_name=crop_name,
        growth_stage=growth_stage,
        soil_moisture=soil_moisture,
        symptoms=symptoms,
        historical_context=historical_context,
    )

    soil_task = invoke_agent(
        "get_soil_advisory",
        soil_moisture=soil_moisture,
        soil_ph=soil_ph,
        nitrogen=nitrogen,
        phosphorus=phosphorus,
        potassium=potassium,
        crop_name=crop_name,
        growth_stage=growth_stage,
        soil_type=soil_type,
        historical_context=historical_context
    )

    crop_task = invoke_agent(
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

    successful_statuses = {"completed", "success", "partial"}

    for agent_name, result in list(agent_results.items()):
        if isinstance(result, Exception) or not isinstance(result, dict):
            agent_results[agent_name] = {
                "agent": agent_name,
                "status": "failed",
                "execution_status": "failed",
                "quality_status": "unavailable",
                "error": "Agent output was unavailable.",
            }
            continue
        if result.get("error") or result.get("status") not in successful_statuses:
            result["status"] = "failed"
            result["execution_status"] = "failed"
            result.setdefault("quality_status", "unavailable")
        else:
            result.setdefault("execution_status", "completed")
            if result.get("quality_status") == "degraded":
                result["status"] = "partial"

    weather_result = agent_results["weather"]
    soil_result = agent_results["soil"]
    crop_result = agent_results["pest_disease"]

    print("Weather Agent:", weather_result.get("status"))
    print("Soil Agent:", soil_result.get("status"))
    print("Pest and Disease Agent:", crop_result.get("status"))

    print("\nFan-out completed. All results collected.")

    print(
        "Historical context supplied:",
        bool(historical_context)
    )

    # 3. FAN-IN: Extract the rainfall forecast.

    forecast = (weather_result.get("forecast") or {}).get(
        "daily_forecast", {}
    ) if weather_result.get("status") in successful_statuses else {}

    rainfall = forecast.get("precipitation_sum")
    precipitation_probabilities = forecast.get("precipitation_probability_max")

    expected_rainfall = aggregate_rainfall_if_complete(rainfall)
    recent_rainfall = (weather_result.get("forecast") or {}).get("recent_observed_rainfall")
    recent_rainfall_mm = recent_rainfall.get("precipitation_mm") if isinstance(recent_rainfall, dict) else None

    print(
        "Expected rainfall for next 3 days:",
        expected_rainfall,
        "mm"
    )

    # 4. Run Irrigation Planner after fan-in.

    print("\nStarting Irrigation Planner...")

    # The planner receives the submitted moisture directly, so one failed
    # specialist must not prevent a useful, clearly qualified plan from using
    # the remaining inputs. Missing forecast values are passed as unavailable.
    try:
        irrigation_result = await invoke_agent(
            "get_irrigation_advisory",
            soil_moisture=soil_moisture,
            expected_rainfall=expected_rainfall,
            crop_name=crop_name,
            growth_stage=growth_stage,
            soil_type=soil_type,
            precipitation_probability_max=precipitation_probabilities,
            recent_rainfall_mm=recent_rainfall_mm,
            recent_rainfall_date=recent_rainfall.get("date", "") if isinstance(recent_rainfall, dict) else "",
        )
    except Exception:
        irrigation_result = {"agent": "Irrigation Planner", "status": "failed", "execution_status": "failed", "quality_status": "unavailable", "error": "Irrigation output was unavailable."}

    if not isinstance(irrigation_result, dict) or irrigation_result.get("error") or irrigation_result.get("status") not in successful_statuses:
        irrigation_result = {"agent": "Irrigation Planner", "status": "failed", "execution_status": "failed", "quality_status": "unavailable", "error": "Irrigation output was unavailable."}
    else:
        irrigation_result.setdefault("execution_status", "completed")

    print("Irrigation Planner:", irrigation_result.get("status"))

    # 5. Return the unified result.

    agent_failures = [
        {"agent": name, "message": value.get("error") or "Agent output was unavailable."}
        for name, value in {**agent_results, "irrigation": irrigation_result}.items()
        if value.get("status") not in successful_statuses
    ]
    agent_degradations = [
        {
            "agent": name,
            "reason": value.get("quality_reason") or "partial_result",
            "message": "Agent execution completed, but validated analysis was limited.",
        }
        for name, value in {**agent_results, "irrigation": irrigation_result}.items()
        if value.get("status") in successful_statuses
        and (
            value.get("quality_status") == "degraded"
            or value.get("status") == "partial"
        )
    ]

    final_result = {
        "status": "partial" if agent_failures or agent_degradations else "completed",
        "coordination": "Semantic Kernel Fan-out/Fan-in",
        "historical_context_available": bool(historical_context),
        "agents": {
            "weather": weather_result,
            "soil": soil_result,
            "pest_disease": crop_result,
            "irrigation": irrigation_result
        },
        "agent_failures": agent_failures,
        "agent_degradations": agent_degradations,
        "expected_rainfall_next_3_days_mm": expected_rainfall
    }

    if final_result["agent_failures"] or final_result["agent_degradations"]:
        print("\nAgent coordination completed with failed or limited validated outputs.")
    else:
        print("\nAll agents completed successfully.")
    print("Unified farm advisory generated.")

    return final_result
