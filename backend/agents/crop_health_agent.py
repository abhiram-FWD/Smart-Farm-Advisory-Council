"""Evidence-linked crop health interpretation with fail-safe validation."""

import re

from agents.evidence import (
    exact_source_text,
    find_passage,
    normalize_passages,
    passage_is_relevant,
    public_source,
    retrieved_passages_conflict,
    supports_symptom_risk_relationship,
    validate_excerpt_items,
    validate_recommendations,
)
from tools.crop_tool import get_crop_report


def pest_disease_retrieval_agent(
    crop_name,
    growth_stage,
    symptoms,
    historical_context="",
    *,
    knowledge_searcher=None,
    llm_json=None,
):
    if knowledge_searcher is None:
        from rag.knowledge_base import search_knowledge
        knowledge_searcher = search_knowledge
    if llm_json is None:
        from llm_service import ask_groq_json
        llm_json = ask_groq_json

    crop_report = get_crop_report(crop_name, growth_stage, symptoms)
    pest_results = knowledge_searcher(
        query=f"{crop_name} {growth_stage} pest {' '.join(symptoms)}",
        n_results=3, crop=crop_name, category="pests",
    )
    disease_results = knowledge_searcher(
        query=f"{crop_name} {growth_stage} disease {' '.join(symptoms)}",
        n_results=3, crop=crop_name, category="diseases",
    )
    retrieved = normalize_passages(
        (pest_results if isinstance(pest_results, list) else [])
        + (disease_results if isinstance(disease_results, list) else [])
    )
    relevant = [
        item for item in retrieved
        if passage_is_relevant(
            item,
            " ".join(symptoms),
            crop=crop_name,
            category=item.get("category"),
        )
    ]
    conflict = retrieved_passages_conflict(relevant)
    accepted_pests = []
    accepted_diseases = []
    recommendations = []
    invalid_output = False

    if relevant and not conflict:
        evidence_context = "\n\n".join(
            f"Evidence ID: {item['evidence_id']}\nCategory: {item['category']}\n"
            f"Source: {item['source']}\nSection: {item['section']}\n{item['content']}"
            for item in relevant
        )
        system_prompt = """
You are a crop-health evidence assistant. Never confirm a pest or disease
diagnosis. Return JSON with exactly these keys:
{"possible_pest_risks": [{"name": "name copied exactly from passage", "evidence_id": "retrieved ID"}],
 "possible_disease_risks": [{"name": "name copied exactly from passage", "evidence_id": "retrieved ID"}],
 "recommendations": [{"text": "verbatim passage excerpt", "evidence_id": "retrieved ID"}],
 "expert_inspection_required": true}
Names must occur verbatim in a cited passage in the matching category. Each
recommendation must be copied verbatim from its cited passage. Use empty arrays
when unsupported. Do not invent source names, citations, diagnoses, treatment,
pesticide, fungicide, chemical or dosage advice. Symptoms alone never confirm a
pest or disease. Set expert inspection required when evidence is incomplete.
"""
        user_prompt = f"""Crop: {crop_name}; growth stage: {growth_stage}
Current symptoms: {symptoms}
Historical context (not current symptoms): {historical_context or 'None available.'}
Retrieved evidence:
{evidence_context}
Return only the required JSON."""
        try:
            model_result = llm_json(system_prompt, user_prompt)
        except Exception:
            model_result = None
        required = {
            "possible_pest_risks", "possible_disease_risks",
            "recommendations", "expert_inspection_required",
        }
        if (
            not isinstance(model_result, dict)
            or set(model_result) != required
            or not isinstance(model_result.get("expert_inspection_required"), bool)
        ):
            invalid_output = True
        else:
            accepted_pests, bad_pests = _validate_named_risks(
                model_result["possible_pest_risks"], relevant, "pests", crop_name, symptoms
            )
            accepted_diseases, bad_diseases = _validate_named_risks(
                model_result["possible_disease_risks"], relevant, "diseases", crop_name, symptoms
            )
            recommendations, bad_recommendations = validate_recommendations(
                model_result["recommendations"], relevant
            )
            invalid_output = bad_pests or bad_diseases or bad_recommendations
    else:
        model_result = None

    # A retrieved excerpt is not sufficient validation for recommending a
    # chemical or product treatment. Withhold those actions and require review.
    chemical_recommendation_withheld = any(
        _is_chemical_treatment_recommendation(item["text"])
        for item in recommendations
    )
    recommendations = [
        item for item in recommendations
        if not _is_chemical_treatment_recommendation(item["text"])
    ]
    insufficient = (
        not relevant
        or conflict
        or invalid_output
        or not (accepted_pests or accepted_diseases or recommendations)
    )
    if not relevant:
        summary = "Insufficient relevant crop-health evidence was retrieved; no pest or disease finding is supported."
    elif conflict:
        summary = "Retrieved crop-health passages conflict; expert inspection is required before interpretation."
    elif invalid_output:
        summary = "The model response did not pass source and schema validation; no unsupported claims are shown."
    elif not accepted_pests and not accepted_diseases:
        summary = "No pest or disease risk was supported by the retrieved passages."
    else:
        summary = "Listed items are possible risks linked to retrieved source passages; they are not diagnoses."
    if chemical_recommendation_withheld:
        summary += " A potentially chemical treatment recommendation was withheld for expert review."

    return {
        "agent": "Pest and Disease Retrieval Agent",
        "crop_report": crop_report,
        "possible_pest_risks": [item["risk"] for item in accepted_pests],
        "pest_risk_evidence": accepted_pests,
        "possible_disease_risks": [item["risk"] for item in accepted_diseases],
        "disease_risk_evidence": accepted_diseases,
        "recommendations": [item["text"] for item in recommendations],
        "recommendation_evidence": [
            {"text": item["text"], "evidence_status": item["evidence_status"], "sources": item["sources"]}
            for item in recommendations
        ],
        "evidence_summary": summary,
        "evidence_status": "conflicting" if conflict else "insufficient" if insufficient else "source_supported_possible_risks",
        "retrieval_conflict": conflict,
        "retrieved_sources": [public_source(item) for item in retrieved],
        "evidence_sources": [public_source(item) for item in relevant],
        "expert_inspection_required": insufficient or chemical_recommendation_withheld or bool(
            model_result and model_result.get("expert_inspection_required")
        ),
        "historical_context_used": bool(historical_context),
        "status": "success",
    }


def _validate_named_risks(value, passages, category, crop_name, symptoms):
    if not isinstance(value, list):
        return [], True
    accepted = []
    rejected = False
    for item in value:
        if not isinstance(item, dict) or set(item) != {"name", "evidence_id"}:
            rejected = True
            continue
        name = item.get("name")
        passage = find_passage(passages, item.get("evidence_id"), category=category)
        if not isinstance(name, str) or not name.strip() or passage is None:
            rejected = True
            continue
        expected_crop = str(crop_name).casefold().replace(" ", "_")
        if passage.get("crop") not in {expected_crop, "general"}:
            rejected = True
            continue
        # The named pest/disease must be present as a complete text phrase.
        if (
            not exact_source_text(name, passage)
            or not supports_symptom_risk_relationship(name, symptoms, passage)
        ):
            rejected = True
            continue
        accepted.append({
            "risk": f"Possible {name.strip()}",
            "evidence_status": "source_supported_possible_risk",
            "sources": [public_source(passage)],
        })
    return accepted, rejected


def _is_chemical_treatment_recommendation(text):
    """Conservatively detect actionable use/application of chemical products."""
    product = re.compile(
        r"\b(?:pesticid\w*|insecticid\w*|fungicid\w*|herbicid\w*|acaricid\w*|"
        r"chemical\w*|neem\s+oil|horticultural\s+oil|oil[- ]based\s+(?:product|treatment)|"
        r"sulfur\s+dust|soap(?:y)?\s+solutions?|mixtures?|solutions?|dusts?|"
        r"spray\w*|product|formulation|active\s+ingredient|dosage|dose|dilution)\b",
        re.I,
    )
    treatment_intent = re.compile(
        r"\b(?:use|apply|spray|treat|mix|dilute|dose|administer|coat|dust|drench|"
        r"fumigate|recommend\w*|suggest\w*|consider|select|choose|rotate)\b",
        re.I,
    )
    dosage_instruction = re.compile(
        r"\b(?:\d+(?:\.\d+)?\s*(?:mg|g|kg|ml|mL|l|L|%|ppm)\b|"
        r"per\s+(?:litre|liter|gallon|acre|hectare)|dosage|dilution)\b",
        re.I,
    )
    application_intent = re.compile(
        r"\b(?:use|apply|spray|mix|dilute|dose|administer|coat|dust|drench|fumigate)\b",
        re.I,
    )
    return bool(
        product.search(text) and treatment_intent.search(text)
        or dosage_instruction.search(text) and application_intent.search(text)
    )


def crop_health_agent(
    crop_name,
    growth_stage,
    symptoms,
    historical_context="",
    *,
    knowledge_searcher=None,
    llm_json=None,
):
    return pest_disease_retrieval_agent(
        crop_name,
        growth_stage,
        symptoms,
        historical_context=historical_context,
        knowledge_searcher=knowledge_searcher,
        llm_json=llm_json,
    )
