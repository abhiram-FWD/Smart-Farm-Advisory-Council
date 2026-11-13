from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from tools.weather_tool import aggregate_rainfall_if_complete, get_weather_forecast


def _install_met_timeseries(monkeypatch, timeseries):
    """Install an isolated MET response; this fixture never calls the API."""
    import tools.weather_tool as weather_tool

    response = Mock()
    response.json.return_value = {"properties": {"timeseries": timeseries}}
    response.raise_for_status.return_value = None
    monkeypatch.setattr(weather_tool.requests, "get", Mock(return_value=response))
    return weather_tool


def _met_item(timestamp, precipitation=1, extra_periods=None):
    periods = {"next_6_hours": {"details": {"precipitation_amount": precipitation}}}
    periods.update(extra_periods or {})
    return {
        "time": timestamp,
        "data": {
            "instant": {"details": {"air_temperature": 10}},
            **periods,
        },
    }


def test_weather_forecast_normalizes_stubbed_primary_provider(monkeypatch):
    daily = {
        "time": ["2026-01-01"],
        "temperature_2m_max": [25],
        "temperature_2m_min": [12],
        "precipitation_sum": [1.2],
        "precipitation_probability_max": [20],
    }
    response = Mock()
    response.json.return_value = {"daily": daily}
    response.raise_for_status.return_value = None
    request = Mock(return_value=response)
    monkeypatch.setattr("tools.weather_tool.requests.get", request)

    result = get_weather_forecast(31.22, 75.77)

    assert result["source"] == "Open-Meteo"
    assert result["daily_forecast"] == daily
    assert result["location"] == {"latitude": 31.22, "longitude": 75.77}
    request.assert_called_once()


def test_weather_forecast_uses_stubbed_fallback_without_network(monkeypatch):
    from requests import RequestException
    import tools.weather_tool as weather_tool

    primary = Mock(side_effect=RequestException("isolated primary failure"))
    fallback = Mock(return_value={
        "source": "MET Norway",
        "daily_forecast": {
            "time": ["2026-01-01"],
            "temperature_2m_max": [20],
            "temperature_2m_min": [10],
            "precipitation_sum": [0],
            "precipitation_probability_max": [None],
        },
    })
    monkeypatch.setattr(weather_tool, "get_open_meteo_forecast", primary)
    monkeypatch.setattr(weather_tool, "get_met_norway_forecast", fallback)
    monkeypatch.setattr(weather_tool.time, "sleep", Mock())

    result = get_weather_forecast(31.22, 75.77)

    assert result["source"] == "MET Norway"
    assert result["fallback_used"] is True
    assert result["primary_provider_error"] == "Primary provider unavailable; fallback forecast supplied."
    assert primary.call_count == 2
    fallback.assert_called_once_with(31.22, 75.77)


def test_met_norway_missing_interval_rainfall_remains_unavailable(monkeypatch):
    import tools.weather_tool as weather_tool

    response = Mock()
    response.json.return_value = {"properties": {"timeseries": [{
        "time": "2026-01-01T00:00:00Z",
        "data": {"instant": {"details": {"air_temperature": 10}}},
    }]}}
    response.raise_for_status.return_value = None
    monkeypatch.setattr(weather_tool.requests, "get", Mock(return_value=response))

    result = weather_tool.get_met_norway_forecast(31.22, 75.75)

    assert result["daily_forecast"]["precipitation_sum"] == [None]
    assert result["daily_forecast"]["precipitation_probability_max"] == [None]


def test_met_timestamps_are_normalized_to_utc_calendar_dates(monkeypatch):
    weather_tool = _install_met_timeseries(monkeypatch, [
        _met_item("2026-01-02T00:00:00+01:00"),
        _met_item("2026-01-02T06:00:00+01:00"),
    ])

    result = weather_tool.get_met_norway_forecast(31.22, 75.75)

    assert result["daily_forecast"]["time"] == ["2026-01-01", "2026-01-02"]
    assert result["daily_forecast"]["precipitation_sum"] == [None, None]
    assert "UTC calendar days" in result["note"]


def test_met_interval_crossing_utc_midnight_leaves_both_daily_totals_unavailable(monkeypatch):
    weather_tool = _install_met_timeseries(monkeypatch, [
        _met_item("2026-01-01T18:00:00Z", precipitation=2),
        _met_item("2026-01-02T00:00:00Z", precipitation=3),
        _met_item("2026-01-02T06:00:00Z", precipitation=4),
    ])

    result = weather_tool.get_met_norway_forecast(31.22, 75.75)

    assert result["daily_forecast"]["time"] == ["2026-01-01", "2026-01-02"]
    assert result["daily_forecast"]["precipitation_sum"] == [None, None]


def test_met_missing_interval_precipitation_keeps_daily_total_unavailable(monkeypatch):
    timeseries = [
        _met_item("2026-01-01T00:00:00Z", 1),
        _met_item("2026-01-01T06:00:00Z", None),
        _met_item("2026-01-01T12:00:00Z", 3),
        _met_item("2026-01-01T18:00:00Z", 4),
        _met_item("2026-01-02T00:00:00Z", 5),
    ]
    timeseries[1]["data"]["next_6_hours"]["details"].pop("precipitation_amount")
    weather_tool = _install_met_timeseries(monkeypatch, timeseries)

    result = weather_tool.get_met_norway_forecast(31.22, 75.75)

    assert result["daily_forecast"]["precipitation_sum"] == [None, None]


def test_met_irregular_interval_duration_keeps_daily_total_unavailable(monkeypatch):
    weather_tool = _install_met_timeseries(monkeypatch, [
        _met_item("2026-01-01T00:00:00Z", precipitation=1),
        _met_item("2026-01-01T03:00:00Z", precipitation=2),
        _met_item("2026-01-01T09:00:00Z", precipitation=3),
    ])

    result = weather_tool.get_met_norway_forecast(31.22, 75.75)

    assert result["daily_forecast"]["precipitation_sum"] == [None]


def test_met_overlapping_period_summaries_are_not_double_counted(monkeypatch):
    timeseries = []
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for hour in range(25):
        timestamp = start + timedelta(hours=hour)
        timeseries.append(_met_item(
            timestamp.isoformat().replace("+00:00", "Z"),
            precipitation=1,
            extra_periods={
                "next_1_hours": {"details": {"precipitation_amount": 1}},
                "next_6_hours": {"details": {"precipitation_amount": 6}},
                "next_12_hours": {"details": {"precipitation_amount": 12}},
            },
        ))
    weather_tool = _install_met_timeseries(monkeypatch, timeseries)

    result = weather_tool.get_met_norway_forecast(31.22, 75.75)

    assert result["daily_forecast"]["precipitation_sum"] == [24, None]


def test_met_complete_six_hour_intervals_produce_daily_total(monkeypatch):
    weather_tool = _install_met_timeseries(monkeypatch, [
        _met_item("2026-01-01T00:00:00Z", 1),
        _met_item("2026-01-01T06:00:00Z", 2),
        _met_item("2026-01-01T12:00:00Z", 3),
        _met_item("2026-01-01T18:00:00Z", 4),
        _met_item("2026-01-02T00:00:00Z", 5),
    ])

    result = weather_tool.get_met_norway_forecast(31.22, 75.75)

    assert result["daily_forecast"]["precipitation_sum"] == [10, None]


def test_three_day_rainfall_total_requires_three_complete_finite_values():
    assert aggregate_rainfall_if_complete([1, 2.5, 0]) == 3.5
    assert aggregate_rainfall_if_complete([None, 2, 3]) is None
    assert aggregate_rainfall_if_complete([1, "missing", 3]) is None
    assert aggregate_rainfall_if_complete([1, float("nan"), 3]) is None
    assert aggregate_rainfall_if_complete([1, 2]) is None
