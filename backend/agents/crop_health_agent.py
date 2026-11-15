"""Crop specific pest and disease advice, with cited RAG and safe fallback."""
import re

from agents.evidence import claim_has_source_support, normalize_passages, passage_is_relevant, public_source, normalize_crop_id, retrieved_passages_conflict
from tools.crop_tool import get_crop_report


def pest_disease_retrieval_agent(crop_name, growth_stage, symptoms, historical_context="", *, knowledge_searcher=None, llm_json=None):
    if knowledge_searcher is None:
        from rag.knowledge_base import search_knowledge
        knowledge_searcher = search_knowledge
    if llm_json is None:
        from llm_service import ask_groq_json
        llm_json = ask_groq_json
    symptoms = symptoms or []
    report = get_crop_report(crop_name, growth_stage, symptoms)
    retrieved, retrieval_errors = [], []
    for category in ("pests", "diseases"):
        try:
            retrieved += normalize_passages(knowledge_searcher(f"{crop_name} {growth_stage} {category} {' '.join(symptoms)} monitoring prevention management", n_results=4, crop=crop_name, category=category))
        except Exception:
            retrieval_errors.append(category)
    expected = normalize_crop_id(crop_name)
    relevant = [p for p in retrieved if passage_is_relevant(p, f"{crop_name} {growth_stage}", crop=crop_name, category=p.get("category")) and p.get("category") in ("pests", "diseases")]
    by_id = {p["evidence_id"]: p for p in relevant}
    source_conflict = retrieved_passages_conflict(relevant)
    risks, recommendations = [], []
    llm_status = "unavailable"
    if relevant and not source_conflict:
        context = "\n".join(f"[{p['evidence_id']}] {p['category']} | {p['source']} | {p['section']}: {p['content']}" for p in relevant)
        try:
            result = llm_json(
                'You are a practical crop-health adviser. Explain crop-specific possible pest/disease risks and connect each to the farmer reported symptoms only when they match. Risks are possibilities, never diagnoses. Give a short why_relevant explanation, likely symptoms to inspect, and a practical inspection step. Give treatment measures only when the supplied guides support them; never invent products, rates, or approvals. Prefer non-chemical steps when the cause is unconfirmed. Use only retrieved passages for biological claims. Return JSON: {"risks":[{"name":"...","category":"pests or diseases","impact":"...","why_relevant":"...","reported_symptoms":["exact farmer-reported symptom"],"symptoms_to_check":["..."],"inspection_step":"...","evidence_ids":["..."]}],"recommendations":[{"text":"...","evidence_ids":["..."]}]}',
                f"Crop: {crop_name}; stage: {growth_stage}; symptoms reported now: {symptoms or 'none'}. Historical notes (not current symptoms): {historical_context or 'none'}. Retrieved sources:\n{context}")
            if isinstance(result, dict):
                for item in result.get("risks", []) if isinstance(result.get("risks"), list) else []:
                    if not isinstance(item, dict) or not isinstance(item.get("name"), str): continue
                    ids = item.get("evidence_ids", [])
                    refs = [by_id[i] for i in ids if isinstance(ids, list) and i in by_id and by_id[i].get("category") == item.get("category")]
                    if not refs or any(p.get("crop") not in (expected, "general") for p in refs): continue
                    impact = str(item.get("impact", ""))
                    if not (claim_has_source_support(item["name"], refs) or claim_has_source_support(impact, refs)): continue
                    reported = item.get("reported_symptoms", [])
                    reported = reported if isinstance(reported, list) else []
                    symptom_links = [
                        str(value).strip() for value in reported if isinstance(value, str) and any(
                            value.strip().casefold() == str(symptom).strip().casefold()
                            for symptom in symptoms if isinstance(symptom, str)
                        )
                    ]
                    risks.append({"name": item["name"].strip(), "category": item["category"], "impact": impact or "May affect crop growth if confirmed.", "why_relevant": str(item.get("why_relevant", "A possible cause to check; reported signs alone cannot confirm it.")), "reported_symptoms": symptom_links, "symptoms_to_check": item.get("symptoms_to_check", []) if isinstance(item.get("symptoms_to_check"), list) else [], "inspection_step": str(item.get("inspection_step", "Inspect affected and nearby plants for the listed signs.")), "priority": "medium" if symptom_links else "low", "evidence_status": "source_supported_possible_risk", "sources": [public_source(p) for p in refs]})
                for item in result.get("recommendations", []) if isinstance(result.get("recommendations"), list) else []:
                    if not isinstance(item, dict) or not isinstance(item.get("text"), str): continue
                    ids = item.get("evidence_ids", [])
                    refs = [by_id[i] for i in ids if isinstance(ids, list) and i in by_id]
                    text = item["text"].strip()
                    if not refs or not text or not claim_has_source_support(text, refs): continue
                    if not _treatment_is_source_supported(text, refs): continue
                    recommendations.append({"text": text, "evidence_status": "source_supported_guidance", "sources": [public_source(p) for p in refs]})
                llm_status = "success"
        except Exception:
            llm_status = "provider_error"
    if not recommendations:
        crop_stage = f"{crop_name or 'the crop'}{f' at {growth_stage}' if growth_stage else ''}"
        symptom_note = f" Focus on the reported signs: {', '.join(symptoms)}." if symptoms else " Record any new signs you find."
        recommendations = [
            {"text": f"Inspect {crop_stage} across the field and record where symptoms occur, how many plants are affected and whether damage is spreading.{symptom_note}", "evidence_status": "safe_rule_based_guidance", "sources": [public_source(p) for p in relevant[:1]]},
            {"text": f"Photograph suspected insects or lesions on {crop_name or 'the crop'} and ask a local crop adviser to confirm the cause before treatment.", "evidence_status": "safe_rule_based_guidance", "sources": [public_source(p) for p in relevant[:1]]},
        ]
    risk_evidence = {"pests": [], "diseases": []}
    for risk in risks: risk_evidence[risk["category"]].append({"risk": f"Possible {risk['name']}", **{k: risk[k] for k in ("evidence_status", "sources")}})
    return {
        "agent": "Crop Health Agent", "status": "completed", "execution_status": "completed", "crop_report": report,
        "possible_pest_risks": [x["risk"] for x in risk_evidence["pests"]], "pest_risk_evidence": risk_evidence["pests"],
        "possible_disease_risks": [x["risk"] for x in risk_evidence["diseases"]], "disease_risk_evidence": risk_evidence["diseases"],
        "risk_details": risks, "recommendations": [x["text"] for x in recommendations], "recommendation_evidence": recommendations,
        "evidence_summary": ("Agricultural guides disagree on this point. Monitor the crop and ask a local adviser before choosing a treatment." if source_conflict else "Possible crop-specific risks are listed for field checking; symptoms can overlap and are not a diagnosis." if risks else "No likely issue identified from the available details. Keep monitoring the crop."),
        "evidence_status": "conflicting_sources" if source_conflict else "source_supported_possible_risks" if risks else "rule_based_fallback", "quality_status": "degraded" if source_conflict else "validated" if llm_status == "success" and risks else "degraded",
        "quality_reason": "conflicting_sources" if source_conflict else None if llm_status == "success" and risks else "rule_based_fallback", "llm_status": llm_status,
        "retrieval_status": "partially_unavailable" if retrieval_errors and relevant else "unavailable" if retrieval_errors else "available" if relevant else "no_relevant_sources",
        "retrieval_errors": retrieval_errors, "retrieved_sources": [public_source(p) for p in retrieved], "evidence_sources": [public_source(p) for p in relevant],
        "next_steps": ["Check both affected and apparently healthy plants across the field and note the pattern.", "Photograph symptoms and consult a local crop adviser if damage spreads."],
        "expert_inspection_required": not bool(risks) or source_conflict, "retrieval_conflict": source_conflict, "historical_context_used": bool(historical_context),
    }


def crop_health_agent(crop_name, growth_stage, symptoms, historical_context="", **kwargs):
    return pest_disease_retrieval_agent(crop_name, growth_stage, symptoms, historical_context, **kwargs)


def _treatment_is_source_supported(text, passages):
    """Require a guide to positively support chemical treatment instructions."""
    if not re.search(r"\b(insecticide|fungicide|pesticide|chemical|spray|dosage|dose|rate)\b", text, re.IGNORECASE):
        return True
    treatment_reference = re.compile(
        r"\b(?:treat(?:ed|ment)?|apply|applied|use|used|spray|control|manage)\b.{0,100}\b(?:insecticide|fungicide|pesticide|chemical)\b"
        r"|\b(?:insecticide|fungicide|pesticide|chemical)\b.{0,100}\b(?:treat|apply|use|spray|control|manage)\b",
        re.IGNORECASE,
    )
    for passage in passages:
        content = passage.get("content", "")
        for sentence in re.split(r"(?<=[.!?])\s+", content):
            if treatment_reference.search(sentence) and not re.search(
                r"\b(?:do not|don't|never|avoid|not recommend|not prescribe)\b.{0,70}\b(?:insecticide|fungicide|pesticide|chemical|spray)\b",
                sentence,
                re.IGNORECASE,
            ):
                return True
    return False
