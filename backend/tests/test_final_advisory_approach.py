from unittest.mock import Mock

from agents.crop_health_agent import crop_health_agent
from agents.irrigation_agent import irrigation_agent
from agents.soil_agent import soil_agent
import agents.advisory_manager as advisory_manager


def passage(category="soil", content="Soil pH affects nutrient availability. Soil moisture affects root development. Soil testing helps determine nutrient availability and pH."):
    return {"evidence_id": "guide::section::1", "source": "farm-guide.txt", "title": "Farm guide",
            "section": "Soil", "crop": "general", "category": category, "content": content}


def test_soil_has_safe_actions_without_retrieval_and_does_not_diagnose_unitless_nutrients():
    result = soil_agent(24, 5.2, 10, 12, 9, crop_name="Rice", growth_stage="Tillering",
                        knowledge_searcher=Mock(side_effect=RuntimeError("offline")), llm_json=Mock())
    assert result["recommendations"]
    assert result["nutrient_interpretation_note"]
    assert not any("deficiency" in item.lower() for item in result["ai_identified_risks"])
    assert result["retrieval_status"] == "unavailable"


def test_soil_accepts_a_cited_plain_language_paraphrase_and_keeps_nutrient_caution():
    p = passage()
    llm = Mock(return_value={"findings": [{"text": "Acidity may change nutrient availability for this crop.", "evidence_ids": [p["evidence_id"]]}],
                             "recommendations": [{"text": "Use a soil test to check pH and nutrient availability.", "evidence_ids": [p["evidence_id"]]}]})
    result = soil_agent(40, 5.2, 10, 12, 9, crop_name="Rice", knowledge_searcher=Mock(return_value=[p]), llm_json=llm)
    assert result["llm_status"] == "success"
    assert result["ai_identified_risks"]
    assert result["recommendations"]
    assert result["assessment_context"]["nutrients_interpreted"] is False


def test_soil_recommendations_follow_changed_crop_stage_and_measurements():
    p = passage(content="Rice and maize depend on soil moisture. Soil pH affects nutrient availability; soil testing helps guide inputs.")
    p["evidence_id"] = "general-soil::moisture-ph::1"
    llm = Mock(side_effect=[
        {"findings": [], "recommendations": [{"text": "Check rice root-zone moisture during tillering.", "evidence_ids": [p["evidence_id"]]}]},
        {"findings": [], "recommendations": [{"text": "Check maize soil pH with a fresh test before changing inputs.", "evidence_ids": [p["evidence_id"]]}]},
    ])
    search = Mock(return_value=[p])
    rice = soil_agent(20, 5.4, 12, 8, 9, crop_name="Rice", growth_stage="Tillering", knowledge_searcher=search, llm_json=llm)
    maize = soil_agent(58, 7.1, 45, 28, 36, crop_name="Maize", growth_stage="Flowering", knowledge_searcher=search, llm_json=llm)

    assert rice["recommendations"] != maize["recommendations"]
    assert "20" in llm.call_args_list[0].args[1] and "Tillering" in llm.call_args_list[0].args[1]
    assert "58" in llm.call_args_list[1].args[1] and "Flowering" in llm.call_args_list[1].args[1]


def test_crop_health_reports_source_linked_risk_and_prevention_guidance():
    p = passage("pests", "Wheat crop - pest knowledge. Aphids are small insects. Yellowing or curling leaves may occur. Inspect leaves and stems regularly. Record infestation levels.")
    llm = Mock(return_value={"risks": [{"name": "Aphids", "category": "pests", "impact": "Aphids may cause yellowing or curling leaves.", "symptoms_to_check": ["yellowing leaves"], "evidence_ids": [p["evidence_id"]]}],
                             "recommendations": [{"text": "Inspect leaves and stems regularly and record infestation levels.", "evidence_ids": [p["evidence_id"]]}]})
    result = crop_health_agent("Wheat", "Vegetative", ["yellow leaves"], knowledge_searcher=Mock(side_effect=[[p], []]), llm_json=llm)
    assert result["possible_pest_risks"] == ["Possible Aphids"]
    assert result["risk_details"][0]["symptoms_to_check"]
    assert result["recommendations"]
    assert result["pest_risk_evidence"][0]["sources"]


def test_crop_health_changes_risk_and_actions_for_crop_and_reported_symptoms():
    p = passage("pests", "Aphids damage wheat leaves. Rice leaf folders chew rice leaves. Inspect plants with the crop-specific signs and record how damage spreads.")
    p.update({"evidence_id": "general-pest-guide::crop-signs::1", "crop": "general"})
    llm = Mock(side_effect=[
        {"risks": [{"name": "Aphids", "category": "pests", "impact": "Aphids damage wheat leaves.", "symptoms_to_check": ["yellow leaves"], "evidence_ids": [p["evidence_id"]]}],
         "recommendations": [{"text": "Inspect wheat leaves for aphids and record damage.", "evidence_ids": [p["evidence_id"]]}]},
        {"risks": [{"name": "Rice leaf folders", "category": "pests", "impact": "Rice leaf folders chew rice leaves.", "symptoms_to_check": ["chewed leaves"], "evidence_ids": [p["evidence_id"]]}],
         "recommendations": [{"text": "Inspect rice leaves for chewing and record where damage is spreading.", "evidence_ids": [p["evidence_id"]]}]},
    ])
    search = Mock(return_value=[p])
    wheat = crop_health_agent("Wheat", "Vegetative", ["yellow leaves"], knowledge_searcher=search, llm_json=llm)
    rice = crop_health_agent("Rice", "Tillering", ["chewed leaves"], knowledge_searcher=search, llm_json=llm)

    assert wheat["risk_details"][0]["name"] == "Aphids"
    assert rice["risk_details"][0]["name"] == "Rice leaf folders"
    assert wheat["recommendations"] != rice["recommendations"]
    assert "yellow leaves" in llm.call_args_list[0].args[1]
    assert "chewed leaves" in llm.call_args_list[1].args[1]


def test_crop_health_uses_precautionary_fallback_when_ai_or_retrieval_is_unavailable():
    result = crop_health_agent("Rice", "Flowering", [], knowledge_searcher=Mock(side_effect=RuntimeError("offline")), llm_json=Mock())
    assert result["recommendations"]
    assert result["possible_pest_risks"] == []
    assert result["possible_disease_risks"] == []
    assert result["expert_inspection_required"] is True


def test_irrigation_uses_crop_and_weather_context_and_never_invents_volume():
    result = irrigation_agent(22, 1, "Rice", growth_stage="Tillering", soil_type="Clay",
                              knowledge_searcher=Mock(return_value=[]), llm_json=Mock())
    assert result["recommended_action"]
    assert result["context_inputs"]["growth_stage"] == "Tillering"
    assert result["decision_basis"]["quantity_prescribed"] is False
    assert "30%" in result["guidance_note"]
    assert [item["day"] for item in result["schedule"]] == ["Today", "Days 2–3", "Days 4–7"]
    assert "water" in result["schedule"][1]["action"].lower()


def test_irrigation_action_changes_with_moisture_and_forecast_rain():
    dry = irrigation_agent(18, 0, "Wheat", growth_stage="Vegetative",
                           knowledge_searcher=Mock(return_value=[]), llm_json=Mock())
    rain_expected = irrigation_agent(18, 24, "Wheat", growth_stage="Vegetative",
                                     knowledge_searcher=Mock(return_value=[]), llm_json=Mock())
    assert dry["recommended_action"] == "Consider irrigation"
    assert rain_expected["recommended_action"] == "Recheck before irrigating"
    assert dry["recommended_action"] != rain_expected["recommended_action"]


def test_soil_conflicting_guides_use_cautious_rule_based_actions():
    passages = [
        {"evidence_id": "guide-a::pH::1", "source": "guide-a", "category": "soil", "crop": "Wheat",
         "content": "Low soil pH can reduce nutrient uptake in wheat."},
        {"evidence_id": "guide-b::pH::2", "source": "guide-b", "category": "soil", "crop": "Wheat",
         "content": "Low soil pH cannot reduce nutrient uptake in wheat."},
    ]
    llm = Mock()
    result = soil_agent(35, 5.0, 15, 8, 12, crop_name="Wheat",
                        knowledge_searcher=Mock(return_value=passages), llm_json=llm)
    assert result["retrieval_conflict"] is True
    assert result["quality_reason"] == "conflicting_sources"
    assert result["recommendations"]
    llm.assert_not_called()


def test_crop_conflicting_guides_do_not_create_a_diagnosis():
    passages = [
        {"evidence_id": "guide-a::aphid::1", "source": "guide-a", "category": "pests", "crop": "Wheat",
         "content": "Aphids damage wheat leaves."},
        {"evidence_id": "guide-b::aphid::2", "source": "guide-b", "category": "pests", "crop": "Wheat",
         "content": "Aphids do not damage wheat leaves."},
    ]
    llm = Mock()
    result = crop_health_agent("Wheat", "Vegetative", [], knowledge_searcher=Mock(side_effect=[passages, []]), llm_json=llm)
    assert result["retrieval_conflict"] is True
    assert result["risk_details"] == []
    assert "guides disagree" in result["evidence_summary"].lower()
    assert result["recommendations"]
    llm.assert_not_called()


def test_advisory_manager_combines_agents_into_a_seven_day_plan(monkeypatch):
    monkeypatch.setattr(advisory_manager, "save_farm_observation", Mock(return_value="obs"))
    monkeypatch.setattr(advisory_manager, "get_farm_history", Mock(return_value=[]))
    monkeypatch.setattr(advisory_manager, "count_farm_observations", Mock(return_value=1))
    monkeypatch.setattr(advisory_manager, "save_advisory", Mock(return_value="advisory"))

    async def orchestrate(**_):
        return {"status": "completed", "agents": {
            "weather": {"status": "completed", "forecast": {"daily_forecast": {"time": ["2026-11-14"], "precipitation_sum": [0]}}},
            "soil": {"status": "completed", "recommendations": ["Review the soil test."], "recommendation_evidence": [{"text": "Review the soil test.", "sources": []}]},
            "pest_disease": {"status": "completed", "recommendations": ["Inspect crop leaves."], "recommendation_evidence": [{"text": "Inspect crop leaves.", "sources": []}]},
            "irrigation": {"status": "completed", "recommended_action": "Check the root zone."},
        }, "expected_rainfall_next_3_days_mm": 0}

    monkeypatch.setattr(advisory_manager, "run_semantic_kernel_orchestration", orchestrate)
    result = advisory_manager.generate_farm_advisory(12, 77, 25, 6.2, 10, 8, 12, "Rice", "Tillering", [], farm_id="test", llm_json=Mock(side_effect=RuntimeError("offline")))
    assert result["status"] == "completed"
    assert [item["day"] for item in result["weekly_action_plan"]] == ["Days 1–2", "Days 1–2", "Today", "Days 2–3", "Days 4–7"]
    assert all(item["action"] and item["priority"] for item in result["weekly_action_plan"])


def test_advisory_manager_uses_groq_to_prioritize_contextual_sourced_actions():
    source = {"evidence_id": "maize-guide::water::1", "source": "maize_guide.txt", "title": "Maize guide"}
    llm = Mock(side_effect=[{"actions": [{
        "day": "Today", "action": "Check maize root-zone moisture before irrigation.",
        "priority": "high", "agent": "Irrigation Planner", "source_ids": [source["evidence_id"]],
    }]}, {"actions": [{
        "day": "Days 1-2", "action": "Check rice field moisture before the next watering.",
        "priority": "medium", "agent": "Irrigation Planner", "source_ids": [source["evidence_id"]],
    }]}])
    observation = {"crop_name": "Maize", "growth_stage": "Tasseling", "soil_moisture": 18,
                   "soil_ph": 6.4, "nitrogen": 30, "phosphorus": 20, "potassium": 22}
    agents = {"soil": {}, "pest_disease": {}, "weather": {"identified_risks": []},
              "irrigation": {"recommended_action": "Consider irrigation", "evidence_sources": [source]}}

    plan, generation = advisory_manager.build_weekly_action_plan(observation, agents, llm_json=llm)

    assert generation == "groq"
    assert plan[0]["action"] == "Check maize root-zone moisture before irrigation."
    assert plan[0]["sources"] == [source]
    model_context = llm.call_args.args[1]
    assert "Maize" in model_context and "Tasseling" in model_context and "18" in model_context
    rice_observation = {**observation, "crop_name": "Rice", "growth_stage": "Flowering", "soil_moisture": 62}
    rice_agents = {**agents, "irrigation": {"recommended_action": "No immediate irrigation", "evidence_sources": [source]}}
    rice_plan, _ = advisory_manager.build_weekly_action_plan(rice_observation, rice_agents, llm_json=llm)
    assert rice_plan[0]["action"] != plan[0]["action"]
    rice_context = llm.call_args.args[1]
    assert "Rice" in rice_context and "Flowering" in rice_context and "62" in rice_context
