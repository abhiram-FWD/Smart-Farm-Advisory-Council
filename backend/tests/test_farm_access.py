import pytest
from pymongo.errors import DuplicateKeyError

from memory import mongodb_memory


class MemoryFarmCollection:
    def __init__(self):
        self.records = []

    def insert_one(self, record):
        if any(item["farm_id"] == record["farm_id"] for item in self.records):
            raise DuplicateKeyError("duplicate farm")
        self.records.append(dict(record))

    def find_one(self, query, projection=None):
        return next(
            (dict(item) for item in self.records if all(item.get(k) == v for k, v in query.items())),
            None,
        )


class EmptyHistoryCollection:
    def find_one(self, query, projection=None):
        return None


def use_empty_history(monkeypatch):
    monkeypatch.setattr(mongodb_memory, "observations_collection", EmptyHistoryCollection())
    monkeypatch.setattr(mongodb_memory, "advisories_collection", EmptyHistoryCollection())


def test_farm_creation_stores_only_token_hash(monkeypatch):
    use_empty_history(monkeypatch)
    collection = MemoryFarmCollection()
    monkeypatch.setattr(mongodb_memory, "farms_collection", collection)

    token = mongodb_memory.create_farm("farm-new")

    assert isinstance(token, str) and token
    assert mongodb_memory.get_farm_id_for_token(token) == "farm-new"
    assert collection.records[0]["access_token_hash"] != token
    assert token not in collection.records[0].values()


def test_existing_farm_reuses_same_token_without_rotating_it(monkeypatch):
    use_empty_history(monkeypatch)
    collection = MemoryFarmCollection()
    monkeypatch.setattr(mongodb_memory, "farms_collection", collection)
    token = mongodb_memory.create_farm("farm-current")

    assert mongodb_memory.create_farm("farm-current", current_token=token) is None
    assert len(collection.records) == 1
    assert mongodb_memory.get_farm_id_for_token(token) == "farm-current"


def test_token_cannot_be_associated_with_another_farm(monkeypatch):
    use_empty_history(monkeypatch)
    collection = MemoryFarmCollection()
    monkeypatch.setattr(mongodb_memory, "farms_collection", collection)
    token = mongodb_memory.create_farm("farm-current")

    with pytest.raises(mongodb_memory.ActiveFarmMismatchError):
        mongodb_memory.create_farm("farm-other", current_token=token)

    assert len(collection.records) == 1
    assert mongodb_memory.get_farm_id_for_token(token) == "farm-current"


def test_unknown_token_cannot_claim_existing_farm(monkeypatch):
    use_empty_history(monkeypatch)
    collection = MemoryFarmCollection()
    monkeypatch.setattr(mongodb_memory, "farms_collection", collection)
    token = mongodb_memory.create_farm("farm-current")

    with pytest.raises(mongodb_memory.InvalidFarmTokenError):
        mongodb_memory.create_farm("farm-other", current_token="invalid-token")

    with pytest.raises(mongodb_memory.FarmAlreadyExistsError):
        mongodb_memory.create_farm("farm-current")
    assert mongodb_memory.get_farm_id_for_token(token) == "farm-current"


@pytest.mark.parametrize("collection_name", ["observations_collection", "advisories_collection"])
def test_unregistered_history_cannot_be_claimed_by_new_farm_credential(
    monkeypatch, collection_name
):
    farms = MemoryFarmCollection()
    use_empty_history(monkeypatch)
    monkeypatch.setattr(mongodb_memory, "farms_collection", farms)

    class ExistingHistoryCollection:
        def find_one(self, query, projection=None):
            return {"_id": "existing-history"}

    monkeypatch.setattr(mongodb_memory, collection_name, ExistingHistoryCollection())

    with pytest.raises(mongodb_memory.FarmAlreadyExistsError):
        mongodb_memory.create_farm("unclaimed-farm")

    assert farms.records == []


def test_runtime_database_is_strictly_the_original_database():
    assert mongodb_memory.MONGODB_DB_NAME == "smart_farm_db"
    assert mongodb_memory.database.name == "smart_farm_db"
    assert {
        mongodb_memory.farms_collection.database.name,
        mongodb_memory.observations_collection.database.name,
        mongodb_memory.advisories_collection.database.name,
    } == {"smart_farm_db"}
