
import math


def irrigation_agent(
    soil_moisture: float,
    expected_rainfall: float,
    crop_name: str,
    precipitation_probability_max=None,
):
    """
    Irrigation Planner:
    Uses soil moisture and forecast rainfall
    to suggest an irrigation action.

    Preliminary demonstration rules only.
    """

    valid_moisture = (
        isinstance(soil_moisture, (int, float))
        and not isinstance(soil_moisture, bool)
        and math.isfinite(soil_moisture)
    )
    valid_rainfall = (
        isinstance(expected_rainfall, (int, float))
        and not isinstance(expected_rainfall, bool)
        and math.isfinite(expected_rainfall)
        and expected_rainfall >= 0
    )

    probability_values = None
    if isinstance(precipitation_probability_max, list):
        normalized_probabilities = [
            value if (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
                and 0 <= value <= 100
            ) else None
            for value in precipitation_probability_max[:3]
        ]
        normalized_probabilities.extend(
            [None] * (3 - len(normalized_probabilities))
        )
        if any(value is not None for value in normalized_probabilities):
            probability_values = normalized_probabilities

    if not valid_moisture or not valid_rainfall:
        action = "Irrigation guidance unavailable"
        reason = (
            "Soil moisture or the three-day rainfall forecast is unavailable. "
            "Check current soil conditions and a local forecast before deciding."
        )

    elif soil_moisture < 30 and expected_rainfall < 5:
        action = "Consider irrigation"
        reason = (
            "The forecast shows less than 5 mm over the next three days. "
            "If current soil checks confirm low moisture, irrigation may be considered."
        )

    elif soil_moisture < 30 and expected_rainfall >= 5:
        action = "Recheck before irrigating"
        reason = (
            "The forecast reaches at least 5 mm; recheck soil moisture and "
            "local conditions before deciding whether to irrigate."
        )

    elif soil_moisture >= 30 and expected_rainfall >= 5:
        action = "Consider postponing irrigation"
        reason = (
            "The forecast reaches at least 5 mm and submitted moisture is "
            "above the preliminary threshold; reassess conditions before postponing."
        )

    else:
        action = "No immediate irrigation indicated"
        reason = (
            "Submitted moisture is above the preliminary threshold; check "
            "current field conditions before deciding."
        )

    if not valid_rainfall:
        forecast_uncertainty = (
            "The rainfall forecast amount is unavailable; no rainfall amount is assumed."
        )
    else:
        forecast_uncertainty = "Forecast rainfall is uncertain and may not occur as predicted."

    if probability_values is None:
        probability_note = "Precipitation probability is unavailable; no probability is assumed."
    else:
        daily_probabilities = ", ".join(
            f"day {index + 1}: {value}%" if value is not None
            else f"day {index + 1}: unavailable"
            for index, value in enumerate(probability_values)
        )
        probability_note = (
            "Daily precipitation probability forecasts ("
            f"{daily_probabilities}) are uncertain and do not guarantee rainfall."
        )

    reason = f"{reason} {forecast_uncertainty} {probability_note}"

    return {
        "agent": "Irrigation Planner",
        "crop": crop_name,
        "soil_moisture": soil_moisture,
        "expected_rainfall_mm": expected_rainfall,
        "forecast_precipitation_probability_max": probability_values,
        "recommended_action": action,
        "reason": reason,
        "guidance_type": "preliminary_demonstration_guidance",
        "guidance_note": (
            "This is preliminary demonstration guidance, not a farm-specific "
            "irrigation prescription. A reliable decision needs crop growth "
            "stage, soil type, actual recent rainfall, crop water demand and "
            "local conditions."
        ),
        "status": "completed"
    }
