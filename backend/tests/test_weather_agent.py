
from unittest.mock import Mock

import agents.weather_agent as weather_agent_module
import pytest


def _run_one_day_weather(monkeypatch, temperature=20, rainfall=0, probability=0):
    forecast = {"source": "isolated test fixture", "daily_forecast": {
        "time": ["2026-01-01"],
        "temperature_2m_max": [temperature],
        "precipitation_sum": [rainfall],
        "precipitation_probability_max": [probability],
    }}
    monkeypatch.setattr(
        weather_agent_module, "get_weather_forecast", Mock(return_value=forecast)
    )
    return weather_agent_module.weather_agent(31.22, 75.75, knowledge_searcher=Mock(return_value=[]), llm_json=Mock())


def test_weather_agent_uses_supplied_forecast(monkeypatch):
    forecast = {
        "source": "isolated test fixture",
        "location": {"latitude": 31.22, "longitude": 75.77},
        "daily_forecast": {
            "time": ["2026-01-01"],
            "temperature_2m_max": [24],
            "temperature_2m_min": [13],
            "precipitation_sum": [0],
            "precipitation_probability_max": [0],
        },
    }
    fetch = Mock(return_value=forecast)
    monkeypatch.setattr(weather_agent_module, "get_weather_forecast", fetch)

    result = weather_agent_module.weather_agent(
        latitude=31.22,
        longitude=75.77,
        knowledge_searcher=Mock(return_value=[]), llm_json=Mock(),
    )

    assert result.get("status") == "completed"
    assert result.get("agent") is not None
    assert isinstance(result.get("identified_risks"), list)

    forecast = result.get("forecast")

    assert isinstance(forecast, dict)
    assert forecast.get("source") is not None
    assert forecast["daily_forecast"]["precipitation_probability_max"] == [0]

    fetch.assert_called_once_with(31.22, 75.77)


def test_weather_agent_uses_crop_stage_forecast_and_cited_guide_for_actions(monkeypatch):
    passage = {
        "evidence_id": "wheat-guide::water::0", "source": "wheat_guide.txt",
        "title": "Wheat crop advisory guide", "section": "Water management",
        "crop": "general", "category": "crop",
        "content": "Hot weather can increase crop water demand for wheat and rice. Check soil moisture before irrigation.",
    }
    forecast = {"source": "isolated fixture", "daily_forecast": {
        "time": ["2026-11-15"], "temperature_2m_max": [36],
        "temperature_2m_min": [24], "precipitation_sum": [0],
        "precipitation_probability_max": [0],
    }}
    monkeypatch.setattr(weather_agent_module, "get_weather_forecast", Mock(return_value=forecast))
    llm = Mock(return_value={"summary": "Hot, dry weather may raise water demand during wheat growth.", "risks": [{
        "risk": "High temperature", "date": "2026-11-15", "priority": "high",
        "impact": "Heat may increase water stress during wheat vegetative growth.",
        "recommended_action": "Check root-zone moisture early and irrigate only if the soil is dry.",
        "evidence_ids": [passage["evidence_id"]],
    }]})
    result = weather_agent_module.weather_agent(
        31.22, 75.75, crop_name="Wheat", growth_stage="Vegetative", soil_moisture=22,
        symptoms=["wilting"], knowledge_searcher=Mock(return_value=[passage]), llm_json=llm,
    )

    user_context = llm.call_args.args[1]
    assert "Wheat" in user_context and "Vegetative" in user_context
    assert "22" in user_context and "36" in user_context
    assert result["llm_status"] == "success"
    assert result["weather_summary"]
    assert result["identified_risks"][0]["recommended_action"].startswith("Check root-zone")
    assert result["identified_risks"][0]["sources"][0]["evidence_id"] == passage["evidence_id"]

    cool_forecast = {"source": "isolated fixture", "daily_forecast": {
        "time": ["2026-11-15"], "temperature_2m_max": [27],
        "temperature_2m_min": [19], "precipitation_sum": [0],
        "precipitation_probability_max": [0],
    }}
    monkeypatch.setattr(weather_agent_module, "get_weather_forecast", Mock(return_value=cool_forecast))
    cool_llm = Mock(return_value={"summary": "No marked weather stress is expected for flowering rice.", "risks": []})
    cool = weather_agent_module.weather_agent(
        31.22, 75.75, crop_name="Rice", growth_stage="Flowering", soil_moisture=62,
        knowledge_searcher=Mock(return_value=[passage]), llm_json=cool_llm,
    )
    cool_context = cool_llm.call_args.args[1]
    assert "Rice" in cool_context and "Flowering" in cool_context
    assert "62" in cool_context and "27" in cool_context
    assert cool["identified_risks"] == []
    assert cool["weather_summary"] != result["weather_summary"]


def test_missing_rainfall_is_preserved_as_unavailable(monkeypatch):
    forecast = {"source": "isolated test fixture", "daily_forecast": {
        "time": ["2026-01-01", "2026-01-02", "2026-01-03"],
        "temperature_2m_max": [20, 21, 22],
    }}
    monkeypatch.setattr(weather_agent_module, "get_weather_forecast", Mock(return_value=forecast))

    result = weather_agent_module.weather_agent(31.22, 75.75, knowledge_searcher=Mock(return_value=[]), llm_json=Mock())

    assert result["status"] == "completed"
    assert result["forecast"]["daily_forecast"]["precipitation_sum"] == [None, None, None]


def test_none_and_nonnumeric_rainfall_values_are_unavailable(monkeypatch):
    forecast = {"source": "isolated test fixture", "daily_forecast": {
        "time": ["2026-01-01", "2026-01-02", "2026-01-03"],
        "temperature_2m_max": [20, 21, 22],
        "precipitation_sum": [1.5, None, "unknown"],
    }}
    monkeypatch.setattr(weather_agent_module, "get_weather_forecast", Mock(return_value=forecast))

    result = weather_agent_module.weather_agent(31.22, 75.75, knowledge_searcher=Mock(return_value=[]), llm_json=Mock())

    assert result["forecast"]["daily_forecast"]["precipitation_sum"] == [1.5, None, None]


def test_missing_or_misaligned_probability_is_not_treated_as_zero(monkeypatch):
    for probability_values in (None, [10]):
        forecast = {"source": "isolated test fixture", "daily_forecast": {
            "time": ["2026-01-01", "2026-01-02"],
            "temperature_2m_max": [20, 21],
            "precipitation_sum": [0, 0],
        }}
        if probability_values is not None:
            forecast["daily_forecast"]["precipitation_probability_max"] = probability_values
        monkeypatch.setattr(
            weather_agent_module, "get_weather_forecast", Mock(return_value=forecast)
        )

        result = weather_agent_module.weather_agent(31.22, 75.75, knowledge_searcher=Mock(return_value=[]), llm_json=Mock())

        assert result["forecast"]["daily_forecast"]["precipitation_probability_max"] == [None, None]


@pytest.mark.parametrize(
    ("temperature", "alerted"),
    [(34.9, False), (35, True), (35.1, True)],
)
def test_temperature_indicator_uses_existing_threshold(monkeypatch, temperature, alerted):
    result = _run_one_day_weather(monkeypatch, temperature=temperature)

    assert any(risk["risk"] == "High temperature" for risk in result["identified_risks"]) is alerted


@pytest.mark.parametrize(
    ("rainfall", "alerted"),
    [(19.9, False), (20, True), (20.1, True)],
)
def test_rainfall_indicator_uses_existing_threshold(monkeypatch, rainfall, alerted):
    result = _run_one_day_weather(monkeypatch, rainfall=rainfall)

    assert any(risk["risk"] == "Heavy rainfall" for risk in result["identified_risks"]) is alerted


@pytest.mark.parametrize(
    ("probability", "alerted"),
    [(59.9, False), (60, True), (60.1, True)],
)
def test_probability_indicator_uses_existing_threshold(monkeypatch, probability, alerted):
    result = _run_one_day_weather(monkeypatch, probability=probability)

    assert any(risk["risk"] == "Possible rainfall" for risk in result["identified_risks"]) is alerted


@pytest.mark.parametrize("value", [None, "unknown", float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize("field", ["temperature", "rainfall", "probability"])
def test_unavailable_weather_values_do_not_generate_risk_alerts(monkeypatch, field, value):
    arguments = {field: value}
    result = _run_one_day_weather(monkeypatch, **arguments)

    alert_name = {
        "temperature": "High temperature",
        "rainfall": "Heavy rainfall",
        "probability": "Possible rainfall",
    }[field]
    assert not any(risk["risk"] == alert_name for risk in result["identified_risks"])


def test_weather_response_explains_the_forecast_is_an_early_estimate(monkeypatch):
    result = _run_one_day_weather(monkeypatch, temperature=35)

    note = result["risk_interpretation_note"]
    assert "estimated from the forecast" in note
    assert "actual field conditions" in note
