import re

from agents.evidence import (
    normalize_passages,
    passage_is_relevant,
    public_source,
    retrieved_passages_conflict,
    validate_excerpt_items,
    validate_recommendations,
)
from tools.soil_tool import get_soil_report


def soil_agent(
    moisture: float,
    ph: float,
    nitrogen: float,
    phosphorus: float,
    potassium: float,
    historical_context: str = "",
    *,
    crop_name: str = "",
    knowledge_searcher=None,
    llm_json=None,
):
    """Report measurements, preliminary rules, and source-linked excerpts."""
    if knowledge_searcher is None:
        from rag.knowledge_base import search_knowledge
        knowledge_searcher = search_knowledge
    if llm_json is None:
        from llm_service import ask_groq_json
        llm_json = ask_groq_json

    report = get_soil_report(moisture, ph, nitrogen, phosphorus, potassium)
    indicators = []
    if moisture < 30:
        indicators.append("Low soil moisture")
    if ph < 5.5:
        indicators.append("Soil may be too acidic")
    elif ph > 7.5:
        indicators.append("Soil may be too alkaline")

    query = (
        f"Soil moisture {moisture}, pH {ph}; crop {crop_name or 'unspecified'}. "
        "Evidence about interpreting soil measurements and soil management."
    )
    raw_results = knowledge_searcher(
        query,
        crop=crop_name or None,
        category="soil",
    )
    retrieved = normalize_passages(raw_results)
    relevant = [
        item for item in retrieved
        if passage_is_relevant(item, query, crop=crop_name or None, category="soil")
    ]
    retrieved_context = "\n\n".join(
        f"Evidence ID: {item['evidence_id']}\nSource: {item['source']}\n"
        f"Section: {item['section']}\nPassage:\n{item['content']}"
        for item in relevant
    )

    accepted_interpretations = []
    recommendations = []
    invalid_output = False
    conflicting = retrieved_passages_conflict(relevant)
    if relevant and not conflicting:
        system_prompt = """
You are an agricultural soil information assistant. Use only the supplied
retrieved passages. Return a JSON object with exactly these keys:
{"interpretations": [{"text": "verbatim passage excerpt", "evidence_id": "retrieved ID"}],
 "recommendations": [{"text": "verbatim passage excerpt", "evidence_id": "retrieved ID"}],
 "expert_review_required": true}
Every text value must be copied verbatim from its cited passage. Do not add
diagnoses, measurements, citations, or interpretations not stated there. Do not
interpret unitless nitrogen, phosphorus, or potassium measurements or prescribe
amendments from them. Use empty arrays when no passage directly supports an item.
"""
        user_prompt = f"""Crop context: {crop_name or 'not supplied'}
Current measurements: moisture={moisture}, pH={ph}.
Preliminary rule indicators (not diagnoses): {indicators}
Historical observations: {historical_context or 'None available.'}
Retrieved passages:
{retrieved_context}
Return only the specified JSON object."""
        try:
            model_result = llm_json(system_prompt, user_prompt)
        except Exception:
            model_result = None
        required = {"interpretations", "recommendations", "expert_review_required"}
        if (
            not isinstance(model_result, dict)
            or set(model_result) != required
            or not isinstance(model_result.get("expert_review_required"), bool)
        ):
            invalid_output = True
        else:
            accepted_interpretations, rejected_interpretations = validate_excerpt_items(
                model_result["interpretations"], relevant
            )
            recommendations, rejected_recommendations = validate_recommendations(
                model_result["recommendations"], relevant
            )
            invalid_output = rejected_interpretations or rejected_recommendations
    else:
        # Do not invoke a model when retrieval is absent, irrelevant, or conflicting.
        model_result = None

    nutrient_classification = re.compile(
        r"\b(?:nitrogen|phosphorus|potassium|NPK|nutrient(?:s)?)\b", re.I
    )
    unsupported_nutrient_finding = re.compile(
        r"\b(?:low|high|deficien\w*|excess\w*|adequate|inadequate|"
        r"sufficient|insufficient|suboptimal|optimal|optimum|balanced|imbalanced|unbalanced|"
        r"lacking|lack(?:s|ing)?|shortage|shortfall|not enough|too little|too much|"
        r"within (?:an? )?(?:acceptable|optimal|normal|target|recommended) range|"
        r"below (?:the )?(?:required|recommended|target|optimal)?\s*level|"
        r"above (?:the )?(?:required|recommended|target|optimal)?\s*level)\b", re.I
    )
    amendment_material = re.compile(
        r"\b(?:fertili[sz]\w*|urea|manure|compost|lime|soil amendments?|"
        r"nutrient amendments?|NPK blends?|top[- ]dress(?:ing)?)\b", re.I
    )
    nutrient_application = re.compile(
        r"\b(?:apply|application|dose|dosing|use|add|increase|boost|"
        r"supplement|recommend\w*)\b", re.I
    )
    accepted_interpretations = [
        item for item in accepted_interpretations
        if not (
            nutrient_classification.search(item["text"])
            and unsupported_nutrient_finding.search(item["text"])
        )
    ]
    recommendations = [
        item for item in recommendations
        if not (
            amendment_material.search(item["text"])
            or nutrient_classification.search(item["text"])
            and nutrient_application.search(item["text"])
        )
    ]
    sufficiently_supported = bool(accepted_interpretations or recommendations)
    insufficient = not relevant or conflicting or invalid_output or not sufficiently_supported

    if not relevant:
        summary = "Insufficient relevant retrieved evidence to support a soil interpretation or recommendation."
    elif conflicting:
        summary = "Retrieved soil passages conflict; expert review is required before interpretation."
    elif invalid_output or not sufficiently_supported:
        summary = "Retrieved evidence did not support a validated interpretation or recommendation."
    else:
        summary = "The listed statements are verbatim excerpts from the cited retrieved soil passages."

    return {
        "agent": "Soil Agent",
        "soil_report": report,
        "identified_risks": indicators,
        "preliminary_rule_indicators": indicators,
        "indicator_context": (
            "Moisture and pH indicators use fixed preliminary rules. Their interpretation "
            "depends on measurement method, crop, soil and local conditions; they are not diagnoses."
        ),
        "nutrient_interpretation_note": (
            "Nutrient measurements are preserved as submitted but are not interpreted because "
            "their units and soil-test method were not provided. Interpretation also requires "
            "crop requirements and applicable regional recommendations."
        ),
        "ai_identified_risks": [item["text"] for item in accepted_interpretations],
        "ai_risk_evidence": [
            {"text": item["text"], "evidence_status": item["evidence_status"], "sources": item["sources"]}
            for item in accepted_interpretations
        ],
        "recommendations": [item["text"] for item in recommendations],
        "recommendation_evidence": [
            {"text": item["text"], "evidence_status": item["evidence_status"], "sources": item["sources"]}
            for item in recommendations
        ],
        "soil_health_summary": summary,
        "evidence_status": "insufficient" if insufficient else "source_excerpt",
        "retrieval_conflict": conflicting,
        "expert_review_required": insufficient or bool(
            model_result and model_result.get("expert_review_required")
        ),
        "retrieved_sources": [public_source(item) for item in retrieved],
        "evidence_sources": [public_source(item) for item in relevant],
        "historical_context_used": bool(historical_context),
        "status": "completed",
    }
