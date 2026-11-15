from unittest.mock import Mock

import agents.advisory_manager as advisory_manager


def test_advisory_keeps_risks_separate_from_actionable_recommendations(monkeypatch):
    monkeypatch.setattr(advisory_manager, "save_farm_observation", Mock(return_value="obs-1"))
    monkeypatch.setattr(advisory_manager, "get_farm_history", Mock(return_value=[]))
    monkeypatch.setattr(advisory_manager, "count_farm_observations", Mock(return_value=1))
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
        llm_json=Mock(side_effect=RuntimeError("offline test")),
    )

    assert result["status"] == "completed"
    assert result["weekly_action_list"] == [
        "Review the soil test with a local adviser.",
        "Inspect the reported leaves.",
        "Irrigation recommended",
    ]
    assert len(result["risk_alerts"]) == 1
    assert result["risk_alerts"][0]["risk"] == "Low soil moisture"
    assert result["risk_alerts"][0]["classification"] == "preliminary_rule_indicator"
    assert result["agents"]["soil"]["retrieved_sources"] == ["Soil guide"]
    assert result["watering_schedule"]["recommended_action"] == "Irrigation recommended"
    assert "seven-day sequence" in result["weekly_action_list_note"]
    assert result["weekly_action_plan"]
    assert set(("agents", "weekly_action_list", "risk_alerts", "watering_schedule", "weather_summary")) <= set(result)
    assert advisory_manager.save_farm_observation.call_args.args[0] == "isolated-test-farm"
    assert result["assessment_id"] == advisory_manager.save_farm_observation.call_args.args[1]["assessment_id"]
    assert result["assessment_snapshot"]["soil_moisture"] == 20
    assert "farmer-reported growth stage: Stage" in result["overall_summary"]


def test_partial_advisory_is_saved_with_successful_findings_and_irrigation_action(monkeypatch):
    monkeypatch.setattr(advisory_manager, "save_farm_observation", Mock(return_value="obs-partial"))
    monkeypatch.setattr(advisory_manager, "get_farm_history", Mock(return_value=[]))
    monkeypatch.setattr(advisory_manager, "count_farm_observations", Mock(return_value=1))
    monkeypatch.setattr(advisory_manager, "save_advisory", Mock(return_value="adv-partial"))

    async def orchestrate(**kwargs):
        return {
            "status": "partial",
            "agent_failures": [{"agent": "weather", "message": "Weather output was unavailable."}],
            "agents": {
                "weather": {"status": "failed", "error": "Weather output was unavailable."},
                "soil": {"status": "completed", "recommendations": ["Inspect soil"]},
                "pest_disease": {"status": "success", "recommendations": ["Inspect leaves"]},
                "irrigation": {"status": "completed", "recommended_action": "Recheck before irrigating"},
            },
            "expected_rainfall_next_3_days_mm": None,
        }

    monkeypatch.setattr(advisory_manager, "run_semantic_kernel_orchestration", orchestrate)
    result = advisory_manager.generate_farm_advisory(
        latitude=12, longitude=77, soil_moisture=25, soil_ph=6.5,
        nitrogen=1, phosphorus=1, potassium=1, crop_name="Rice",
        growth_stage="Tillering", symptoms=[], farm_id="partial-farm",
        llm_json=Mock(side_effect=RuntimeError("offline test")),
    )
    assert result["status"] == "partial"
    assert result["agents"]["soil"]["recommendations"] == ["Inspect soil"]
    assert result["weekly_action_list"] == ["Inspect soil", "Inspect leaves", "Recheck before irrigating"]
    assert result["agent_failures"][0]["agent"] == "weather"


def test_advisory_preserves_evidence_status_provenance_and_expert_review(monkeypatch):
    monkeypatch.setattr(advisory_manager, "save_farm_observation", Mock(return_value="obs-evidence"))
    monkeypatch.setattr(advisory_manager, "get_farm_history", Mock(return_value=[]))
    monkeypatch.setattr(advisory_manager, "count_farm_observations", Mock(return_value=1))
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
                    "risk_details": [{"name": "Aphids", "priority": "low", "impact": "Check for aphids under leaves.", "reported_symptoms": [], "symptoms_to_check": ["small insects"], "inspection_step": "Inspect leaf undersides."}],
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
        llm_json=Mock(side_effect=RuntimeError("offline test")),
    )

    pest_alert = next(item for item in result["risk_alerts"] if item["risk"] == "Possible Aphids")
    assert pest_alert["evidence_status"] == "source_supported_possible_risk"
    assert pest_alert["sources"] == [source["source"]]
    assert pest_alert["evidence_sources"] == [source]
    assert pest_alert["priority"] == "low"
    assert pest_alert["symptoms_to_check"] == ["small insects"]
    assert result["weekly_action_list"] == ["Inspect affected leaves.", "No action"]
    assert result["weekly_action_evidence"][0]["sources"] == [source]
    assert result["expert_review_required"] is True


def test_positive_findings_require_explicit_supporting_source_evidence():
    agent = {
        "soil": {
            "positive_findings": ["Claimed good soil", "Water reading recorded"],
            "positive_finding_evidence": [{"text": "Water reading recorded", "sources": [{"source": "soil test"}]}],
        }
    }
    assert advisory_manager._evidence_supported_positive_findings(agent) == [
        {"text": "Water reading recorded", "reported_by": "soil", "sources": [{"source": "soil test"}]}
    ]


def test_assessment_reports_total_previous_observations_separately_from_agent_context(monkeypatch):
    monkeypatch.setattr(advisory_manager, "save_farm_observation", Mock(return_value="obs-current"))
    monkeypatch.setattr(advisory_manager, "get_farm_history", Mock(return_value=[
        {"observation_id": f"obs-{index}", "observation": {"crop_name": "Rice"}}
        for index in range(10)
    ]))
    monkeypatch.setattr(advisory_manager, "count_farm_observations", Mock(return_value=16))
    monkeypatch.setattr(advisory_manager, "save_advisory", Mock(return_value="adv-count"))

    async def orchestrate(**kwargs):
        return {
            "status": "completed",
            "agents": {
                "weather": {"status": "completed"},
                "soil": {"status": "completed"},
                "pest_disease": {"status": "completed"},
                "irrigation": {"status": "completed"},
            },
        }

    monkeypatch.setattr(advisory_manager, "run_semantic_kernel_orchestration", orchestrate)
    result = advisory_manager.generate_farm_advisory(
        latitude=12, longitude=77, soil_moisture=30, soil_ph=6.5,
        nitrogen=10, phosphorus=10, potassium=10, crop_name="Rice",
        growth_stage="Tillering", symptoms=[], farm_id="history-count-farm",
        llm_json=Mock(side_effect=RuntimeError("offline test")),
    )

    assert result["memory"]["previous_observations_count"] == 15
    assert result["memory"]["historical_context_observations_count"] == 10
    assert result["history_context"] == {
        "previous_observations_count": 15,
        "observations_supplied_to_agents": 10,
    }
