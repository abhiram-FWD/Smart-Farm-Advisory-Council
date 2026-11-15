
import asyncio
import logging
import json

from agents.semantic_kernel_orchestrator import (
    run_semantic_kernel_orchestration
)

from memory.farm_history import format_farm_history

from memory.mongodb_memory import (
    save_farm_observation,
    get_farm_history,
    count_farm_observations,
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
            impact = risk.get("impact")
            priority = risk.get("priority")
            recommended_action = risk.get("recommended_action")
            symptom_details = {key: risk.get(key) for key in ("why_relevant", "reported_symptoms", "symptoms_to_check", "inspection_step") if risk.get(key)}

        elif isinstance(risk, str):
            risk_name = risk
            date = None
            severity = "unspecified"

        else:
            continue

        if not isinstance(risk, dict):
            evidence_status = None
            risk_sources = []
            impact = None
            priority = None
            recommended_action = None
            symptom_details = {}
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
            if impact:
                existing["impact"] = impact
            if priority:
                existing["priority"] = priority
            if recommended_action:
                existing["recommended_action"] = recommended_action
            existing.update(symptom_details)

        else:

            alerts.append({
                "risk": risk_name,
                "date": date,
                "severity": severity,
                "reported_by": [agent_name],
                "sources": _unique_source_names(source_refs),
                "evidence_sources": _unique_source_refs(source_refs),
            })
            if impact:
                alerts[-1]["impact"] = impact
            if priority:
                alerts[-1]["priority"] = priority
            if recommended_action:
                alerts[-1]["recommended_action"] = recommended_action
            alerts[-1].update(symptom_details)
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


def _risks_with_evidence(items, evidence_items, details=None):
    """Join additive evidence records to legacy string risk fields."""
    evidence_by_risk = {
        item.get("risk", item.get("text")): item
        for item in evidence_items or []
        if isinstance(item, dict)
    }
    details_by_name = {}
    for item in details or []:
        if isinstance(item, dict) and item.get("name"):
            details_by_name[f"Possible {item['name']}".casefold()] = item
    return [
        {"risk": item, **{
            key: evidence_by_risk[item][key]
            for key in ("evidence_status", "sources")
            if key in evidence_by_risk.get(item, {})
        }, **({
            "impact": details_by_name[item.casefold()].get("impact"),
            "priority": details_by_name[item.casefold()].get("priority", "medium"),
            "why_relevant": details_by_name[item.casefold()].get("why_relevant"),
            "reported_symptoms": details_by_name[item.casefold()].get("reported_symptoms", []),
            "symptoms_to_check": details_by_name[item.casefold()].get("symptoms_to_check", []),
            "inspection_step": details_by_name[item.casefold()].get("inspection_step"),
            "recommended_action": "Inspect the crop for the listed signs and monitor whether affected plants or field area increase.",
        } if item.casefold() in details_by_name else {})}
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


def _evidence_supported_positive_findings(agents):
    """Only retain explicitly reported positives with attached source evidence."""
    findings = []
    for agent_name, agent in agents.items():
        if not isinstance(agent, dict):
            continue
        evidence = agent.get("positive_finding_evidence", [])
        evidence_by_text = {
            item.get("text"): item for item in evidence
            if isinstance(item, dict) and item.get("text") and item.get("sources")
        }
        for item in agent.get("positive_findings", []):
            text = item.get("text") if isinstance(item, dict) else item
            if isinstance(text, str) and text in evidence_by_text:
                findings.append({"text": text, "reported_by": agent_name, **evidence_by_text[text]})
    return findings


def build_weekly_action_plan(observation, agents, *, llm_json=None):
    """Use Groq to prioritize specialist advice, with safe input-based fallback."""
    try:
        if llm_json is None:
            from llm_service import ask_groq_json
            llm_json = ask_groq_json
    except Exception:
        llm_json = None

    soil = agents.get("soil", {})
    crop = agents.get("pest_disease", {})
    weather = agents.get("weather", {})
    irrigation = agents.get("irrigation", {})
    candidates = []
    known_sources = {}

    def add_candidate(day, action, agent, sources=None, priority="medium"):
        if not isinstance(action, str) or not action.strip():
            return
        source_list = sources if isinstance(sources, list) else []
        for source in source_list:
            if isinstance(source, dict) and isinstance(source.get("evidence_id"), str):
                known_sources[source["evidence_id"]] = source
        candidates.append({"day": day, "action": action.strip(), "agent": agent,
                           "priority": priority, "sources": source_list})

    for item in soil.get("recommendation_evidence", []):
        if isinstance(item, dict):
            add_candidate("Days 1-2", item.get("text"), "Soil Agent", item.get("sources"), "medium")
    for item in crop.get("recommendation_evidence", []):
        if isinstance(item, dict):
            add_candidate("Days 1-2", item.get("text"), "Crop Health Agent", item.get("sources"), "medium")
    for risk in weather.get("identified_risks", []):
        if isinstance(risk, dict):
            add_candidate("Today", risk.get("recommended_action"), "Weather Agent", risk.get("sources"), risk.get("priority", "high"))
    for risk in soil.get("rule_indicator_details", []):
        if isinstance(risk, dict):
            add_candidate("Today", risk.get("recommended_action") or risk.get("action"), "Soil Agent", risk.get("sources"), risk.get("priority", "medium"))
    for item in irrigation.get("schedule", []):
        if isinstance(item, dict):
            add_candidate(item.get("day", "Today"), item.get("action"), "Irrigation Planner", irrigation.get("evidence_sources", []), "high" if item.get("day") == "Today" else "medium")
    add_candidate("Today", irrigation.get("recommended_action"), "Irrigation Planner", irrigation.get("evidence_sources", []), "high")
    for item in candidates:
        for source in item["sources"]:
            if isinstance(source, dict) and isinstance(source.get("evidence_id"), str):
                known_sources[source["evidence_id"]] = source

    context = {
        "farm": {key: observation.get(key) for key in (
            "crop_name", "growth_stage", "soil_moisture", "soil_ph", "nitrogen",
            "phosphorus", "potassium", "soil_type", "symptoms")},
        "weather_summary": weather.get("weather_summary"),
        "weather_risks": weather.get("identified_risks", []),
        "soil_findings": soil.get("rule_indicator_details", []),
        "crop_findings": crop.get("risk_details", []),
        "candidate_actions": [{key: item[key] for key in ("day", "action", "agent", "priority")} for item in candidates],
        "source_ids": list(known_sources),
    }
    if llm_json and candidates:
        try:
            result = llm_json(
                'You are the Advisory Manager for a farm. Build a concise, prioritized seven-day action plan from the supplied farm readings, specialist findings, and candidate actions. Do not add diagnoses, measurements, chemicals, or actions unsupported by the candidates. Use only source IDs supplied; IDs are references, not quotations. Return JSON {"actions":[{"day":"Today|Days 1-2|Days 2-3|Days 4-7","action":"...","priority":"high|medium|low","agent":"...","source_ids":["..."]}]}. Order most urgent first and avoid duplicate actions.',
                json.dumps(context, ensure_ascii=False, default=str),
            )
            plan = []
            allowed_days = {"today": "Today", "days 1-2": "Days 1–2", "days 2-3": "Days 2–3", "days 4-7": "Days 4–7"}
            if isinstance(result, dict) and isinstance(result.get("actions"), list):
                for item in result["actions"]:
                    if not isinstance(item, dict):
                        continue
                    action = item.get("action")
                    day_key = str(item.get("day", "")).replace("–", "-").casefold()
                    ids = item.get("source_ids", [])
                    if not isinstance(action, str) or not action.strip() or len(action) > 400 or day_key not in allowed_days:
                        continue
                    source_refs = [known_sources[source_id] for source_id in ids if isinstance(ids, list) and source_id in known_sources]
                    candidate = next((c for c in candidates if c["action"].casefold() == action.strip().casefold()), None)
                    if not source_refs and candidate is None:
                        continue
                    plan.append({
                        "day": allowed_days[day_key], "action": action.strip(),
                        "priority": item.get("priority") if item.get("priority") in {"high", "medium", "low"} else (candidate or {}).get("priority", "medium"),
                        "agent": item.get("agent") if isinstance(item.get("agent"), str) else (candidate or {}).get("agent", "Advisory Manager"),
                        "sources": source_refs or (candidate or {}).get("sources", []),
                    })
                    if len(plan) == 7:
                        break
            if plan:
                return _complete_week_horizon(_dedupe_plan(plan), observation), "groq"
        except Exception:
            logger.info("Advisory plan generation fell back to specialist actions.")

    # Fallback uses this farm's specialist actions and measured context first.
    plan = []
    for item in candidates:
        day_key = item["day"].replace("–", "-").casefold()
        day = {"days 1-2": "Days 1–2", "days 2-3": "Days 2–3", "days 4-7": "Days 4–7"}.get(day_key, item["day"])
        plan.append({**item, "day": day})
    if not any(item["day"] == "Days 2–3" for item in plan):
        plan.append({"day": "Days 2–3", "action": "Check the forecast and soil moisture again after rain or hot weather.", "priority": "medium", "agent": "Weather Agent", "sources": []})
    if not any(item["day"] == "Days 4–7" for item in plan):
        plan.append({"day": "Days 4–7", "action": f"Review {observation.get('crop_name') or 'crop'} symptoms and field notes, then recheck soil before changing inputs.", "priority": "medium", "agent": "Advisory Manager", "sources": []})
    return _complete_week_horizon(_dedupe_plan(plan)[:7], observation), "rule_based_fallback"


def _dedupe_plan(plan):
    import re

    unique = []
    for item in plan:
        words = {word for word in re.findall(r"[a-z0-9]+", item.get("action", "").casefold()) if len(word) > 2}
        duplicate = None
        for existing in unique:
            other = {word for word in re.findall(r"[a-z0-9]+", existing.get("action", "").casefold()) if len(word) > 2}
            overlap = len(words & other) / max(1, len(words | other))
            if item.get("day") == existing.get("day") and (item.get("action", "").casefold() == existing.get("action", "").casefold() or overlap >= 0.72):
                duplicate = existing
                break
        if duplicate is None:
            unique.append(item)
        else:
            existing_sources = duplicate.get("sources", [])
            for source in item.get("sources", []):
                source_key = source.get("evidence_id", source.get("source")) if isinstance(source, dict) else source
                if not any((old.get("evidence_id", old.get("source")) if isinstance(old, dict) else old) == source_key for old in existing_sources):
                    existing_sources.append(source)
            duplicate["sources"] = existing_sources
            if item.get("priority") == "high":
                duplicate["priority"] = "high"
            agents = list(dict.fromkeys([*str(duplicate.get("agent", "")).split(" / "), *str(item.get("agent", "")).split(" / ")]))
            duplicate["agent"] = " / ".join(agent for agent in agents if agent)
    return unique


def _complete_week_horizon(plan, observation):
    """Ensure the plan includes near-term follow-up and late-week review."""
    crop = observation.get("crop_name") or "crop"
    moisture = observation.get("soil_moisture")
    if not any(item.get("day") == "Days 2–3" for item in plan):
        action = f"Recheck {crop} root-zone moisture and symptoms after any forecast rain."
        if isinstance(moisture, (int, float)) and moisture < 30:
            action = f"Recheck {crop} root-zone moisture within 2–3 days and adjust watering to actual rain and field conditions."
        plan.append({"day": "Days 2–3", "action": action, "priority": "medium", "agent": "Advisory Manager", "sources": []})
    if not any(item.get("day") == "Days 4–7" for item in plan):
        plan.append({
            "day": "Days 4–7",
            "action": f"Review {crop} growth and recorded symptoms; repeat soil checks before changing fertilizer or irrigation.",
            "priority": "medium", "agent": "Advisory Manager", "sources": [],
        })
    return _dedupe_plan(plan)[:7]


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
    farm_id=None,
    soil_type="",
    llm_json=None,
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

    assessment_id = str(uuid4())
    observation = {
        "assessment_id": assessment_id,
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
    if isinstance(soil_type, str) and soil_type.strip():
        observation["soil_type"] = soil_type.strip()

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

    try:
        # The context sent to agents is intentionally capped, but the count
        # shown to the farmer should represent all earlier observations.
        previous_observations_count = max(0, count_farm_observations(farm_id) - 1)
    except Exception as error:
        logger.warning(
            "Farm observation count unavailable (exception_type=%s)",
            type(error).__name__,
        )
        previous_observations_count = None

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
                historical_context=historical_context,
                soil_type=soil_type
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

    if orchestration_result.get("status") not in {"completed", "partial"}:

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

        if agent_result.get("status") == "failed":
            logger.warning("Farm advisory agent output unavailable (agent=%s).", agent_name)
        elif agent_result.get("status") == "partial":
            logger.warning("Farm advisory agent returned limited validated output (agent=%s).", agent_name)

    # 6. Extract individual agent results.

    weather_result = agents.get("weather", {})
    soil_result = agents.get("soil", {})
    crop_result = agents.get("pest_disease", {})
    irrigation_result = agents.get("irrigation", {})

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
        soil_result.get("rule_indicator_details", soil_result.get("identified_risks", [])),
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
            crop_result.get("risk_details", []),
        ),
        "Pest and Disease Retrieval Agent",
        pest_sources
    )

    add_risk_alerts(
        risk_alerts,
        _risks_with_evidence(
            crop_result.get("possible_disease_risks", []),
            crop_result.get("disease_risk_evidence", []),
            crop_result.get("risk_details", []),
        ),
        "Pest and Disease Retrieval Agent",
        disease_sources
    )

    priority_rank = {"high": 0, "severe": 0, "medium": 1, "moderate": 1, "low": 2, "unspecified": 3}
    risk_alerts.sort(key=lambda item: priority_rank.get(
        str(item.get("priority") or item.get("severity") or "unspecified").casefold(), 3
    ))

    # 9. Generate weekly action list.

    weekly_actions = []

    weekly_actions.extend(
        soil_result.get("recommendations", [])
    )

    weekly_actions.extend(
        crop_result.get("recommendations", [])
    )

    irrigation_action = irrigation_result.get("recommended_action")
    if (
        irrigation_result.get("status") in ("completed", "success")
        and isinstance(irrigation_action, str)
        and irrigation_action.strip()
        and irrigation_action != "Irrigation guidance unavailable"
    ):
        weekly_actions.append(irrigation_action.strip())

    weekly_actions = unique_actions(weekly_actions)
    weekly_action_evidence = []
    for evidence_field in ("recommendation_evidence",):
        for agent_result in (soil_result, crop_result, irrigation_result):
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
        "fetched_at": weather_result.get("forecast", {}).get("fetched_at"),
        "location": weather_result.get("forecast", {}).get("location"),
        "recent_observed_rainfall": weather_result.get("forecast", {}).get("recent_observed_rainfall"),
        "expected_rainfall_next_3_days_mm": (
            orchestration_result.get(
                "expected_rainfall_next_3_days_mm"
            )
        ),
        "daily_forecast": forecast
    }

    # Prioritize specialist recommendations into one farm-specific plan.
    weekly_action_plan, plan_generation = build_weekly_action_plan(observation, agents, llm_json=llm_json)
    forecast_dates = forecast.get("time", []) if isinstance(forecast, dict) else []
    if not forecast_dates:
        weather_result.setdefault("forecast_note", "A current forecast was unavailable; check a local weather service before time-sensitive field work.")

    # 11. Construct final advisory.

    final_advisory = {
        "project": "Smart Farm Advisory Council",
        "status": "partial" if orchestration_result.get("status") == "partial" else "completed",

        "farm_id": farm_id,
        "assessment_id": assessment_id,
        "assessment_snapshot": dict(observation),
        "overall_summary": (
            f"Assessment recorded for {crop_name}; farmer-reported growth stage: {growth_stage}. "
            f"Measured soil moisture: {soil_moisture}%; measured pH: {soil_ph}. "
            f"The agents reported {len(risk_alerts)} risk alert(s)."
        ),

        "coordination": orchestration_result.get(
            "coordination",
            "Semantic Kernel Fan-out/Fan-in"
        ),

        "agents": agents,
        "agent_failures": orchestration_result.get("agent_failures", []),
        "agent_degradations": orchestration_result.get("agent_degradations", []),
        "positive_findings": _evidence_supported_positive_findings(agents),

        "weekly_action_list": weekly_actions,
        "weekly_action_plan": weekly_action_plan,
        "weekly_action_plan_generation": plan_generation,
        "weekly_action_evidence": weekly_action_evidence,
        "weekly_action_list_note": (
            "A practical seven-day sequence based on current agent findings; recheck local field and weather conditions as the week progresses."
        ),

        "risk_alerts": risk_alerts,

        "expert_review_required": any(
            bool(agents.get(agent_name, {}).get("expert_review_required"))
            or bool(agents.get(agent_name, {}).get("expert_inspection_required"))
            for agent_name in ("soil", "pest_disease")
        ),

        "watering_schedule": irrigation_result,

        "weather_summary": weather_summary,
        "historical_context_available": bool(historical_context),
        "history_context": {
            "previous_observations_count": previous_observations_count,
            "observations_supplied_to_agents": len(previous_history),
        },
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
            "previous_observations_count": previous_observations_count,
            "historical_context_observations_count": len(previous_history),
        }
    }
