
import math

from tools.weather_tool import get_weather_forecast
from agents.evidence import normalize_passages, passage_is_relevant, public_source


def weather_agent(latitude: float, longitude: float, *, crop_name="", growth_stage="",
                  soil_moisture=None, symptoms=None, historical_context="",
                  knowledge_searcher=None, llm_json=None):
    """
    Weather Agent:
    Fetches forecast data and identifies basic weather risks.
    """

    forecast = get_weather_forecast(latitude, longitude)

    if forecast.get("error"):
        return {
            "agent": "Weather Agent",
            "status": "failed",
            "error": forecast["error"]
        }

    daily = forecast.get("daily_forecast", {})

    required_fields = [
        "time",
        "temperature_2m_max",
    ]

    if any(not isinstance(daily.get(field), list) for field in required_fields):
        return {
            "agent": "Weather Agent",
            "status": "failed",
            "error": "Required daily weather data is missing."
        }

    dates = daily["time"]
    maximum_temperatures = daily["temperature_2m_max"]

    if len(dates) != len(maximum_temperatures):
        return {
            "agent": "Weather Agent",
            "status": "failed",
            "error": "Weather forecast date and temperature arrays have inconsistent lengths."
        }

    raw_rainfall = daily.get("precipitation_sum")
    if isinstance(raw_rainfall, list) and len(raw_rainfall) == len(dates):
        rainfall_values = [
            value if (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
                and value >= 0
            ) else None
            for value in raw_rainfall
        ]
    else:
        rainfall_values = [None] * len(dates)
    daily["precipitation_sum"] = rainfall_values

    raw_probabilities = daily.get("precipitation_probability_max")
    if isinstance(raw_probabilities, list) and len(raw_probabilities) == len(dates):
        probabilities = [
            value if (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
                and 0 <= value <= 100
            ) else None
            for value in raw_probabilities
        ]
    else:
        probabilities = [None] * len(dates)
    daily["precipitation_probability_max"] = probabilities

    risks = []
    crop_stage = f"{crop_name or 'the crop'}{f' at {growth_stage}' if growth_stage else ''}"

    for index, date in enumerate(dates):

        max_temp = maximum_temperatures[index]
        rainfall = rainfall_values[index]

        if (
            isinstance(max_temp, (int, float))
            and not isinstance(max_temp, bool)
            and math.isfinite(max_temp)
            and max_temp >= 35
        ):
            risks.append({
                "date": date,
                "risk": "High temperature",
                "severity": "High",
                "priority": "high",
                "impact": f"Hot conditions may increase water demand and heat stress for {crop_stage}.",
                "recommended_action": f"Check {crop_name or 'crop'} root-zone moisture early and watch for wilting; irrigate only if field checks show it is needed.",
            })

        if isinstance(rainfall, (int, float)) and rainfall >= 20:
            risks.append({
                "date": date,
                "risk": "Heavy rainfall",
                    "severity": "High",
                    "priority": "high",
                    "impact": f"Heavy rain may waterlog soil around {crop_stage}, increase erosion or delay field work.",
                    "recommended_action": f"Keep drainage paths clear around {crop_name or 'the crop'} and reassess soil moisture after rain before irrigating.",
            })

        elif index < len(probabilities):

            rain_probability = probabilities[index]

            if (
                isinstance(rain_probability, (int, float))
                and rain_probability >= 60
            ):
                risks.append({
                    "date": date,
                    "risk": "Possible rainfall",
                    "severity": "Medium",
                    "priority": "medium",
                    "impact": f"Rain may change soil moisture needs for {crop_stage} and the timing of field work.",
                    "recommended_action": f"Check actual rainfall and {crop_name or 'crop'} root-zone moisture before changing the irrigation plan.",
                })

    # Interpret weather against this crop and stage. Candidate events are derived
    # only from provider values; Groq explains their likely farm impact/actions.
    sources = []
    llm_status = "unavailable"
    if knowledge_searcher is None:
        try:
            from rag.knowledge_base import search_knowledge
            knowledge_searcher = search_knowledge
        except Exception:
            knowledge_searcher = None
    if llm_json is None:
        try:
            from llm_service import ask_groq_json
            llm_json = ask_groq_json
        except Exception:
            llm_json = None

    passages = []
    if knowledge_searcher:
        for category in ("crop", "soil"):
            try:
                query = f"{crop_name} {growth_stage} weather heat rainfall field management crop water stress"
                found = normalize_passages(knowledge_searcher(
                    query,
                    crop=crop_name or None, category=category,
                ))
                passages.extend(p for p in found if passage_is_relevant(p, query, crop=crop_name or None, category=category))
            except Exception:
                continue
    unique_passages = list({p["evidence_id"]: p for p in passages}.values())
    sources = [public_source(p) for p in unique_passages]
    if llm_json and unique_passages:
        daily_context = [
            {"date": date,
             "max_temperature_c": maximum_temperatures[i],
             "min_temperature_c": (daily.get("temperature_2m_min", [None] * len(dates))[i]
                                   if isinstance(daily.get("temperature_2m_min"), list)
                                   and len(daily["temperature_2m_min"]) == len(dates) else None),
             "rain_mm": rainfall_values[i],
             "rain_probability_percent": probabilities[i]}
            for i, date in enumerate(dates)
        ]
        passage_context = "\n".join(
            f"[{p['evidence_id']}] {p['source']} / {p['section']}: {p['content']}"
            for p in unique_passages
        )
        try:
            result = llm_json(
                'You are a practical farm-weather adviser. Use only the supplied forecast values to identify weather events and the supplied agricultural guide passages to explain crop impact and actions. Match event dates and risk names to the supplied candidates; do not invent events. Tailor wording to the crop and stage. Return JSON: {"summary":"...","risks":[{"risk":"candidate risk name","date":"candidate date","impact":"...","recommended_action":"...","evidence_ids":["..."],"priority":"high|medium|low"}]}.',
                f"Crop: {crop_name or 'not recorded'}; growth stage: {growth_stage or 'not recorded'}; soil moisture: {soil_moisture if soil_moisture is not None else 'not recorded'}; reported symptoms: {symptoms or []}; recent farm history: {historical_context or 'none'}. Current conditions: {forecast.get('current_conditions') or 'not supplied'}. Seven-day forecast: {daily_context}. Candidate weather events: {risks}. Agricultural guides:\n{passage_context or 'No relevant agricultural guide was retrieved; use forecast facts only.'}",
            )
            if isinstance(result, dict):
                candidate_keys = {(risk["risk"].casefold(), risk.get("date")) for risk in risks}
                passage_by_id = {p["evidence_id"]: p for p in unique_passages}
                interpreted = []
                for item in result.get("risks", []) if isinstance(result.get("risks"), list) else []:
                    if not isinstance(item, dict):
                        continue
                    risk_name, date = item.get("risk"), item.get("date")
                    ids = item.get("evidence_ids", [])
                    cited = [passage_by_id[eid] for eid in ids if isinstance(ids, list) and eid in passage_by_id]
                    if not isinstance(risk_name, str) or (risk_name.casefold(), date) not in candidate_keys:
                        continue
                    if not isinstance(item.get("impact"), str) or not item["impact"].strip():
                        continue
                    if not isinstance(item.get("recommended_action"), str) or not item["recommended_action"].strip():
                        continue
                    # Weather facts come from the provider; guide references are
                    # attached only when the model cites IDs returned by RAG.
                    interpreted.append({
                        "risk": risk_name, "date": date,
                        "severity": next((r["severity"] for r in risks if r["risk"].casefold() == risk_name.casefold() and r.get("date") == date), "Medium"),
                        "priority": item.get("priority") if item.get("priority") in {"high", "medium", "low"} else "medium",
                        "impact": item["impact"].strip(),
                        "recommended_action": item["recommended_action"].strip(),
                        "sources": [public_source(p) for p in cited],
                    })
                if interpreted or not risks:
                    risks = interpreted
                    llm_status = "success"
                    summary = result.get("summary") if isinstance(result.get("summary"), str) else ""
                else:
                    summary = ""
            else:
                summary = ""
        except Exception:
            summary = ""
            llm_status = "provider_error"
    else:
        summary = ""

    # Keep safe, input-derived alerts if AI or RAG cannot interpret the forecast.
    return {
        "agent": "Weather Agent",
        "forecast": forecast,
        "identified_risks": risks,
        "weather_summary": summary,
        "crop_context": {"crop_name": crop_name, "growth_stage": growth_stage},
        "evidence_sources": sources,
        "llm_status": llm_status,
        "risk_interpretation_note": "Weather events are estimated from the forecast; check actual field conditions.",
        "status": "completed"
    }
