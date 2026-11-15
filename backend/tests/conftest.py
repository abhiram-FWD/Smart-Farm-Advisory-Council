import pytest


@pytest.fixture
def isolated_knowledge_base(monkeypatch):
    from rag import knowledge_base

    monkeypatch.setattr(knowledge_base, "_knowledge_index", {
        "fingerprint": None,
        "chunks": [],
        "idf": {},
    })
    return knowledge_base
