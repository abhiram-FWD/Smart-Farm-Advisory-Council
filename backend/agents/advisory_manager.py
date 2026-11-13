
import asyncio
import logging

from agents.semantic_kernel_orchestrator import (
    run_semantic_kernel_orchestration
)

from memory.farm_history import format_farm_history

from memory.mongodb_memory import (
    save_farm_observation,
    get_farm_history,
    save_advisory
)


logger = logging.getLogger(__name__)


def unique_strings(items):
    """Remove duplicate strings while preserving their order."""

    result = []
    seen = set()

    for item in items:
        if not isinstance(item, str):
            continue

        cleaned = item.strip()

        if not cleaned:
            continue

        key = cleaned.casefold()

        if key not in seen:
            seen.add(key)
            result.append(cleaned)

    return result


def extract_sources(sources, category=None):
    """Keep source provenance objects intact; retain legacy string sources."""

    extracted = []

    for source in sources or []:

        if isinstance(source, str):
            if category is None:
                extracted.append(source)

        elif isinstance(source, dict):

            if category and source.get("category") != category:
                continue

            source_name = source.get("source")

            if isinstance(source_name, str):
                extracted.append(source)

    unique = []
    seen = set()
    for source in extracted:
        key = source.get("evidence_id", source.get("source")) if isinstance(source, dict) else source
        if key not in seen:
            seen.add(key)
            unique.append(source)
    return unique


def add_risk_alerts(alerts, risks, agent_name, sources=None, classification=None):
    """Add risk alerts while avoiding duplicate entries."""

    sources = sources or []

    for risk in risks or []:

        if isinstance(risk, dict):
            risk_name = risk.get("risk", "Unspecified risk")
            date = risk.get("date")
            severity = risk.get("severity", "unspecified")
            evidence_status = risk.get("evidence_status")
            risk_sources = risk.get("sources") if isinstance(risk.get("sources"), list) else sources

        elif isinstance(risk, str):
            risk_name = risk
            date = None
            severity = "unspecified"

        else:
            continue

        if not isinstance(risk, dict):
            evidence_status = None
            risk_sources = []
            source_refs = sources
        else:
            source_refs = risk_sources or sources

        risk_name = str(risk_name).strip()

        if not risk_name:
            continue

        existing = None

        for alert in alerts:
            if (
                alert["risk"].casefold() == risk_name.casefold()
                and alert.get("date") == date
            ):
                existing = alert
                break

        if existing:

            if agent_name not in existing["reported_by"]:
                existing["reported_by"].append(agent_name)

            existing["sources"] = _unique_source_names(existing["sources"] + source_refs)
            existing["evidence_sources"] = _unique_source_refs(
                existing.get("evidence_sources", []) + source_refs
            )
            if classification:
                existing["classification"] = classification
            if evidence_status:
                existing["evidence_status"] = evidence_status

        else:

            alerts.append({
                "risk": risk_name,
                "date": date,
                "severity": severity,
                "reported_by": [agent_name],
                "sources": _unique_source_names(source_refs),
                "evidence_sources": _unique_source_refs(source_refs),
            })
            if classification:
                alerts[-1]["classification"] = classification
            if evidence_status:
                alerts[-1]["evidence_status"] = evidence_status


def _unique_source_refs(sources):
    unique = []
    seen = set()
    for source in sources:
        key = source.get("evidence_id", source.get("source")) if isinstance(source, dict) else source
        if isinstance(key, str) and key and key not in seen:
            seen.add(key)
            unique.append(source)
    return unique


def _unique_source_names(sources):
    names = []
    for source in sources:
        name = source.get("source") if isinstance(source, dict) else source
        if isinstance(name, str) and name.strip() and name not in names:
            names.append(name)
    return names


def _risks_with_evidence(items, evidence_items):
    """Join additive evidence records to legacy string risk fields."""
    evidence_by_risk = {
        item.get("risk", item.get("text")): item
        for item in evidence_items or []
        if isinstance(item, dict)
    }
    return [
        {"risk": item, **{
            key: evidence_by_risk[item][key]
            for key in ("evidence_status", "sources")
            if key in evidence_by_risk.get(item, {})
        }}
        if isinstance(item, str) else item
        for item in items or []
    ]


def unique_actions(items):
    """Return the legacy string-list contract, deduplicated in order."""
    actions = []
    seen = set()
    for item in items:
        if isinstance(item, str):
            text = item.strip()
            key = text.casefold()
            value = text
        else:
            continue
        if text and key not in seen:
            seen.add(key)
            actions.append(value)
    return actions


def generate_farm_advisory(
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
    farm_id=None
):
    """
    Main Advisory Manager.

    Saves farm observations, retrieves previous farm history,
    coordinates agents and saves generated advisories
    using MongoDB persistent memory.
    """

    from uuid import uuid4

    if not farm_id:
        farm_id = str(uuid4())

    # 1. Prepare the current farm observation.

    observation = {
        "latitude": latitude,
        "longitude": longitude,
        "soil_moisture": soil_moisture,
        "soil_ph": soil_ph,
        "nitrogen": nitrogen,
        "phosphorus": phosphorus,
        "potassium": potassium,
        "crop_name": crop_name,
        "growth_stage": growth_stage,
        "symptoms": symptoms
    }

    # 2. Save current observation and retrieve farm history.

    try:

        observation_id = save_farm_observation(
            farm_id,
            observation
        )

        previous_history = get_farm_history(
            farm_id,
            limit=10
        )

    except Exception as error:
        logger.error("Farm data storage failed (exception_type=%s)", type(error).__name__)

        return {
            "project": "Smart Farm Advisory Council",
            "status": "failed",
            "error": "Farm data storage is temporarily unavailable."
        }

    # Exclude the current observation from historical records.

    previous_history = [
        record for record in previous_history
        if record.get("observation_id") != observation_id
    ]

    # 3. Format previous observations for the agents.

    historical_context = format_farm_history(previous_history)

    # 4. Execute Semantic Kernel orchestration.

    try:

        orchestration_result = asyncio.run(
            run_semantic_kernel_orchestration(
                latitude=latitude,
                longitude=longitude,
                soil_moisture=soil_moisture,
                soil_ph=soil_ph,
                nitrogen=nitrogen,
                phosphorus=phosphorus,
                potassium=potassium,
                crop_name=crop_name,
                growth_stage=growth_stage,
                symptoms=symptoms,
                historical_context=historical_context
            )
        )

    except Exception as error:
        logger.error("Farm advisory orchestration failed (exception_type=%s)", type(error).__name__)

        return {
            "project": "Smart Farm Advisory Council",
            "status": "failed",
            "error": "Farm advisory orchestration could not be completed.",
            "observation_saved": True
        }

    # 5. Validate orchestration result.

    if not isinstance(orchestration_result, dict):

        logger.error("Farm advisory orchestration returned an invalid result.")

        return {
            "project": "Smart Farm Advisory Council",
            "status": "failed",
            "error": "Invalid orchestration result."
        }

    if orchestration_result.get("status") != "completed":

        logger.error("Farm advisory orchestration returned a failure status.")

        return {
            "project": "Smart Farm Advisory Council",
            "status": "failed",
            "farm_id": farm_id,
            "error": "Farm advisory orchestration could not be completed."
        }

    agents = orchestration_result.get("agents", {})

    required_agents = [
        "weather",
        "soil",
        "pest_disease",
        "irrigation"
    ]

    for agent_name in required_agents:

        agent_result = agents.get(agent_name)

        if not isinstance(agent_result, dict):

            logger.error("Farm advisory agent returned an invalid result (agent=%s).", agent_name)

            return {
                "project": "Smart Farm Advisory Council",
                "status": "failed",
                "error": "Farm advisory orchestration could not be completed."
            }

        if agent_result.get("status") not in [
            "completed",
            "success"
        ]:

            logger.error("Farm advisory agent failed (agent=%s).", agent_name)

            return {
                "project": "Smart Farm Advisory Council",
                "status": "failed",
                "error": "The AI advisory service could not complete the analysis."
            }

    # 6. Extract individual agent results.

    weather_result = agents["weather"]
    soil_result = agents["soil"]
    crop_result = agents["pest_disease"]
    irrigation_result = agents["irrigation"]

    # 7. Extract sources.

    soil_sources = extract_sources(
        soil_result.get("retrieved_sources", [])
    )

    pest_sources = extract_sources(
        crop_result.get("retrieved_sources", []),
        category="pests"
    )

    disease_sources = extract_sources(
        crop_result.get("retrieved_sources", []),
        category="diseases"
    )

    # 8. Build unified risk alerts.

    risk_alerts = []

    add_risk_alerts(
        risk_alerts,
        weather_result.get("identified_risks", []),
        "Weather Agent"
    )

    add_risk_alerts(
        risk_alerts,
        soil_result.get("identified_risks", []),
        "Soil Agent",
        soil_sources,
        classification="preliminary_rule_indicator"
    )

    add_risk_alerts(
        risk_alerts,
        _risks_with_evidence(
            soil_result.get("ai_identified_risks", []),
            soil_result.get("ai_risk_evidence", []),
        ),
        "Soil Agent",
        classification="source_excerpt",
    )

    add_risk_alerts(
        risk_alerts,
        _risks_with_evidence(
            crop_result.get("possible_pest_risks", []),
            crop_result.get("pest_risk_evidence", []),
        ),
        "Pest and Disease Retrieval Agent",
        pest_sources
    )

    add_risk_alerts(
        risk_alerts,
        _risks_with_evidence(
            crop_result.get("possible_disease_risks", []),
            crop_result.get("disease_risk_evidence", []),
        ),
        "Pest and Disease Retrieval Agent",
        disease_sources
    )

    # 9. Generate weekly action list.

    weekly_actions = []

    weekly_actions.extend(
        soil_result.get("recommendations", [])
    )

    weekly_actions.extend(
        crop_result.get("recommendations", [])
    )

    weekly_actions = unique_actions(weekly_actions)
    weekly_action_evidence = []
    for evidence_field in ("recommendation_evidence",):
        for agent_result in (soil_result, crop_result):
            evidence_items = agent_result.get(evidence_field, [])
            if isinstance(evidence_items, list):
                weekly_action_evidence.extend(
                    item for item in evidence_items
                    if isinstance(item, dict) and item.get("text") in weekly_actions
                )

    # 10. Extract weather summary.

    forecast = (
        weather_result
        .get("forecast", {})
        .get("daily_forecast", {})
    )

    weather_summary = {
        "source": weather_result.get("forecast", {}).get("source"),
        "expected_rainfall_next_3_days_mm": (
            orchestration_result.get(
                "expected_rainfall_next_3_days_mm"
            )
        ),
        "daily_forecast": forecast
    }

    # 11. Construct final advisory.

    final_advisory = {
        "project": "Smart Farm Advisory Council",
        "status": "completed",

        "farm_id": farm_id,

        "coordination": orchestration_result.get(
            "coordination",
            "Semantic Kernel Fan-out/Fan-in"
        ),

        "agents": agents,

        "weekly_action_list": weekly_actions,
        "weekly_action_evidence": weekly_action_evidence,
        "weekly_action_list_note": (
            "Current agent recommendations; this is not a verified seven-day schedule."
        ),

        "risk_alerts": risk_alerts,

        "expert_review_required": any(
            bool(agents.get(agent_name, {}).get("expert_review_required"))
            or bool(agents.get(agent_name, {}).get("expert_inspection_required"))
            for agent_name in ("soil", "pest_disease")
        ),

        "watering_schedule": irrigation_result,

        "weather_summary": weather_summary,

        "historical_context_available": bool(historical_context)
    }

    # 12. Save final advisory in MongoDB.

    try:

        advisory_id = save_advisory(
            farm_id,
            final_advisory
        )

    except Exception as error:
        logger.error("Farm advisory persistence failed (exception_type=%s)", type(error).__name__)

        return {
            **final_advisory,
            "status": "completed_with_memory_warning",
            "memory_warning": "Advisory generated, but it could not be saved to farm history."
        }

    # 13. Return advisory and memory metadata.

    return {
        **final_advisory,

        "memory": {
            "storage": "MongoDB Atlas",
            "observation_saved": True,
            "advisory_saved": True,
            "observation_id": observation_id,
            "advisory_id": advisory_id,
            "previous_observations_count": len(previous_history)
        }
    }
