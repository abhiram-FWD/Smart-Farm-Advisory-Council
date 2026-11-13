import os

import pytest
from pymongo import MongoClient


def test_disposable_mongodb_connection():
    uri = os.getenv("AGRIVISION_TEST_MONGODB_URI")
    db_name = os.getenv("AGRIVISION_TEST_DB_NAME")
    if not uri or not db_name:
        pytest.skip("Disposable MongoDB integration settings are not configured.")
    if db_name != "agrivision_test_db":
        pytest.fail("Integration tests require the isolated agrivision_test_db database.")

    test_client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    try:
        selected_database = test_client[db_name]
        assert selected_database.name == "agrivision_test_db"
        assert selected_database.command("ping").get("ok") == 1
    finally:
        test_client.close()
