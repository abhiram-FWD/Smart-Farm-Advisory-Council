from agents import coordinator


def test_farm_coordination_uses_isolated_agent_results(monkeypatch):
    forecast = {
        "daily_forecast": {
            "precipitation_sum": [0, 1, 2],
            "precipitation_probability_max": [20, 40, 60],
        },
        "source": "isolated test fixture",
    }
    monkeypatch.setattr(coordinator, "weather_agent", lambda *args: {
        "status": "completed", "forecast": forecast, "identified_risks": [],
    })
    monkeypatch.setattr(coordinator, "soil_agent", lambda *args: {
        "status": "completed", "identified_risks": [], "recommendations": [],
    })
    monkeypatch.setattr(coordinator, "crop_health_agent", lambda *args: {
        "status": "success", "possible_pest_risks": [], "possible_disease_risks": [],
    })
    irrigation_calls = []
    def irrigation_fixture(*args):
        irrigation_calls.append(args)
        return {"status": "completed", "recommended_action": "fixture action"}
    monkeypatch.setattr(coordinator, "irrigation_agent", irrigation_fixture)

    result = coordinator.run_farm_coordination(
        31.22, 75.77, 20, 5.0, 30, 15, 25,
        "Wheat", "Vegetative", ["Yellow leaves", "Wilting"],
    )

    assert result["status"] == "completed"
    assert set(result["agents"]) == {"weather", "soil", "crop_health", "irrigation"}
    assert result["expected_rainfall_next_3_days_mm"] == 3
    assert irrigation_calls[0][3] == [20, 40, 60]


def test_incomplete_rainfall_reaches_planner_as_unavailable(monkeypatch):
    monkeypatch.setattr(coordinator, "weather_agent", lambda *args: {
        "status": "completed",
        "forecast": {"daily_forecast": {"precipitation_sum": [None, 4, 2]}},
    })
    monkeypatch.setattr(coordinator, "soil_agent", lambda *args: {"status": "completed"})
    monkeypatch.setattr(coordinator, "crop_health_agent", lambda *args: {"status": "success"})

    result = coordinator.run_farm_coordination(
        31.22, 75.75, 20, 6.5, 10, 10, 10, "Wheat", "Vegetative", [],
    )

    assert result["expected_rainfall_next_3_days_mm"] is None
    assert result["agents"]["irrigation"]["recommended_action"] == "Check local forecast before deciding"
