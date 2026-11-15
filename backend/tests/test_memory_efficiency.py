import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from agents import semantic_kernel_orchestrator as orchestrator
from rag import knowledge_base


def test_chroma_client_collection_and_embedding_function_are_reused(monkeypatch):
    calls = {"client": 0, "embedding_function": 0, "collection": 0}
    collection = object()

    class FakeClient:
        def get_or_create_collection(self, **kwargs):
            calls["collection"] += 1
            assert kwargs["embedding_function"] is embedding_function
            return collection

    embedding_function = object()

    def create_client():
        calls["client"] += 1
        return FakeClient()

    def create_embedding_function():
        calls["embedding_function"] += 1
        return embedding_function

    monkeypatch.setattr(knowledge_base, "client", None)
    monkeypatch.setattr(knowledge_base, "collection", None)
    monkeypatch.setattr(knowledge_base, "_embedding_function", None)
    monkeypatch.setattr(knowledge_base, "_create_chroma_client", create_client)
    monkeypatch.setattr(
        knowledge_base,
        "_create_shared_embedding_function",
        create_embedding_function,
    )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: knowledge_base._get_collection(), range(16)))

    assert all(result is collection for result in results)
    assert calls == {"client": 1, "embedding_function": 1, "collection": 1}


def test_onnx_embedding_model_is_loaded_once_and_inference_is_serialized(monkeypatch):
    active_calls = 0
    max_active_calls = 0
    create_calls = 0
    state_lock = threading.Lock()

    class FakeModel:
        def __call__(self, values):
            nonlocal active_calls, max_active_calls
            with state_lock:
                active_calls += 1
                max_active_calls = max(max_active_calls, active_calls)
            time.sleep(0.02)
            with state_lock:
                active_calls -= 1
            return values

    def create_model():
        nonlocal create_calls
        create_calls += 1
        return FakeModel()

    monkeypatch.setattr(knowledge_base, "_embedding_model", None)
    monkeypatch.setattr(knowledge_base, "_create_onnx_embedding_model", create_model)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(knowledge_base._embed_with_shared_model, [[i] for i in range(8)]))

    assert results == [[i] for i in range(8)]
    assert create_calls == 1
    assert max_active_calls == 1


@pytest.mark.asyncio
async def test_semantic_kernel_agent_execution_is_limited_process_wide(monkeypatch):
    active_calls = 0
    max_active_calls = 0
    state_lock = threading.Lock()

    class FakeKernel:
        def add_plugin(self, *_args, **_kwargs):
            pass

        async def invoke(self, **_kwargs):
            nonlocal active_calls, max_active_calls
            with state_lock:
                active_calls += 1
                max_active_calls = max(max_active_calls, active_calls)
            time.sleep(0.03)
            with state_lock:
                active_calls -= 1
            return SimpleNamespace(value={"status": "completed"})

    monkeypatch.setattr(orchestrator, "Kernel", FakeKernel)

    results = await asyncio.gather(*(
        orchestrator.invoke_agent("test_agent", index=index)
        for index in range(8)
    ))

    assert len(results) == 8
    assert all(result == {"status": "completed"} for result in results)
    assert max_active_calls == 2
