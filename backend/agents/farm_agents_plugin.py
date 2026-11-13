
from typing import Any

from semantic_kernel.functions import kernel_function

from agents.weather_agent import weather_agent
from agents.soil_agent import soil_agent
from agents.crop_health_agent import crop_health_agent
from agents.irrigation_agent import irrigation_agent


class FarmAgentsPlugin:
    """
    Semantic Kernel plugin exposing specialist farm agents.
    """

    @kernel_function(
        name="get_weather_advisory",
        description="Fetch weather forecast and identify weather risks."
    )
    def get_weather_advisory(
        self,
        latitude: float,
        longitude: float
    ) -> dict:

        return weather_agent(latitude, longitude)

    @kernel_function(
        name="get_soil_advisory",
        description="Analyse soil readings and historical soil trends."
    )
    def get_soil_advisory(
        self,
        soil_moisture: float,
        soil_ph: float,
        nitrogen: float,
        phosphorus: float,
        potassium: float,
        historical_context: str = "",
        crop_name: str = ""
    ) -> dict:

        return soil_agent(
            soil_moisture,
            soil_ph,
            nitrogen,
            phosphorus,
            potassium,
            historical_context=historical_context,
            crop_name=crop_name,
        )

    @kernel_function(
        name="get_pest_disease_advisory",
        description="Analyse crop symptoms using agricultural evidence and farm history."
    )
    def get_pest_disease_advisory(
        self,
        crop_name: str,
        growth_stage: str,
        symptoms: list[str],
        historical_context: str = ""
    ) -> dict:

        return crop_health_agent(
            crop_name,
            growth_stage,
            symptoms,
            historical_context=historical_context
        )

    @kernel_function(
        name="get_irrigation_advisory",
        description="Generate an irrigation recommendation using soil moisture and rainfall."
    )
    def get_irrigation_advisory(
        self,
        soil_moisture: float,
        expected_rainfall: Any,
        crop_name: str,
        precipitation_probability_max: Any = None,
    ) -> dict:

        return irrigation_agent(
            soil_moisture=soil_moisture,
            expected_rainfall=expected_rainfall,
            crop_name=crop_name,
            precipitation_probability_max=precipitation_probability_max,
        )
