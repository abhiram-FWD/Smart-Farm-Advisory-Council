from unittest.mock import Mock

from agents.crop_health_agent import crop_health_agent


PEST = {"evidence_id": "wheat-pests::aphids::0", "source": "wheat_pests.txt", "title": "Wheat pest guide",
        "section": "Aphids", "crop": "wheat", "category": "pests",
        "content": "Aphids are small insects on wheat leaves. Yellowing or curling leaves may occur. Inspect leaves and stems regularly. Record infestation levels and crop growth stage."}


def test_source_supported_risk_symptoms_impact_and_practical_monitoring():
    llm = Mock(return_value={
        "risks": [{"name": "Aphids", "category": "pests", "impact": "Aphids may be found on wheat leaves.",
                   "symptoms_to_check": ["yellowing leaves"], "evidence_ids": [PEST["evidence_id"]]}],
        "recommendations": [{"text": "Inspect leaves and stems regularly and record infestation levels.", "evidence_ids": [PEST["evidence_id"]]}],
    })
    result = crop_health_agent("Wheat", "Vegetative", ["Yellow leaves"],
                               knowledge_searcher=Mock(side_effect=[[PEST], []]), llm_json=llm)
    assert llm.called
    assert result["possible_pest_risks"] == ["Possible Aphids"]
    assert result["risk_details"][0]["symptoms_to_check"] == ["yellowing leaves"]
    assert result["recommendations"]
    assert result["pest_risk_evidence"][0]["sources"]


def test_rejects_unretrieved_risk_citations_and_falls_back_to_field_checks():
    llm = Mock(return_value={"risks": [{"name": "Aphids", "category": "pests", "impact": "Aphids damage wheat leaves.", "evidence_ids": ["fake"]}], "recommendations": []})
    result = crop_health_agent("Wheat", "Vegetative", ["Yellow leaves"],
                               knowledge_searcher=Mock(side_effect=[[PEST], []]), llm_json=llm)
    assert result["possible_pest_risks"] == []
    assert result["expert_inspection_required"] is True
    assert result["recommendations"]


def test_no_retrieval_or_groq_still_returns_precautionary_steps():
    result = crop_health_agent("Rice", "Flowering", [],
                               knowledge_searcher=Mock(side_effect=RuntimeError("offline")),
                               llm_json=Mock(side_effect=RuntimeError("offline")))
    assert result["possible_pest_risks"] == []
    assert result["possible_disease_risks"] == []
    assert result["recommendations"]
    assert result["next_steps"]
    assert result["expert_inspection_required"]


def test_allows_source_supported_treatment_guidance_but_does_not_invent_it():
    p = {**PEST, "content": PEST["content"] + " Aphids may be treated with a registered insecticide."}
    llm = Mock(return_value={"risks": [], "recommendations": [
        {"text": "Apply insecticide to control aphids.", "evidence_ids": [p["evidence_id"]]}]})
    result = crop_health_agent("Wheat", "Vegetative", [], knowledge_searcher=Mock(side_effect=[[p], []]), llm_json=llm)
    assert "Apply insecticide to control aphids." in result["recommendations"]


def test_rejects_chemical_application_when_guide_only_has_a_precaution():
    llm = Mock(return_value={"risks": [], "recommendations": [
        {"text": "Apply insecticide to control aphids.", "evidence_ids": [PEST["evidence_id"]]}]})
    result = crop_health_agent("Wheat", "Vegetative", [], knowledge_searcher=Mock(side_effect=[[PEST], []]), llm_json=llm)
    assert "Apply insecticide to control aphids." not in result["recommendations"]


def test_crop_risk_links_only_reported_symptoms_and_uses_cautious_priority():
    llm = Mock(return_value={
        "risks": [{"name": "Aphids", "category": "pests", "impact": "Aphids may affect wheat leaves.",
                   "why_relevant": "The reported leaf yellowing can also occur with aphids.",
                   "reported_symptoms": ["Yellow leaves", "Wilting"],
                   "symptoms_to_check": ["insects under leaves"], "inspection_step": "Check leaf undersides.",
                   "evidence_ids": [PEST["evidence_id"]]}],
        "recommendations": [],
    })
    result = crop_health_agent("Wheat", "Vegetative", ["Yellow leaves"],
                               knowledge_searcher=Mock(side_effect=[[PEST], []]), llm_json=llm)
    risk = result["risk_details"][0]
    assert risk["reported_symptoms"] == ["Yellow leaves"]
    assert risk["priority"] == "medium"
    assert risk["why_relevant"]
    assert risk["inspection_step"]
