
import math
import os
import time
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

MET_NORWAY_URL = (
    "https://api.met.no/weatherapi/locationforecast/2.0/compact"
)

MET_NORWAY_USER_AGENT = os.getenv("MET_NORWAY_USER_AGENT", "AgriVision/1.0")


def get_open_meteo_forecast(latitude, longitude):
    """Fetch forecast from Open-Meteo."""

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": [
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_sum",
            "precipitation_probability_max"
        ],
        "current": [
            "temperature_2m", "relative_humidity_2m", "precipitation",
            "weather_code", "wind_speed_10m",
        ],
        "timezone": "auto",
        "past_days": 1,
        "forecast_days": 7,
    }

    response = requests.get(
        OPEN_METEO_URL,
        params=params,
        timeout=20
    )

    response.raise_for_status()

    data = response.json()
    daily = data.get("daily")
    current = data.get("current")

    if not isinstance(daily, dict):
        raise ValueError("Invalid Open-Meteo daily forecast")

    required_fields = [
        "time",
        "temperature_2m_max",
        "temperature_2m_min",
        "precipitation_sum",
        "precipitation_probability_max"
    ]

    for field in required_fields:
        if not isinstance(daily.get(field), list):
            raise ValueError(f"Missing forecast field: {field}")

    # Keep the last completed local calendar day as observed rainfall and
    # exclude it from the forward forecast arrays.
    dates = daily["time"]
    today = (current or {}).get("time", "")[:10]
    previous_indices = [index for index, value in enumerate(dates) if isinstance(value, str) and value < today]
    recent_rainfall = None
    forecast_indices = list(range(len(dates)))
    if previous_indices:
        recent_index = previous_indices[-1]
        rainfall = daily["precipitation_sum"][recent_index]
        if isinstance(rainfall, (int, float)) and not isinstance(rainfall, bool) and math.isfinite(rainfall) and rainfall >= 0:
            recent_rainfall = {
                "date": dates[recent_index],
                "precipitation_mm": rainfall,
                "source": "Open-Meteo historical daily precipitation",
            }
        forecast_indices = [index for index, value in enumerate(dates) if isinstance(value, str) and value >= today]
    forecast_daily = {
        key: [values[index] for index in forecast_indices]
        if isinstance(values, list) and len(values) == len(dates) else values
        for key, values in daily.items()
    }

    return {
        "location": {
            "latitude": latitude,
            "longitude": longitude
        },
        "daily_forecast": forecast_daily,
        "recent_observed_rainfall": recent_rainfall,
        "current_conditions": current if isinstance(current, dict) else None,
        "source": "Open-Meteo"
    }


def get_met_norway_forecast(latitude, longitude):
    """Fetch and normalize MET Norway forecast data."""

    headers = {
        "User-Agent": MET_NORWAY_USER_AGENT
    }

    params = {
        "lat": round(latitude, 4),
        "lon": round(longitude, 4)
    }

    response = requests.get(
        MET_NORWAY_URL,
        params=params,
        headers=headers,
        timeout=25
    )

    response.raise_for_status()

    data = response.json()

    timeseries = data.get("properties", {}).get("timeseries", [])

    if not timeseries:
        raise ValueError("MET Norway returned no forecast data")

    parsed_series = []
    for item in timeseries:
        timestamp = item.get("time") if isinstance(item, dict) else None
        details = item.get("data", {}) if isinstance(item, dict) else {}
        if not isinstance(timestamp, str) or not isinstance(details, dict):
            continue
        try:
            parsed_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if parsed_time.tzinfo is None:
                continue
            parsed_time = parsed_time.astimezone(timezone.utc)
        except (TypeError, ValueError, OverflowError):
            continue
        parsed_series.append((parsed_time, details))

    parsed_series.sort(key=lambda entry: entry[0])
    if not parsed_series:
        raise ValueError("MET Norway forecast could not be normalized")

    # MET Norway timestamps are UTC. Without a timezone identifier in this
    # response, use UTC calendar days consistently and disclose that policy.
    daily_data = {}
    for timestamp, details in parsed_series:
        date = timestamp.date().isoformat()
        values = daily_data.setdefault(date, {
            "temperatures": [],
            "precipitation_intervals": [],
            "rainfall_unavailable": False,
        })

        instant = details.get("instant", {})
        instant_details = instant.get("details", {}) if isinstance(instant, dict) else {}
        temperature = instant_details.get("air_temperature")
        if (
            isinstance(temperature, (int, float))
            and not isinstance(temperature, bool)
            and math.isfinite(temperature)
        ):
            values["temperatures"].append(temperature)

    def mark_unavailable(start, end):
        """Mark every UTC date touched by an interval as unsafe to total."""
        current_date = start.date()
        final_date = (end - timedelta(microseconds=1)).date()
        while current_date <= final_date:
            daily_data.setdefault(current_date.isoformat(), {
                "temperatures": [],
                "precipitation_intervals": [],
                "rainfall_unavailable": False,
            })["rainfall_unavailable"] = True
            current_date += timedelta(days=1)

    # A MET Norway next_X_hours amount covers the period beginning at its
    # timestamp. Match X to the next timestamp gap so overlapping 1/6/12-hour
    # summaries are never added together and irregular gaps remain unavailable.
    period_hours = (1, 6, 12)
    for index, (start, details) in enumerate(parsed_series[:-1]):
        end = parsed_series[index + 1][0]
        if end <= start:
            mark_unavailable(start, start + timedelta(microseconds=1))
            continue

        duration = end - start
        hours = next((value for value in period_hours
                      if duration == timedelta(hours=value)), None)
        if hours is None:
            mark_unavailable(start, end)
            continue

        interval = details.get(f"next_{hours}_hours")
        interval_details = interval.get("details", {}) if isinstance(interval, dict) else {}
        precipitation = interval_details.get("precipitation_amount")
        valid_precipitation = (
            isinstance(precipitation, (int, float))
            and not isinstance(precipitation, bool)
            and math.isfinite(precipitation)
            and precipitation >= 0
        )

        # A period crossing midnight cannot be split accurately from its
        # aggregate amount, so retain None for every affected daily total.
        if start.date() != (end - timedelta(microseconds=1)).date():
            mark_unavailable(start, end)
            continue
        if not valid_precipitation:
            mark_unavailable(start, end)
            continue

        daily_data[start.date().isoformat()]["precipitation_intervals"].append(
            (start, end, precipitation)
        )

    dates = sorted(daily_data.keys())[:7]

    daily_forecast = {
        "time": dates,
        "temperature_2m_max": [],
        "temperature_2m_min": [],
        "precipitation_sum": [],
        "precipitation_probability_max": []
    }

    for date in dates:

        values = daily_data[date]
        temperatures = values["temperatures"]

        daily_forecast["temperature_2m_max"].append(max(temperatures) if temperatures else None)
        daily_forecast["temperature_2m_min"].append(min(temperatures) if temperatures else None)

        intervals = sorted(values["precipitation_intervals"], key=lambda item: item[0])
        day_start = datetime.fromisoformat(date).replace(tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        covered_until = day_start
        complete_day = not values["rainfall_unavailable"]
        rainfall_total = 0.0
        for interval_start, interval_end, amount in intervals:
            if interval_start != covered_until or interval_end > day_end:
                complete_day = False
                break
            rainfall_total += amount
            covered_until = interval_end
        if covered_until != day_end:
            complete_day = False
        daily_rainfall = round(rainfall_total, 2) if complete_day else None
        daily_forecast["precipitation_sum"].append(daily_rainfall)

        # MET Norway compact response does not provide
        # precipitation probability in this endpoint.
        daily_forecast["precipitation_probability_max"].append(None)

    instant = parsed_series[0][1].get("instant")
    current_details = instant.get("details", {}) if isinstance(instant, dict) else {}
    current = {
        "time": parsed_series[0][0].isoformat(),
        "temperature": current_details.get("air_temperature"),
        "relative_humidity": current_details.get("relative_humidity"),
        "wind_speed": current_details.get("wind_speed"),
    }
    return {
        "location": {
            "latitude": latitude,
            "longitude": longitude
        },
        "daily_forecast": daily_forecast,
        "current_conditions": current,
        "source": "MET Norway",
        "note": (
            "Daily summaries use UTC calendar days and are derived from "
            "non-overlapping forecast intervals. "
            "Precipitation probability is not available. Current conditions "
            "are the first provider forecast period, not an independent measurement."
        )
    }


def aggregate_rainfall_if_complete(daily_rainfall, days=3):
    """Sum a complete forecast window, preserving any unavailable value as None."""
    if not isinstance(daily_rainfall, list) or len(daily_rainfall) < days:
        return None
    values = daily_rainfall[:days]
    if any(
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
        or value < 0
        for value in values
    ):
        return None
    return sum(values)


def get_weather_forecast(latitude: float, longitude: float):
    """
    Fetch live weather data.

    Primary provider: Open-Meteo
    Fallback provider: MET Norway
    """

    open_meteo_error = None

    for attempt in range(2):

        try:
            result = get_open_meteo_forecast(latitude, longitude)
            result["fetched_at"] = datetime.now(timezone.utc).isoformat()
            return result

        except (requests.RequestException, ValueError) as error:

            open_meteo_error = str(error)

            if attempt == 0:
                time.sleep(1)

    try:
        result = get_met_norway_forecast(latitude, longitude)

        result["fallback_used"] = True
        result["primary_provider_error"] = "Primary provider unavailable; fallback forecast supplied."
        result["fetched_at"] = datetime.now(timezone.utc).isoformat()

        return result

    except (requests.RequestException, ValueError):

        return {
            "error": "Weather forecast providers are temporarily unavailable."
        }
