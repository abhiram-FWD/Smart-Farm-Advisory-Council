from unittest.mock import Mock

import pytest

import agents.soil_agent as soil_agent_module


SOIL_CONTENT = (
    "Soil moisture should be interpreted according to soil texture, crop type, "
    "growth stage and recent weather conditions. "
    "Monitor soil conditions regularly and maintain farm records."
)


def soil_passage(content=SOIL_CONTENT, **overrides):
    return {
        "evidence_id": "soil-management.txt::2. SOIL MOISTURE::0",
        "source": "soil_management.txt",
        "title": "SOIL MANAGEMENT AND AGRONOMY GUIDE",
        "filename": "soil_management.txt",
        "relative_path": "soil_management.txt",
        "content": content,
        "section": "2. SOIL MOISTURE",
        "crop": "general",
        "category": "soil",
        **overrides,
    }


def soil_output(**overrides):
    return {
        "interpretations": [{
            "text": "Soil moisture should be interpreted according to soil texture, crop type, growth stage and recent weather conditions.",
            "evidence_id": "soil-management.txt::2. SOIL MOISTURE::0",
        }],
        "recommendations": [{
            "text": "Monitor soil conditions regularly and maintain farm records.",
            "evidence_id": "soil-management.txt::2. SOIL MOISTURE::0",
        }],
        "expert_review_required": False,
        **overrides,
    }


def run_soil_agent(ai_result=None, retrieved=None, crop_name="Wheat"):
    knowledge = Mock(return_value=[soil_passage()] if retrieved is None else retrieved)
    llm = Mock(return_value=soil_output() if ai_result is None else ai_result)
    result = soil_agent_module.soil_agent(
        moisture=20,
        ph=5.0,
        nitrogen=12.5,
        phosphorus=26.0,
        potassium=8.25,
        crop_name=crop_name,
        knowledge_searcher=knowledge,
        llm_json=llm,
    )
    return result, knowledge, llm


def test_preserves_npk_values_without_threshold_classifications():
    result, _, _ = run_soil_agent()

    assert result["soil_report"]["nitrogen"] == 12.5
    assert result["soil_report"]["phosphorus"] == 26.0
    assert result["soil_report"]["potassium"] == 8.25
    assert not any("nitrogen" in item.lower() for item in result["ai_identified_risks"])
    assert "units" in result["nutrient_interpretation_note"]
    assert "soil-test method" in result["nutrient_interpretation_note"]
    assert "crop requirements" in result["nutrient_interpretation_note"]
    assert "regional recommendations" in result["nutrient_interpretation_note"]


def test_relevant_soil_retrieval_returns_traceable_source_excerpts_and_crop_query():
    result, knowledge, _ = run_soil_agent()

    assert result["evidence_status"] == "source_excerpt"
    assert result["expert_review_required"] is False
    assert isinstance(result["ai_identified_risks"][0], str)
    assert result["ai_risk_evidence"][0]["sources"][0]["filename"] == "soil_management.txt"
    assert result["ai_risk_evidence"][0]["evidence_status"] == "verbatim_source_excerpt"
    assert isinstance(result["recommendations"][0], str)
    assert result["recommendation_evidence"][0]["text"] == result["recommendations"][0]
    assert knowledge.call_args.kwargs["crop"] == "Wheat"


def test_empty_and_irrelevant_soil_retrieval_requires_review_and_skips_llm():
    for passages in ([], [soil_passage("Unrelated phrase about unrelated things.")]):
        result, _, llm = run_soil_agent(retrieved=passages)
        assert result["evidence_status"] == "insufficient"
        assert result["expert_review_required"] is True
        assert result["ai_identified_risks"] == []
        assert result["recommendations"] == []
        llm.assert_not_called()


def test_unitless_npk_claims_and_recommendations_are_rejected():
    result, _, _ = run_soil_agent(ai_result={
        "interpretations": [{
            "text": "Low nitrogen",
            "evidence_id": "soil-management.txt::2. SOIL MOISTURE::0",
        }],
        "recommendations": [{
            "text": "Apply fertilizer now",
            "evidence_id": "soil-management.txt::2. SOIL MOISTURE::0",
        }],
        "expert_review_required": False,
    })
    assert result["ai_identified_risks"] == []
    assert result["recommendations"] == []
    assert result["expert_review_required"] is True


@pytest.mark.parametrize("claim", [
    "Nitrogen is adequate.",
    "Phosphorus is optimal.",
    "Potassium is insufficient.",
    "The crop shows a nitrogen deficiency.",
    "Nitrogen levels are not enough for the crop.",
    "Phosphorus is balanced.",
    "Potassium is excessive.",
    "Nitrogen is suboptimal.",
    "Phosphorus is within an acceptable range.",
])
def test_npk_status_interpretations_are_rejected_without_units_and_method(claim):
    passage = soil_passage(claim)
    result, _, _ = run_soil_agent(
        retrieved=[passage],
        ai_result={
            "interpretations": [{"text": claim, "evidence_id": passage["evidence_id"]}],
            "recommendations": [],
            "expert_review_required": False,
        },
    )
    assert result["ai_identified_risks"] == []
    assert result["ai_risk_evidence"] == []
    assert result["expert_review_required"] is True


@pytest.mark.parametrize("advice", [
    "Apply nitrogen fertilizer to the field.",
    "Add phosphorus to the soil.",
    "Apply a nutrient amendment to the crop.",
    "Increase potassium with fertilizer.",
    "Apply urea to the field.",
])
def test_npk_fertilizer_and_amendment_recommendations_are_rejected(advice):
    passage = soil_passage(advice)
    result, _, _ = run_soil_agent(
        retrieved=[passage],
        ai_result={
            "interpretations": [],
            "recommendations": [{"text": advice, "evidence_id": passage["evidence_id"]}],
            "expert_review_required": False,
        },
    )
    assert result["recommendations"] == []
    assert result["recommendation_evidence"] == []
    assert result["expert_review_required"] is True


def test_neutral_npk_measurement_excerpt_remains_available():
    neutral = "Soil moisture was recorded; nitrogen was measured at 12.5 in the submitted sample."
    passage = soil_passage(neutral)
    result, _, _ = run_soil_agent(
        retrieved=[passage],
        ai_result={
            "interpretations": [{"text": neutral, "evidence_id": passage["evidence_id"]}],
            "recommendations": [],
            "expert_review_required": False,
        },
    )
    assert result["ai_identified_risks"] == [neutral]
    assert result["ai_risk_evidence"][0]["text"] == neutral


@pytest.mark.parametrize("advice", [
    "Test soil moisture before interpreting nutrient levels.",
    "Inspect soil moisture and texture regularly.",
])
def test_safe_soil_testing_and_inspection_recommendations_remain_available(advice):
    passage = soil_passage(advice)
    result, _, _ = run_soil_agent(
        retrieved=[passage],
        ai_result={
            "interpretations": [],
            "recommendations": [{"text": advice, "evidence_id": passage["evidence_id"]}],
            "expert_review_required": False,
        },
    )
    assert result["recommendations"] == [advice]
    assert result["recommendation_evidence"][0]["text"] == advice


def test_unretrieved_citation_and_malformed_schema_fail_safely():
    invalid_outputs = [
        {
            "interpretations": [{"text": "Unsupported claim", "evidence_id": "not-retrieved"}],
            "recommendations": [], "expert_review_required": False,
        },
        {"interpretations": [], "recommendations": []},
        {"interpretations": "not-a-list", "recommendations": [], "expert_review_required": False},
    ]
    for output in invalid_outputs:
        result, _, _ = run_soil_agent(ai_result=output)
        assert result["ai_identified_risks"] == []
        assert result["recommendations"] == []
        assert result["expert_review_required"] is True


def test_task_3a_preliminary_moisture_and_ph_rules_remain_labeled():
    result, _, _ = run_soil_agent()

    assert result["preliminary_rule_indicators"] == [
        "Low soil moisture", "Soil may be too acidic",
    ]
    assert result["identified_risks"] == result["preliminary_rule_indicators"]
    assert "not diagnoses" in result["indicator_context"]
    assert result["soil_report"]["source"] == "Farm Soil Report"
