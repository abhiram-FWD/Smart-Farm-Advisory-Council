from agents.evidence import normalize_passages, passage_is_relevant, retrieved_passages_conflict, supports_symptom_risk_relationship


def test_conflict_heuristic_detects_differently_worded_opposite_guidance():
    passages = [
        {"content": "Inspect wheat leaves weekly for aphids."},
        {"content": "Do not inspect wheat leaves weekly for aphids."},
    ]
    assert retrieved_passages_conflict(passages) is True


def test_conflict_heuristic_documents_its_limit_for_semantically_conflicting_text():
    passages = [
        {"content": "Irrigate the crop after a dry week."},
        {"content": "Withhold water following dry weather."},
    ]
    # This lexical heuristic is not a semantic contradiction detector.
    assert retrieved_passages_conflict(passages) is False


def test_conflict_heuristic_detects_additional_negation_forms():
    passages = [
        {"content": "Apply treatment to wheat leaves weekly."},
        {"content": "Apply treatment to wheat leaves weekly; contraindicated."},
    ]
    assert retrieved_passages_conflict(passages) is True


def test_symptom_risk_relationship_rejects_weather_clause_bypass():
    passage = {"content": "Aphids are associated with wet weather, and yellow leaves were reported."}
    assert not supports_symptom_risk_relationship("Aphids", ["yellow leaves"], passage)


def test_symptom_risk_relationship_requires_explicit_relation_participants():
    assert supports_symptom_risk_relationship(
        "Aphids", ["yellow leaves"],
        {"content": "Yellow leaves may be symptoms of Aphids."},
    )
    assert not supports_symptom_risk_relationship(
        "Aphids", ["yellow leaves"],
        {"content": "Aphids occur on wheat. Yellow leaves were reported."},
    )
    assert not supports_symptom_risk_relationship(
        "Aphids", ["yellow leaves"],
        {"content": "Aphids are associated with wet weather. Yellow leaves were reported."},
    )
    assert not supports_symptom_risk_relationship(
        "Aphids", ["yellow leaves"],
        {"content": "Yellow leaves are not associated with Aphids."},
    )
    assert not supports_symptom_risk_relationship(
        "Aphids", ["yellow leaves"],
        {"content": "Yellow leaves are excluded as a symptom of Aphids."},
    )
    assert not supports_symptom_risk_relationship(
        "Aphids", ["yellow leaves"],
        {"content": "Yellow leaves may possibly be a symptom of Aphids."},
    )
    assert supports_symptom_risk_relationship(
        "Aphids", ["yellow leaves"],
        {"content": "Yellow leaves are symptoms of Aphids. Inspect the field regularly."},
    )


def test_later_unconfirmed_relationship_rejects_prior_positive_clause():
    for content in (
        "Yellow leaves are associated with Aphids, but the relationship is not confirmed.",
        "Yellow leaves are associated with Aphids, but their relationship is unconfirmed.",
        "Yellow leaves are associated with Aphids. This link is unclear.",
    ):
        assert not supports_symptom_risk_relationship(
            "Aphids", ["yellow leaves"], {"content": content}
        )


def test_unrelated_uncertainty_does_not_reject_explicit_relationship():
    assert supports_symptom_risk_relationship(
        "Aphids", ["yellow leaves"],
        {"content": "Yellow leaves are associated with Aphids. The relationship between rainfall and yield is unclear."},
    )


def test_semantically_ranked_paraphrase_is_not_rejected_by_lexical_gate():
    passage = {
        "content": "Water available to roots can decline as the growing medium dries.",
        "source": "soil-guide.txt",
        "crop": "wheat",
        "category": "soil",
    }
    assert passage_is_relevant(
        passage, "soil moisture and crop growth stage", crop="Wheat", category="soil"
    )
    assert not passage_is_relevant(
        passage, "soil moisture", crop="Rice", category="soil"
    )


def test_missing_provenance_is_labeled_without_fabricating_metadata():
    passage = normalize_passages([{
        "content": "Soil moisture guidance.",
        "source": "local-guide.txt",
        "evidence_id": "local-guide.txt::1::0",
    }])[0]
    assert passage["author"] == "Unavailable"
    assert passage["organization"] == "Unavailable"
    assert passage["publication_date"] == "Unavailable"
    assert passage["provenance_status"] == "weak_or_unavailable"
    assert passage["source_document_status"] == "unverified"
