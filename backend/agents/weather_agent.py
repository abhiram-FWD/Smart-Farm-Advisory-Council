
import math

from tools.weather_tool import get_weather_forecast


def weather_agent(latitude: float, longitude: float):
    """
    Weather Agent:
    Fetches forecast data and identifies basic weather risks.
    """

    forecast = get_weather_forecast(latitude, longitude)

    if forecast.get("error"):
        return {
            "agent": "Weather Agent",
            "status": "failed",
            "error": forecast["error"]
        }

    daily = forecast.get("daily_forecast", {})

    required_fields = [
        "time",
        "temperature_2m_max",
    ]

    if any(not isinstance(daily.get(field), list) for field in required_fields):
        return {
            "agent": "Weather Agent",
            "status": "failed",
            "error": "Required daily weather data is missing."
        }

    dates = daily["time"]
    maximum_temperatures = daily["temperature_2m_max"]

    if len(dates) != len(maximum_temperatures):
        return {
            "agent": "Weather Agent",
            "status": "failed",
            "error": "Weather forecast date and temperature arrays have inconsistent lengths."
        }

    raw_rainfall = daily.get("precipitation_sum")
    if isinstance(raw_rainfall, list) and len(raw_rainfall) == len(dates):
        rainfall_values = [
            value if (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
                and value >= 0
            ) else None
            for value in raw_rainfall
        ]
    else:
        rainfall_values = [None] * len(dates)
    daily["precipitation_sum"] = rainfall_values

    raw_probabilities = daily.get("precipitation_probability_max")
    if isinstance(raw_probabilities, list) and len(raw_probabilities) == len(dates):
        probabilities = [
            value if (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
                and 0 <= value <= 100
            ) else None
            for value in raw_probabilities
        ]
    else:
        probabilities = [None] * len(dates)
    daily["precipitation_probability_max"] = probabilities

    risks = []

    for index, date in enumerate(dates):

        max_temp = maximum_temperatures[index]
        rainfall = rainfall_values[index]

        if (
            isinstance(max_temp, (int, float))
            and not isinstance(max_temp, bool)
            and math.isfinite(max_temp)
            and max_temp >= 35
        ):
            risks.append({
                "date": date,
                "risk": "High temperature",
                "severity": "High"
            })

        if isinstance(rainfall, (int, float)) and rainfall >= 20:
            risks.append({
                "date": date,
                "risk": "Heavy rainfall",
                "severity": "High"
            })

        elif index < len(probabilities):

            rain_probability = probabilities[index]

            if (
                isinstance(rain_probability, (int, float))
                and rain_probability >= 60
            ):
                risks.append({
                    "date": date,
                    "risk": "Possible rainfall",
                    "severity": "Medium"
                })

    return {
        "agent": "Weather Agent",
        "forecast": forecast,
        "identified_risks": risks,
        "risk_interpretation_note": (
            "These thresholds are preliminary project indicators, not "
            "universal agricultural thresholds, not verified crop-specific "
            "warnings, and not professional agricultural advice."
        ),
        "status": "completed"
    }
