
SCENARIOS = [
    {
        "id": "S01",
        "name": "Low moisture with no expected rain",
        "category": "irrigation",
        "input": {
            "moisture": 15, "ph": 6.5,
            "nitrogen": 60, "phosphorus": 30, "potassium": 30,
            "crop_name": "Wheat", "growth_stage": "Vegetative",
            "symptoms": [], "expected_rainfall": 0
        },
        "expected": {
            "risk": "Low soil moisture",
            "action": "irrigation"
        }
    },
    {
        "id": "S02",
        "name": "Low moisture with rain expected",
        "category": "irrigation",
        "input": {
            "moisture": 20, "ph": 6.5,
            "nitrogen": 60, "phosphorus": 30, "potassium": 30,
            "crop_name": "Wheat", "growth_stage": "Vegetative",
            "symptoms": [], "expected_rainfall": 25
        },
        "expected": {
            "risk": "Low soil moisture",
            "action": "recheck_before_irrigation"
        }
    },
    {
        "id": "S03",
        "name": "Adequate moisture with rain expected",
        "category": "irrigation",
        "input": {
            "moisture": 55, "ph": 6.5,
            "nitrogen": 60, "phosphorus": 30, "potassium": 30,
            "crop_name": "Wheat", "growth_stage": "Vegetative",
            "symptoms": [], "expected_rainfall": 30
        },
        "expected": {
            "risk": None,
            "action": "postpone_irrigation"
        }
    },
    {
        "id": "S04",
        "name": "Adequate moisture without rain",
        "category": "irrigation",
        "input": {
            "moisture": 60, "ph": 6.5,
            "nitrogen": 60, "phosphorus": 30, "potassium": 30,
            "crop_name": "Wheat", "growth_stage": "Vegetative",
            "symptoms": [], "expected_rainfall": 0
        },
        "expected": {
            "risk": None,
            "action": "no_immediate_irrigation"
        }
    },
    {
        "id": "S05",
        "name": "Preliminary acidic pH and moisture indicators",
        "category": "soil",
        "input": {
            "moisture": 20, "ph": 5.0,
            "nitrogen": 25, "phosphorus": 30, "potassium": 30,
            "crop_name": "Wheat", "growth_stage": "Vegetative",
            "symptoms": [], "expected_rainfall": 0
        },
        "expected": {
            "risks": [
                "Low soil moisture",
                "Soil may be too acidic"
            ]
        }
    },
    {
        "id": "S06",
        "name": "Preliminary alkaline pH indicator",
        "category": "soil",
        "input": {
            "moisture": 55, "ph": 8.0,
            "nitrogen": 60, "phosphorus": 10, "potassium": 30,
            "crop_name": "Wheat", "growth_stage": "Vegetative",
            "symptoms": [], "expected_rainfall": 0
        },
        "expected": {
            "risks": ["Soil may be too alkaline"]
        }
    },
    {
        "id": "S07",
        "name": "Preliminary soil moisture indicator",
        "category": "soil",
        "input": {
            "moisture": 20, "ph": 6.5,
            "nitrogen": 60, "phosphorus": 30, "potassium": 10,
            "crop_name": "Wheat", "growth_stage": "Vegetative",
            "symptoms": [], "expected_rainfall": 0
        },
        "expected": {
            "risks": [
                "Low soil moisture"
            ]
        }
    },
    {
        "id": "S08",
        "name": "Wheat with yellow leaves and wilting",
        "category": "crop_health",
        "input": {
            "moisture": 35, "ph": 6.5,
            "nitrogen": 50, "phosphorus": 25, "potassium": 25,
            "crop_name": "Wheat", "growth_stage": "Vegetative",
            "symptoms": ["yellow leaves", "wilting"],
            "expected_rainfall": 0
        },
        "expected": {
            "rag_required": True,
            "expert_inspection": True
        }
    },
    {
        "id": "S09",
        "name": "Rice with leaf damage and brown spots",
        "category": "crop_health",
        "input": {
            "moisture": 45, "ph": 6.5,
            "nitrogen": 50, "phosphorus": 25, "potassium": 25,
            "crop_name": "Rice", "growth_stage": "Tillering",
            "symptoms": ["leaf damage", "brown spots"],
            "expected_rainfall": 0
        },
        "expected": {
            "rag_required": True,
            "expert_inspection": True
        }
    },
    {
        "id": "S10",
        "name": "Repeated observations and farm-history memory",
        "category": "farm_memory",
        "input": {
            "moisture": 35, "ph": 6.2,
            "nitrogen": 45, "phosphorus": 25, "potassium": 30,
            "crop_name": "Wheat", "growth_stage": "Vegetative",
            "symptoms": ["yellow leaves"],
            "expected_rainfall": 0
        },
        "previous_observations": [
            {
                "moisture": 20,
                "ph": 5.0,
                "nitrogen": 30,
                "phosphorus": 15,
                "potassium": 25,
                "crop_name": "Wheat",
                "growth_stage": "Vegetative",
                "symptoms": ["yellow leaves", "wilting"]
            }
        ],
        "expected": {
            "historical_context_available": True,
            "historical_context_used": True
        }
    }
]


def get_all_scenarios():
    return SCENARIOS


def get_scenario_by_id(scenario_id):
    for scenario in SCENARIOS:
        if scenario["id"] == scenario_id:
            return scenario

    raise ValueError(f"Scenario not found: {scenario_id}")
