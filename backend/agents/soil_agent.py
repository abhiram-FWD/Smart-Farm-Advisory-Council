"""Crop-aware soil guidance grounded in local agricultural passages."""
from agents.evidence import claim_has_source_support, normalize_passages, passage_is_relevant, public_source, retrieved_passages_conflict
from tools.soil_tool import get_soil_report


def soil_agent(moisture, ph, nitrogen, phosphorus, potassium, historical_context="", *,
               crop_name="", growth_stage="", soil_type="", knowledge_searcher=None,
               llm_json=None):
    if knowledge_searcher is None:
        from rag.knowledge_base import search_knowledge
        knowledge_searcher = search_knowledge
    if llm_json is None:
        from llm_service import ask_groq_json
        llm_json = ask_groq_json

    report = get_soil_report(moisture, ph, nitrogen, phosphorus, potassium)
    query = f"{crop_name} {growth_stage} soil moisture pH nutrients soil testing crop impact corrective management"
    retrieval_error = False
    try:
        passages = normalize_passages(knowledge_searcher(query, crop=crop_name or None, category="soil"))
    except Exception:
        passages, retrieval_error = [], True
    relevant = [p for p in passages if passage_is_relevant(p, query, crop=crop_name or None, category="soil")]
    by_id = {p["evidence_id"]: p for p in relevant}
    source_conflict = retrieved_passages_conflict(relevant)

    indicators = []
    crop_context = f"{crop_name or 'the crop'}{f' at {growth_stage}' if growth_stage else ''}"
    if isinstance(moisture, (int, float)) and moisture < 30:
        indicators.append({"risk": "Low soil moisture",
                           "impact": f"Below a preliminary 30% screen. Low moisture can limit water uptake and stress {crop_context}.",
                           "recommended_action": f"Check moisture around {crop_context}'s roots; irrigate only if the root zone is dry and useful rain is not expected.",
                           "priority": "high", "classification": "preliminary_rule_indicator"})
    elif isinstance(moisture, (int, float)) and moisture > 80:
        indicators.append({"risk": "Soil moisture is high on the submitted scale.",
                           "impact": f"If this reflects saturated field soil, {crop_context} roots may have less air and waterlogging risk can rise.",
                           "recommended_action": "Pause irrigation and check drainage and standing water before adding more water.",
                           "priority": "medium", "classification": "preliminary_rule_indicator"})
    if isinstance(ph, (int, float)) and ph < 5.5:
        indicators.append({"risk": "Soil may be too acidic", "impact": f"Preliminary pH screen. Acidity can affect nutrient availability for {crop_context}.", "recommended_action": f"Confirm pH with a soil test and get a local amendment recommendation for {crop_name or 'this crop'} before applying lime or other products.", "priority": "medium", "classification": "preliminary_rule_indicator"})
    elif isinstance(ph, (int, float)) and ph > 7.5:
        indicators.append({"risk": "Soil may be too alkaline", "impact": f"Preliminary pH screen. Alkalinity can affect nutrient availability for {crop_context}.", "recommended_action": f"Confirm pH with a soil test and ask a local adviser which amendment, if any, suits {crop_name or 'this crop'} and the soil.", "priority": "medium", "classification": "preliminary_rule_indicator"})

    nutrient_note = ("N, P and K values are recorded as supplied. Their units, extraction method and regional crop targets are missing, "
                     "so no nutrient deficiency or excess can be concluded. Use a soil laboratory report before selecting fertilizer.")
    fallback = []
    if indicators:
        fallback.append({"text": f"Recheck the reading around {crop_context} using the same method and compare it with local crop guidance and field conditions.", "evidence_status": "preliminary_rule_guidance", "sources": []})
    if any("acidic" in item["risk"].lower() or "alkaline" in item["risk"].lower() for item in indicators):
        fallback.append({"text": "Confirm pH with a reliable soil test and ask the local extension service which amendment, if any, suits this crop and soil; do not apply lime or acidifying products from this reading alone.", "evidence_status": "preliminary_rule_guidance", "sources": [public_source(p) for p in relevant[:1]]})
    fallback.append({"text": "Request a laboratory soil test that reports available N, P and K with units and test method, then match recommendations to the crop, growth stage and regional guidance.", "evidence_status": "safe_rule_based_guidance", "sources": [public_source(p) for p in relevant[:1]]})

    narrative, recommendations, llm_status = [], [], "unavailable"
    if relevant and not source_conflict:
        context = "\n".join(f"[{p['evidence_id']}] {p['source']} / {p['section']}: {p['content']}" for p in relevant)
        try:
            result = llm_json(
                'You are a practical agricultural soil adviser. Give concise plain-language interpretation and actions for the crop. Do not claim N/P/K deficiency from numbers without units, soil-test method and regional reference ranges. Treat moisture and pH rules as preliminary. Cite each item only with evidence IDs supplied. Return JSON: {"findings":[{"text":"...","evidence_ids":["..."]}],"recommendations":[{"text":"...","evidence_ids":["..."]}]}',
                f"Crop: {crop_name}; stage: {growth_stage}; soil: {soil_type or 'unknown'}. Measurements: moisture {moisture}%, pH {ph}, N {nitrogen}, P {phosphorus}, K {potassium}. Prior farm context: {historical_context or 'none'}.\nSources:\n{context}")
            if isinstance(result, dict):
                def accept(items):
                    accepted = []
                    if not isinstance(items, list): return accepted
                    for item in items:
                        if not isinstance(item, dict) or not isinstance(item.get("text"), str): continue
                        ids = item.get("evidence_ids", [])
                        refs = [by_id[x] for x in ids if isinstance(ids, list) and x in by_id]
                        # Disallow nutrient diagnoses and fertilizer prescriptions absent a usable lab report.
                        text = item["text"]
                        low = text.lower()
                        if any(term in low for term in ("nitrogen deficiency", "phosphorus deficiency", "potassium deficiency", "low nitrogen", "low phosphorus", "low potassium", "apply fertilizer", "apply urea")):
                            continue
                        if not refs or not claim_has_source_support(text, refs): continue
                        accepted.append({"text": text.strip(), "evidence_status": "source_supported_interpretation" if refs else "contextual_guidance", "sources": [public_source(p) for p in refs]})
                    return accepted
                narrative, recommendations = accept(result.get("findings")), accept(result.get("recommendations"))
                llm_status = "success"
        except Exception:
            llm_status = "provider_error"
    if not recommendations:
        recommendations = fallback
    if indicators and not narrative:
        narrative = [{"text": f"{i['risk']} {i['impact']}", "evidence_status": "preliminary_rule_indicator", "sources": []} for i in indicators]
    return {
        "agent": "Soil Agent", "status": "completed", "execution_status": "completed",
        "soil_report": report, "assessment_context": {"crop_name": crop_name, "growth_stage": growth_stage, "soil_type": soil_type, "nutrients_interpreted": False},
        "identified_risks": [item["risk"] for item in indicators],
        "preliminary_rule_indicators": [item["risk"] for item in indicators],
        "rule_indicator_details": indicators,
        "ai_identified_risks": [x["text"] for x in narrative], "ai_risk_evidence": narrative,
        "recommendations": [x["text"] for x in recommendations], "recommendation_evidence": recommendations,
        "soil_health_summary": " ".join(x["text"] for x in narrative) or "No clear moisture or pH screening flag was found. N, P and K still need a test report with units and method.",
        "nutrient_interpretation_note": nutrient_note, "indicator_context": "Moisture and pH flags are preliminary screening indicators; confirm the measurement method and local crop guidance.",
        "evidence_status": "conflicting_sources" if source_conflict else "source_supported" if relevant else "rule_based_fallback", "quality_status": "degraded" if source_conflict else "validated" if relevant and llm_status == "success" else "degraded",
        "quality_reason": "conflicting_sources" if source_conflict else None if relevant and llm_status == "success" else "rule_based_fallback", "llm_status": llm_status,
        "retrieval_status": "unavailable" if retrieval_error else "available" if relevant else "no_relevant_sources",
        "retrieved_sources": [public_source(p) for p in passages], "evidence_sources": [public_source(p) for p in relevant],
        "next_steps": ["Record the units, test method and sampling depth with each soil result.", "Use a local soil laboratory or extension service to turn N/P/K results into crop-specific rates."],
        "expert_review_required": bool(indicators) or source_conflict, "retrieval_conflict": source_conflict, "historical_context_used": bool(historical_context),
    }
