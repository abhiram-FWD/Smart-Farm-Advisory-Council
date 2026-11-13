from unittest.mock import Mock

import agents.advisory_manager as advisory_manager


def test_advisory_keeps_risks_separate_from_actionable_recommendations(monkeypatch):
    monkeypatch.setattr(advisory_manager, "save_farm_observation", Mock(return_value="obs-1"))
    monkeypatch.setattr(advisory_manager, "get_farm_history", Mock(return_value=[]))
    monkeypatch.setattr(advisory_manager, "save_advisory", Mock(return_value="adv-1"))

    async def orchestrate(**kwargs):
        return {
            "status": "completed",
            "agents": {
                "weather": {"status": "completed", "identified_risks": []},
                "soil": {
                    "status": "completed",
                    "identified_risks": ["Low soil moisture"],
                    "recommendations": ["Review the soil test with a local adviser."],
                    "retrieved_sources": ["Soil guide"],
                },
                "pest_disease": {
                    "status": "completed",
                    "possible_pest_risks": [],
                    "possible_disease_risks": [],
                    "recommendations": ["Inspect the reported leaves."],
                    "retrieved_sources": [],
                },
                "irrigation": {
                    "status": "completed",
                    "recommended_action": "Irrigation recommended",
                    "guidance_type": "preliminary_demonstration_guidance",
                },
            },
            "expected_rainfall_next_3_days_mm": 0,
        }

    monkeypatch.setattr(advisory_manager, "run_semantic_kernel_orchestration", orchestrate)

    result = advisory_manager.generate_farm_advisory(
        latitude=12,
        longitude=77,
        soil_moisture=20,
        soil_ph=6.5,
        nitrogen=10,
        phosphorus=10,
        potassium=10,
        crop_name="Crop",
        growth_stage="Stage",
        symptoms=[],
        farm_id="isolated-test-farm",
    )

    assert result["status"] == "completed"
    assert result["weekly_action_list"] == [
        "Review the soil test with a local adviser.",
        "Inspect the reported leaves.",
    ]
    assert len(result["risk_alerts"]) == 1
    assert result["risk_alerts"][0]["risk"] == "Low soil moisture"
    assert result["risk_alerts"][0]["classification"] == "preliminary_rule_indicator"
    assert result["agents"]["soil"]["retrieved_sources"] == ["Soil guide"]
    assert result["watering_schedule"]["recommended_action"] == "Irrigation recommended"
    assert "not a verified seven-day schedule" in result["weekly_action_list_note"]
    assert set(("agents", "weekly_action_list", "risk_alerts", "watering_schedule", "weather_summary")) <= set(result)
    assert advisory_manager.save_farm_observation.call_args.args[0] == "isolated-test-farm"


def test_advisory_preserves_evidence_status_provenance_and_expert_review(monkeypatch):
    monkeypatch.setattr(advisory_manager, "save_farm_observation", Mock(return_value="obs-evidence"))
    monkeypatch.setattr(advisory_manager, "get_farm_history", Mock(return_value=[]))
    monkeypatch.setattr(advisory_manager, "save_advisory", Mock(return_value="adv-evidence"))
    source = {
        "evidence_id": "wheat_pests.txt::1::0",
        "source": "wheat_pests.txt",
        "title": "WHEAT CROP - PEST KNOWLEDGE",
        "filename": "wheat_pests.txt",
        "section": "1. APHIDS",
    }

    async def orchestrate(**kwargs):
        return {
            "status": "completed",
            "agents": {
                "weather": {"status": "completed", "identified_risks": []},
                "soil": {
                    "status": "completed", "identified_risks": [],
                    "ai_identified_risks": [], "recommendations": [],
                    "recommendation_evidence": [],
                    "expert_review_required": True, "retrieved_sources": [],
                },
                "pest_disease": {
                    "status": "success",
                    "possible_pest_risks": ["Possible Aphids"],
                    "pest_risk_evidence": [{
                        "risk": "Possible Aphids",
                        "evidence_status": "source_supported_possible_risk",
                        "sources": [source],
                    }],
                    "possible_disease_risks": [],
                    "recommendations": ["Inspect affected leaves."],
                    "recommendation_evidence": [{
                        "text": "Inspect affected leaves.",
                        "evidence_status": "verbatim_source_excerpt",
                        "sources": [source],
                    }],
                    "expert_inspection_required": True,
                    "retrieved_sources": [source],
                },
                "irrigation": {"status": "completed", "recommended_action": "No action"},
            },
            "expected_rainfall_next_3_days_mm": 0,
        }

    monkeypatch.setattr(advisory_manager, "run_semantic_kernel_orchestration", orchestrate)
    result = advisory_manager.generate_farm_advisory(
        latitude=12, longitude=77, soil_moisture=30, soil_ph=6.5,
        nitrogen=0, phosphorus=0, potassium=0, crop_name="Wheat",
        growth_stage="Vegetative", symptoms=[], farm_id="evidence-test-farm",
    )

    pest_alert = next(item for item in result["risk_alerts"] if item["risk"] == "Possible Aphids")
    assert pest_alert["evidence_status"] == "source_supported_possible_risk"
    assert pest_alert["sources"] == [source["source"]]
    assert pest_alert["evidence_sources"] == [source]
    assert result["weekly_action_list"] == ["Inspect affected leaves."]
    assert result["weekly_action_evidence"][0]["sources"] == [source]
    assert result["expert_review_required"] is True
