
from semantic_kernel import Kernel

from agents.farm_agents_plugin import FarmAgentsPlugin


def test_farm_agents_plugin_registration():

    kernel = Kernel()

    kernel.add_plugin(
        FarmAgentsPlugin(),
        plugin_name="FarmAgents"
    )

    expected_functions = {
        "get_weather_advisory",
        "get_soil_advisory",
        "get_pest_disease_advisory",
        "get_irrigation_advisory"
    }

    assert "FarmAgents" in kernel.plugins

    functions = kernel.plugins["FarmAgents"].functions

    assert set(functions.keys()) == expected_functions

    print("\nALL FOUR FARM AGENT FUNCTIONS REGISTERED SUCCESSFULLY")
