
def get_crop_report(
    crop_name: str,
    growth_stage: str,
    symptoms: list
):
    """
    Reads crop condition information supplied by the farmer.
    """

    return {
        "crop_name": crop_name,
        "growth_stage": growth_stage,
        "symptoms": symptoms,
        "source": "Farm Crop Observation"
    }
