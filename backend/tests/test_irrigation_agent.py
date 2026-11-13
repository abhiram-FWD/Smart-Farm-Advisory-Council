import pytest

from agents.irrigation_agent import irrigation_agent


@pytest.mark.parametrize(
    ("moisture", "rainfall", "expected_action"),
    [
        (29.9, 4.9, "Consider irrigation"),
        (29.9, 5.0, "Recheck before irrigating"),
        (29.9, 5.1, "Recheck before irrigating"),
        (30.0, 5.0, "Consider postponing irrigation"),
        (30.0, 5.1, "Consider postponing irrigation"),
        (30.0, 4.9, "No immediate irrigation indicated"),
    ],
)
def test_all_existing_irrigation_branches_are_preserved(moisture, rainfall, expected_action):
    result = irrigation_agent(moisture, rainfall, "Wheat")

    assert result["recommended_action"] == expected_action
    assert result["soil_moisture"] == moisture
    assert result["expected_rainfall_mm"] == rainfall
    assert result["crop"] == "Wheat"
    assert result["status"] == "completed"
    assert result["guidance_type"] == "preliminary_demonstration_guidance"
    assert "not a farm-specific" in result["guidance_note"]
    assert "growth stage" in result["guidance_note"]
    assert "soil type" in result["guidance_note"]
    assert "actual recent rainfall" in result["guidance_note"]
    assert "crop water demand" in result["guidance_note"]
    assert "local conditions" in result["guidance_note"]
    assert not any(key in result for key in ("quantity", "duration", "schedule"))
    assert "may not occur as predicted" in result["reason"]


@pytest.mark.parametrize("rainfall", [None, "unknown", float("nan")])
def test_unavailable_rainfall_never_triggers_irrigation_or_postponement(rainfall):
    result = irrigation_agent(20, rainfall, "Wheat")

    assert result["recommended_action"] == "Irrigation guidance unavailable"
    assert "rainfall forecast is unavailable" in result["reason"]
    assert result["guidance_type"] == "preliminary_demonstration_guidance"


def test_missing_soil_moisture_does_not_produce_an_irrigation_decision():
    result = irrigation_agent(None, 0, "Wheat")

    assert result["recommended_action"] == "Irrigation guidance unavailable"


def test_available_precipitation_probabilities_are_preserved_and_qualified():
    result = irrigation_agent(
        29.9, 5.0, "Wheat", [70, None, 35]
    )

    assert result["forecast_precipitation_probability_max"] == [70, None, 35]
    assert "day 1: 70%" in result["reason"]
    assert "day 2: unavailable" in result["reason"]
    assert "do not guarantee rainfall" in result["reason"]


def test_missing_precipitation_probability_is_not_invented():
    result = irrigation_agent(29.9, 4.9, "Wheat")

    assert result["forecast_precipitation_probability_max"] is None
    assert "Precipitation probability is unavailable" in result["reason"]
    assert "no probability is assumed" in result["reason"]


def test_missing_rainfall_and_moisture_remain_unavailable_with_probability_data():
    result = irrigation_agent(None, None, "Wheat", [80, 70, 60])

    assert result["recommended_action"] == "Irrigation guidance unavailable"
    assert result["expected_rainfall_mm"] is None
    assert result["forecast_precipitation_probability_max"] == [80, 70, 60]
    assert "rainfall forecast amount is unavailable" in result["reason"]
    assert "day 1: 80%" in result["reason"]
