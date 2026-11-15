from unittest.mock import Mock

from agents.irrigation_agent import irrigation_agent


def agent(**kwargs):
    return irrigation_agent(knowledge_searcher=Mock(return_value=[]), llm_json=Mock(), **kwargs)


def test_low_moisture_and_little_rain_prompt_root_zone_check():
    result = agent(soil_moisture=24, expected_rainfall=2, crop_name="Rice", growth_stage="Tillering", soil_type="Clay")
    assert result["recommended_action"] == "Consider irrigation"
    assert "root depth" in result["reason"]
    assert result["context_inputs"]["growth_stage"] == "Tillering"


def test_rain_forecast_prompts_recheck_before_irrigation():
    result = agent(soil_moisture=24, expected_rainfall=12, crop_name="Rice", precipitation_probability_max=[80, 60])
    assert result["recommended_action"] == "Recheck before irrigating"
    assert result["forecast_precipitation_probability_max"] == [80, 60]


def test_missing_rainfall_keeps_moisture_guidance_cautious():
    result = agent(soil_moisture=24, expected_rainfall=None, crop_name="Wheat")
    assert result["recommended_action"] == "Check local forecast before deciding"
    assert "unavailable" in result["reason"].lower()


def test_high_moisture_advises_drainage_check():
    result = agent(soil_moisture=88, expected_rainfall=0, crop_name="Rice")
    assert result["recommended_action"] == "Pause and check drainage"
    assert "standing water" in result["reason"]


def test_missing_moisture_does_not_claim_a_watering_decision_or_volume():
    result = agent(soil_moisture=None, expected_rainfall=0, crop_name="Wheat")
    assert result["recommended_action"] == "Check field moisture"
    assert result["decision_basis"]["quantity_prescribed"] is False


def test_recent_rainfall_is_recorded_as_context():
    result = agent(soil_moisture=24, expected_rainfall=2, crop_name="Rice", growth_stage="Tillering",
                   recent_rainfall_mm=8, recent_rainfall_date="2026-11-13")
    assert result["context_inputs"]["recent_rainfall_date"] == "2026-11-13"
    assert "8 mm" in result["guidance_note"]
    factors = {item["label"]: item["detail"] for item in result["decision_factors"]}
    assert "24%" in factors["Soil"]
    assert "Rice" in factors["Crop stage"]
    assert "8 mm" in factors["Recent rain"]
    assert "after rain" in factors["When to reconsider"]
