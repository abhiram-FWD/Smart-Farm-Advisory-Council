"""Practical irrigation plan from measured moisture, crop stage and rain."""
import math


def irrigation_agent(soil_moisture, expected_rainfall, crop_name, precipitation_probability_max=None,
                    growth_stage="", soil_type="", recent_rainfall_mm=None, recent_rainfall_date="",
                    knowledge_searcher=None, llm_json=None):
    valid_m = isinstance(soil_moisture, (int, float)) and not isinstance(soil_moisture, bool) and math.isfinite(soil_moisture)
    valid_r = isinstance(expected_rainfall, (int, float)) and not isinstance(expected_rainfall, bool) and math.isfinite(expected_rainfall) and expected_rainfall >= 0
    if not valid_m:
        action, reason = "Check field moisture", "A usable soil-moisture reading is missing. Check the root zone and local forecast before changing irrigation."
    elif soil_moisture < 30:
        if not valid_r:
            action, reason = "Check local forecast before deciding", "The moisture reading is below a preliminary 30% screen, but rainfall information is unavailable. Check the root zone and a reliable local forecast; irrigate only if field checks show the crop needs water."
        elif valid_r and expected_rainfall >= 5:
            action, reason = "Recheck before irrigating", f"Moisture is below a preliminary 30% screen, while {expected_rainfall:g} mm rain is forecast over three days. Check the root zone and actual rainfall before deciding."
        else:
            action, reason = "Consider irrigation", "The submitted moisture is below a preliminary 30% screen. Confirm it at root depth; if the soil is dry, provide a modest irrigation suited to the crop stage and local practice."
    elif soil_moisture > 80:
        action, reason = "Pause and check drainage", "The submitted moisture is high. Check for standing water and keep drainage open; avoid adding water until the root zone is assessed."
    elif valid_r and expected_rainfall >= 5:
        action, reason = "Consider postponing irrigation", f"Soil moisture is not in the preliminary low range and {expected_rainfall:g} mm is forecast over three days. Recheck after rain before irrigating."
    else:
        action, reason = "No immediate irrigation indicated", "Moisture is not in the preliminary low range. Check the root zone daily and adjust to crop stage, soil texture and local conditions."

    sources, llm_status = [], "not_configured"
    if knowledge_searcher is None:
        try:
            from rag.knowledge_base import search_knowledge
            knowledge_searcher = search_knowledge
        except Exception: pass
    if llm_json is None:
        try:
            from llm_service import ask_groq_json
            llm_json = ask_groq_json
        except Exception: pass
    if knowledge_searcher:
        try:
            from agents.evidence import claim_has_source_support, normalize_passages, public_source
            passages = normalize_passages(knowledge_searcher(f"{crop_name} {growth_stage} irrigation soil moisture rainfall scheduling", crop=crop_name or None, category="irrigation"))
            sources = [public_source(p) for p in passages]
            if passages and llm_json:
                context = "\n".join(f"[{p['evidence_id']}] {p['source']}: {p['content']}" for p in passages)
                try:
                    result = llm_json('Give one plain-language crop- and stage-aware irrigation action from the supplied context. Never invent rainfall or exact water quantity. Use the source guidance and submitted field observations. Return JSON {"action":"...","reason":"...","evidence_ids":["..."]}.', f"Crop {crop_name}; stage {growth_stage}; soil type {soil_type or 'unknown'}; measured moisture {soil_moisture}; forecast rain next 3 days {expected_rainfall}; recent observed rain {recent_rainfall_mm} on {recent_rainfall_date}. Preliminary action: {action}. Sources:\n{context}")
                    if isinstance(result, dict) and isinstance(result.get("action"), str) and isinstance(result.get("reason"), str):
                        ids = result.get("evidence_ids", [])
                        allowed = {p["evidence_id"] for p in passages}
                        cited = [p for p in passages if isinstance(ids, list) and p["evidence_id"] in ids]
                        if isinstance(ids, list) and any(i in allowed for i in ids) and cited and result["action"].strip() and claim_has_source_support(result["reason"], cited):
                            action, reason = result["action"].strip(), result["reason"].strip()
                            llm_status = "success"
                except Exception: llm_status = "provider_error"
        except Exception: pass
    prob = precipitation_probability_max if isinstance(precipitation_probability_max, list) else None
    note = "The 30% moisture screen is preliminary; interpret readings using the meter method, root depth, soil and crop stage. No water volume or rigid schedule is inferred."
    if valid_r and recent_rainfall_mm is not None:
        note += f" Provider-reported recent rainfall: {recent_rainfall_mm} mm ({recent_rainfall_date or 'date unavailable'})."
    factors = []
    if valid_m:
        moisture_context = "below the preliminary screen" if soil_moisture < 30 else "above the preliminary screen" if soil_moisture > 80 else "within the preliminary range"
        factors.append({"label": "Soil", "detail": f"Measured moisture is {soil_moisture:g}% ({moisture_context}); confirm at root depth."})
    else:
        factors.append({"label": "Soil", "detail": "No usable moisture reading; check the root zone before deciding."})
    factors.append({"label": "Forecast", "detail": f"{expected_rainfall:g} mm rain is forecast over three days; recheck after it falls." if valid_r else "Forecast rainfall is unavailable; check a local forecast."})
    if recent_rainfall_mm is not None:
        factors.append({"label": "Recent rain", "detail": f"The weather provider recorded {recent_rainfall_mm:g} mm on {recent_rainfall_date or 'an unrecorded date'}; compare with rain measured in the field."})
    if growth_stage:
        factors.append({"label": "Crop stage", "detail": f"Water needs can change at {growth_stage}; use local guidance for {crop_name or 'this crop'} at this stage."})
    factors.append({"label": "When to reconsider", "detail": "Check moisture again after rain, during hot weather and before the next watering."})
    return {
        "agent": "Irrigation Planner", "status": "completed", "soil_moisture": soil_moisture,
        "expected_rainfall_mm": expected_rainfall if valid_r else None,
        "forecast_precipitation_probability_max": prob,
        "context_inputs": {"crop": crop_name, "growth_stage": growth_stage or None, "soil_type": soil_type or None,
                           "recent_rainfall_mm": recent_rainfall_mm, "recent_rainfall_date": recent_rainfall_date or None},
        "recommended_action": action, "reason": reason, "decision_factors": factors, "guidance_type": "crop_contextual" if llm_status == "success" else "preliminary_rule_based",
        "schedule": _watering_check_schedule(soil_moisture, expected_rainfall if valid_r else None),
        "guidance_note": note, "decision_basis": {"type": "moisture_rainfall_crop_stage", "soil_moisture_threshold_percent": 30,
                          "forecast_rainfall_threshold_mm": 5, "crop_name": crop_name, "growth_stage": growth_stage,
                          "soil_type": soil_type, "quantity_prescribed": False},
        "evidence_sources": sources, "llm_status": llm_status, "status": "completed"
    }


def _watering_check_schedule(soil_moisture, expected_rainfall):
    """Give a short field-check cadence without inventing irrigation quantities."""
    valid = isinstance(soil_moisture, (int, float)) and not isinstance(soil_moisture, bool) and math.isfinite(soil_moisture)
    if not valid:
        first = "Today: measure moisture in the crop root zone and check the local forecast."
    elif soil_moisture < 30 and expected_rainfall is not None and expected_rainfall < 5:
        first = "Today: confirm the root zone is dry; if it is, irrigate to local crop guidance."
    elif expected_rainfall is not None and expected_rainfall >= 5:
        first = "Today: wait for the forecast rain and check how much reaches the field."
    elif soil_moisture > 80:
        first = "Today: pause irrigation and check for standing water or poor drainage."
    else:
        first = "Today: check root-zone moisture before watering."
    return [
        {"day": "Today", "action": first},
        {"day": "Days 2–3", "action": "Recheck soil moisture and actual rainfall; water only if crop and field checks show it is needed."},
        {"day": "Days 4–7", "action": "Keep checking before irrigation and adjust for crop stage, soil and updated local rain."},
    ]
