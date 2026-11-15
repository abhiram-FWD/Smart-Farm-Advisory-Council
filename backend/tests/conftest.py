import pytest


class InMemoryCollection:
    """Minimal deterministic collection for RAG tests; stores no app data."""

    name = "isolated-test-collection"

    def __init__(self):
        self.records = {}
        self.metadata = {}

    def modify(self, metadata=None):
        if metadata is not None:
            self.metadata = dict(metadata)

    def _matches(self, metadata, where):
        if not where:
            return True
        if "$and" in where:
            return all(self._matches(metadata, condition) for condition in where["$and"])
        if "$or" in where:
            return any(self._matches(metadata, condition) for condition in where["$or"])
        return all(metadata.get(key) == value for key, value in where.items())

    def get(self, where=None, include=None):
        selected = [
            (key, record) for key, record in self.records.items()
            if self._matches(record["metadata"], where)
        ]
        return {
            "ids": [key for key, _ in selected],
            "metadatas": [record["metadata"] for _, record in selected],
        }

    def delete(self, ids):
        for key in ids:
            self.records.pop(key, None)

    def add(self, documents, ids, metadatas):
        for document, key, metadata in zip(documents, ids, metadatas):
            self.records[key] = {"document": document, "metadata": metadata}

    def count(self):
        return len(self.records)

    def query(self, query_texts, n_results, where=None):
        selected = [
            record for record in self.records.values()
            if self._matches(record["metadata"], where)
        ][:n_results]
        return {
            "documents": [[record["document"] for record in selected]],
            "metadatas": [[record["metadata"] for record in selected]],
        }


@pytest.fixture
def isolated_knowledge_base(monkeypatch):
    from rag import knowledge_base

    monkeypatch.setattr(knowledge_base, "client", None)
    monkeypatch.setattr(knowledge_base, "collection", InMemoryCollection())
    return knowledge_base
