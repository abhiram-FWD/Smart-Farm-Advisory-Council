from unittest.mock import Mock

import pytest

from agents.crop_health_agent import crop_health_agent


PEST_PASSAGE = {
    "evidence_id": "wheat_pests.txt::1. APHIDS::0",
    "source": "wheat_pests.txt",
    "title": "WHEAT CROP - PEST KNOWLEDGE",
    "filename": "wheat_pests.txt",
    "relative_path": "pests/wheat_pests.txt",
    "content": "Aphids are small, soft-bodied insects that may occur in colonies on wheat leaves, stems and developing ears. Yellow leaves may be symptoms of Aphids.",
    "category": "pests",
    "crop": "wheat",
    "section": "1. APHIDS",
}
DISEASE_PASSAGE = {
    "evidence_id": "wheat_diseases.txt::1. WHEAT RUST::0",
    "source": "wheat_diseases.txt",
    "title": "WHEAT CROP - DISEASE KNOWLEDGE",
    "filename": "wheat_diseases.txt",
    "relative_path": "diseases/wheat_diseases.txt",
    "content": "Yellow rust may cause yellow leaves with yellow-orange pustules arranged in stripes.",
    "category": "diseases",
    "crop": "wheat",
    "section": "1. WHEAT RUST",
}


def crop_output(**overrides):
    return {
        "possible_pest_risks": [{"name": "Aphids", "evidence_id": PEST_PASSAGE["evidence_id"]}],
        "possible_disease_risks": [{"name": "Yellow rust", "evidence_id": DISEASE_PASSAGE["evidence_id"]}],
        "recommendations": [],
        "expert_inspection_required": False,
        **overrides,
    }


_DEFAULT = object()


def run_crop_agent(pest_results=None, disease_results=None, model_result=_DEFAULT, symptoms=None):
    knowledge = Mock(side_effect=[
        [PEST_PASSAGE] if pest_results is None else pest_results,
        [DISEASE_PASSAGE] if disease_results is None else disease_results,
    ])
    llm = Mock(return_value=crop_output() if model_result is _DEFAULT else model_result)
    result = crop_health_agent(
        crop_name="Wheat",
        growth_stage="Vegetative",
        symptoms=symptoms or ["Yellow leaves", "Leaf spots"],
        knowledge_searcher=knowledge,
        llm_json=llm,
    )
    return result, knowledge, llm


def test_relevant_crop_retrieval_links_possible_risks_to_real_passages():
    result, knowledge, llm = run_crop_agent()

    assert result["possible_pest_risks"] == ["Possible Aphids"]
    assert result["pest_risk_evidence"][0]["sources"][0]["filename"] == "wheat_pests.txt"
    assert result["possible_disease_risks"] == ["Possible Yellow rust"]
    assert result["disease_risk_evidence"][0]["sources"][0]["section"] == "1. WHEAT RUST"
    assert result["expert_inspection_required"] is False
    assert knowledge.call_count == 2
    llm.assert_called_once()


def test_empty_and_irrelevant_crop_retrieval_return_insufficient_evidence():
    cases = [([], []), ([{**PEST_PASSAGE, "content": "Unrelated passage."}], [])]
    for pests, diseases in cases:
        result, _, llm = run_crop_agent(pest_results=pests, disease_results=diseases)
        assert result["possible_pest_risks"] == []
        assert result["possible_disease_risks"] == []
        assert result["expert_inspection_required"] is True
        assert result["evidence_status"] == "insufficient"
        assert "Insufficient relevant" in result["evidence_summary"]
        llm.assert_not_called()


def test_contradictory_retrieved_passages_require_expert_inspection():
    positive = {**PEST_PASSAGE, "content": "Inspect leaf spots regularly."}
    negative = {**DISEASE_PASSAGE, "evidence_id": "conflict::1", "content": "Do not inspect leaf spots regularly."}
    result, _, llm = run_crop_agent(
        pest_results=[positive], disease_results=[negative], symptoms=["leaf spots regularly"]
    )
    assert result["retrieval_conflict"] is True
    assert result["expert_inspection_required"] is True
    assert result["possible_pest_risks"] == []
    llm.assert_not_called()


def test_unretrieved_sources_and_unsupported_diagnoses_are_rejected():
    result, _, _ = run_crop_agent(model_result=crop_output(
        possible_pest_risks=[{"name": "Aphids", "evidence_id": "fabricated-source"}],
        possible_disease_risks=[{"name": "Potato blight", "evidence_id": DISEASE_PASSAGE["evidence_id"]}],
    ))
    assert result["possible_pest_risks"] == []
    assert result["possible_disease_risks"] == []
    assert result["expert_inspection_required"] is True
    assert result["evidence_status"] == "insufficient"


def test_model_generated_source_names_not_present_in_retrieval_are_rejected():
    result, _, _ = run_crop_agent(model_result=crop_output(
        possible_pest_risks=[{
            "name": "Aphids",
            "evidence_id": PEST_PASSAGE["evidence_id"],
            "source_name": "invented_extension_service_report.pdf",
        }],
        possible_disease_risks=[],
    ))
    assert result["possible_pest_risks"] == []
    assert result["expert_inspection_required"] is True


def test_explicit_symptom_to_risk_relationship_is_accepted():
    result, _, _ = run_crop_agent(symptoms=["Yellow leaves"])
    assert result["possible_pest_risks"] == ["Possible Aphids"]
    assert result["pest_risk_evidence"][0]["evidence_status"] == "source_supported_possible_risk"


def test_legacy_crop_response_fields_remain_strings_with_separate_evidence():
    passage = {**PEST_PASSAGE, "content": "Aphids are associated with yellow leaves. Inspect affected leaves regularly."}
    result, _, _ = run_crop_agent(
        pest_results=[passage], disease_results=[], symptoms=["yellow leaves"],
        model_result=crop_output(
            possible_pest_risks=[{"name": "Aphids", "evidence_id": passage["evidence_id"]}],
            possible_disease_risks=[],
            recommendations=[{"text": "Inspect affected leaves regularly.", "evidence_id": passage["evidence_id"]}],
        ),
    )
    assert result["possible_pest_risks"] == ["Possible Aphids"]
    assert result["recommendations"] == ["Inspect affected leaves regularly."]
    assert result["pest_risk_evidence"][0]["risk"] == result["possible_pest_risks"][0]
    assert result["recommendation_evidence"][0]["text"] == result["recommendations"][0]


def test_risk_and_symptom_cooccurrence_without_relationship_is_rejected():
    unrelated = {**PEST_PASSAGE, "content": "Aphids occur on wheat. Yellow leaves were also observed in this field."}
    result, _, _ = run_crop_agent(
        pest_results=[unrelated], disease_results=[], symptoms=["Yellow leaves"],
        model_result=crop_output(possible_disease_risks=[]),
    )
    assert result["possible_pest_risks"] == []
    assert result["expert_inspection_required"] is True
    assert result["evidence_status"] == "insufficient"


def test_weather_relationship_does_not_transfer_to_unrelated_symptom_clause():
    passage = {
        **PEST_PASSAGE,
        "content": "Aphids are associated with wet weather, and yellow leaves were reported.",
    }
    result, _, _ = run_crop_agent(
        pest_results=[passage], disease_results=[], symptoms=["yellow leaves"],
        model_result=crop_output(possible_disease_risks=[]),
    )
    assert result["possible_pest_risks"] == []
    assert result["pest_risk_evidence"] == []
    assert result["expert_inspection_required"] is True


def test_unconfirmed_followup_cannot_leave_risk_in_legacy_or_evidence_fields():
    passage = {
        **PEST_PASSAGE,
        "content": "Yellow leaves are associated with Aphids, but the relationship is not confirmed.",
    }
    result, _, _ = run_crop_agent(
        pest_results=[passage], disease_results=[], symptoms=["yellow leaves"],
        model_result=crop_output(possible_disease_risks=[]),
    )
    assert result["possible_pest_risks"] == []
    assert result["pest_risk_evidence"] == []
    assert result["expert_inspection_required"] is True


def test_unrelated_uncertain_relationship_does_not_hide_explicit_crop_risk():
    passage = {
        **PEST_PASSAGE,
        "content": (
            "Yellow leaves are associated with Aphids. "
            "The relationship between rainfall and yield is unclear."
        ),
    }
    result, _, _ = run_crop_agent(
        pest_results=[passage], disease_results=[], symptoms=["yellow leaves"],
        model_result=crop_output(possible_disease_risks=[]),
    )
    assert result["possible_pest_risks"] == ["Possible Aphids"]
    assert result["pest_risk_evidence"][0]["evidence_status"] == "source_supported_possible_risk"
    assert result["expert_inspection_required"] is False


@pytest.mark.parametrize("content", [
    "Yellow leaves are not associated with Aphids.",
    "Aphids are unlikely to cause yellow leaves.",
    "Aphids were ruled out as the cause of yellow leaves.",
])
def test_denied_or_ruled_out_relationship_is_rejected(content):
    passage = {**PEST_PASSAGE, "content": content}
    result, _, _ = run_crop_agent(
        pest_results=[passage], disease_results=[], symptoms=["Yellow leaves"],
        model_result=crop_output(possible_disease_risks=[]),
    )
    assert result["possible_pest_risks"] == []
    assert result["expert_inspection_required"] is True


def test_crop_and_category_mismatches_are_rejected():
    wrong_crop = {**PEST_PASSAGE, "crop": "maize"}
    result, _, _ = run_crop_agent(
        pest_results=[wrong_crop], disease_results=[], symptoms=["Yellow leaves"],
    )
    assert result["possible_pest_risks"] == []
    wrong_category = {**PEST_PASSAGE, "category": "diseases"}
    result, _, _ = run_crop_agent(
        pest_results=[wrong_category], disease_results=[], symptoms=["Yellow leaves"],
    )
    assert result["possible_pest_risks"] == []


def test_empty_and_irrelevant_retrieval_has_no_source_supported_claims():
    for pests, diseases in (([], []), ([{**PEST_PASSAGE, "content": "Unrelated notes."}], [])):
        result, _, _ = run_crop_agent(pest_results=pests, disease_results=diseases)
        assert result["possible_pest_risks"] == []
        assert result["pest_risk_evidence"] == []
        assert result["expert_inspection_required"] is True


def test_chemical_treatment_excerpt_is_not_returned_as_a_recommendation():
    treatment_passage = {
        **PEST_PASSAGE,
        "content": "Use insecticides to treat aphids.",
        "evidence_id": "treatment::0",
    }
    result, _, _ = run_crop_agent(
        pest_results=[treatment_passage], disease_results=[],
        symptoms=["aphids"],
        model_result=crop_output(
            possible_pest_risks=[], possible_disease_risks=[],
            recommendations=[{
                "text": "Use insecticides to treat aphids.",
                "evidence_id": "treatment::0",
            }],
        ),
    )
    assert result["recommendations"] == []
    assert result["expert_inspection_required"] is True


@pytest.mark.parametrize("advice", [
    "Use neem oil to treat aphids.",
    "Apply sulfur dust to treat aphids.",
    "Use a soap solution to treat aphids.",
    "Apply the garden product to treat aphids.",
    "Spray the crop to control aphids.",
    "Apply 5 ml per litre to treat aphids.",
    "Use fungicide to treat aphids.",
    "Apply insecticide to control aphids.",
])
def test_actionable_chemical_and_dosage_recommendations_are_withheld(advice):
    passage = {**PEST_PASSAGE, "content": advice, "evidence_id": "chemical::0"}
    result, _, _ = run_crop_agent(
        pest_results=[passage], disease_results=[], symptoms=["aphids"],
        model_result=crop_output(
            possible_pest_risks=[], possible_disease_risks=[],
            recommendations=[{"text": advice, "evidence_id": "chemical::0"}],
        ),
    )
    assert result["recommendations"] == []
    assert result["recommendation_evidence"] == []
    assert result["expert_inspection_required"] is True


@pytest.mark.parametrize("advice", [
    "Monitor the crop regularly for aphids.",
    "Inspect aphids on affected leaves and record changes.",
])
def test_safe_monitoring_and_inspection_are_not_filtered_as_chemical_treatment(advice):
    passage = {**PEST_PASSAGE, "content": advice, "evidence_id": "monitoring::0"}
    result, _, _ = run_crop_agent(
        pest_results=[passage], disease_results=[], symptoms=["aphids"],
        model_result=crop_output(
            possible_pest_risks=[], possible_disease_risks=[],
            recommendations=[{"text": advice, "evidence_id": "monitoring::0"}],
        ),
    )
    assert result["recommendations"] == [advice]
    assert result["expert_inspection_required"] is False


def test_malformed_or_incomplete_model_json_fails_to_insufficient_state():
    for response in (None, [], {"possible_pest_risks": []}):
        result, _, _ = run_crop_agent(model_result=response)
        assert result["possible_pest_risks"] == []
        assert result["possible_disease_risks"] == []
        assert result["recommendations"] == []
        assert result["expert_inspection_required"] is True
        assert "schema validation" in result["evidence_summary"]


def test_task_3a_crop_report_and_history_contract_remain_available():
    result, _, _ = run_crop_agent(model_result=crop_output(
        possible_pest_risks=[], possible_disease_risks=[], expert_inspection_required=True,
    ))
    assert result["status"] == "success"
    assert result["historical_context_used"] is False
    assert result["crop_report"]["crop_name"] == "Wheat"
