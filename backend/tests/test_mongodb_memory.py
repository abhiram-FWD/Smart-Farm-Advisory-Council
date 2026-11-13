import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pymongo import MongoClient

from memory import mongodb_memory


@pytest.fixture
def disposable_memory(monkeypatch):
    uri = os.getenv("AGRIVISION_TEST_MONGODB_URI")
    db_name = os.getenv("AGRIVISION_TEST_DB_NAME")
    if not uri or not db_name:
        pytest.skip("Disposable MongoDB integration settings are not configured.")
    if db_name != "agrivision_test_db":
        pytest.fail("Integration tests require the isolated agrivision_test_db database.")

    test_client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    test_database = test_client[db_name]
    monkeypatch.setattr(mongodb_memory, "database", test_database)
    monkeypatch.setattr(mongodb_memory, "farms_collection", test_database["farms"])
    monkeypatch.setattr(mongodb_memory, "observations_collection", test_database["farm_observations"])
    monkeypatch.setattr(mongodb_memory, "advisories_collection", test_database["advisories"])
    try:
        yield test_database
    finally:
        test_client.close()


def test_mongodb_memory_round_trip_in_disposable_database(disposable_memory):
    farm_id = f"test-farm-{uuid4()}"
    observation = {
        "crop_name": "Wheat",
        "growth_stage": "Vegetative",
        "soil_moisture": 25,
        "soil_ph": 6.2,
        "nitrogen": 45,
        "phosphorus": 30,
        "potassium": 35,
        "symptoms": ["yellow leaves"],
    }

    try:
        mongodb_memory.initialize_memory()
        observation_id = mongodb_memory.save_farm_observation(farm_id, observation)
        history = mongodb_memory.get_farm_history(farm_id)
        assert len(history) == 1
        assert history[0]["observation_id"] == observation_id
        assert history[0]["observation"] == observation

        advisory = {"status": "completed", "weekly_action_list": ["Monitor soil moisture"]}
        mongodb_memory.save_advisory(farm_id, advisory)
        previous = mongodb_memory.get_previous_advisories(farm_id)
        assert len(previous) == 1
        assert previous[0]["advisory"] == advisory
    finally:
        disposable_memory["farms"].delete_many({"farm_id": farm_id})
        disposable_memory["farm_observations"].delete_many({"farm_id": farm_id})
        disposable_memory["advisories"].delete_many({"farm_id": farm_id})


def test_history_queries_sort_descending_and_apply_limit(disposable_memory):
    farm_id = f"test-farm-{uuid4()}"
    now = datetime.now(timezone.utc)
    observations = disposable_memory["farm_observations"]
    advisories = disposable_memory["advisories"]
    try:
        observations.insert_many([
            {"observation_id": "older", "farm_id": farm_id, "observation": {"crop_name": "one"}, "created_at": now},
            {"observation_id": "newer", "farm_id": farm_id, "observation": {"crop_name": "two"}, "created_at": now + timedelta(seconds=1)},
        ])
        advisories.insert_many([
            {"advisory_id": "older", "farm_id": farm_id, "advisory": {"status": "old"}, "created_at": now},
            {"advisory_id": "newer", "farm_id": farm_id, "advisory": {"status": "new"}, "created_at": now + timedelta(seconds=1)},
        ])

        assert [r["observation_id"] for r in mongodb_memory.get_farm_observations(farm_id, 1)] == ["newer"]
        assert [r["advisory_id"] for r in mongodb_memory.get_farm_advisories(farm_id, 1)] == ["newer"]
    finally:
        observations.delete_many({"farm_id": farm_id})
        advisories.delete_many({"farm_id": farm_id})
