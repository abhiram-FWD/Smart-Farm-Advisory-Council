from unittest.mock import Mock

from agents.soil_agent import soil_agent


PASSAGE = {
    "evidence_id": "soil::pH::0", "source": "soil_guide.txt", "title": "Soil guide",
    "section": "Soil pH", "crop": "general", "category": "soil",
    "content": "Soil pH affects nutrient availability. Soil pH should be measured using a reliable soil testing method. Fertilizer recommendations should consider crop requirements, soil test results and regional agricultural recommendations.",
}


def test_records_npk_without_inventing_deficiencies_when_method_and_units_are_missing():
    result = soil_agent(24, 5.2, 11, 8, 9, crop_name="Rice", growth_stage="Tillering",
                        knowledge_searcher=Mock(return_value=[]), llm_json=Mock())
    assert result["soil_report"]
    assert result["assessment_context"]["nutrients_interpreted"] is False
    assert "units" in result["nutrient_interpretation_note"]
    assert result["recommendations"]
    assert result["preliminary_rule_indicators"]


def test_uses_groq_for_plain_language_explanation_and_accepts_cited_paraphrase():
    model = Mock(return_value={
        "findings": [{"text": "Acidity may affect nutrient availability.", "evidence_ids": [PASSAGE["evidence_id"]]}],
        "recommendations": [{"text": "Use a reliable soil test to check pH before selecting a treatment.", "evidence_ids": [PASSAGE["evidence_id"]]}],
    })
    result = soil_agent(40, 5.2, 11, 8, 9, crop_name="Rice", knowledge_searcher=Mock(return_value=[PASSAGE]), llm_json=model)
    assert model.called
    assert result["llm_status"] == "success"
    assert result["ai_identified_risks"] == ["Acidity may affect nutrient availability."]
    assert result["recommendation_evidence"][0]["sources"][0]["source"] == "soil_guide.txt"


def test_unavailable_retrieval_keeps_safe_measures_and_readings():
    result = soil_agent(24, 6.2, 12, 15, 8, crop_name="Rice",
                        knowledge_searcher=Mock(side_effect=RuntimeError("offline")), llm_json=Mock())
    assert result["retrieval_status"] == "unavailable"
    assert result["soil_report"]
    assert result["recommendations"]
    assert result["next_steps"]


def test_rejects_fabricated_sources_and_unitless_nutrient_claims():
    output = {"findings": [{"text": "Nitrogen deficiency is confirmed.", "evidence_ids": ["fabricated"]}],
              "recommendations": [{"text": "Apply urea immediately.", "evidence_ids": [PASSAGE["evidence_id"]]}]}
    result = soil_agent(40, 6.2, 2, 1, 1, knowledge_searcher=Mock(return_value=[PASSAGE]), llm_json=Mock(return_value=output))
    assert not result["ai_identified_risks"]
    assert "Apply urea immediately." not in result["recommendations"]
    assert result["recommendations"]  # safe, rule-based soil-testing action remains available
