import json


def format_farm_history(history):
    """Convert farm observations into readable agent context."""

    if not history:
        return ""

    formatted_observations = []

    for index, record in enumerate(history, start=1):
        observation = record.get("observation", {})

        if not isinstance(observation, dict):
            continue

        created_at = record.get("created_at")
        if hasattr(created_at, "isoformat"):
            created_at = created_at.isoformat()

        formatted_observations.append({
            "observation_number": index,
            "recorded_at": str(created_at) if created_at else "Unknown",
            "crop_name": observation.get("crop_name"),
            "growth_stage": observation.get("growth_stage"),
            "soil_moisture": observation.get("soil_moisture"),
            "soil_ph": observation.get("soil_ph"),
            "nitrogen": observation.get("nitrogen"),
            "phosphorus": observation.get("phosphorus"),
            "potassium": observation.get("potassium"),
            "symptoms": observation.get("symptoms", [])
        })

    if not formatted_observations:
        return ""

    return json.dumps(formatted_observations, indent=2, default=str)
