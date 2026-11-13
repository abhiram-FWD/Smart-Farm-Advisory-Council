
def get_soil_report(
    moisture: float,
    ph: float,
    nitrogen: float,
    phosphorus: float,
    potassium: float
):
    """
    Reads structured soil report data.
    """

    return {
        "moisture": moisture,
        "ph": ph,
        "nitrogen": nitrogen,
        "phosphorus": phosphorus,
        "potassium": potassium,
        "source": "Farm Soil Report"
    }
