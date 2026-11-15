import asyncio
import builtins
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from agents import semantic_kernel_orchestrator as orchestrator
from rag import knowledge_base


def test_tfidf_retrieval_uses_cached_sparse_index_without_heavy_model_imports(
    isolated_knowledge_base, monkeypatch
):
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "chromadb" or name.startswith("chromadb.") or name == "onnxruntime":
            raise AssertionError(f"Heavy embedding dependency imported: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    count = isolated_knowledge_base.load_knowledge_base()
    first_index = isolated_knowledge_base._knowledge_index
    assert count > 0
    assert all(isinstance(chunk["vector"], dict) for chunk in first_index["chunks"])

    results = isolated_knowledge_base.search_knowledge(
        "wheat rust yellow orange pustules", crop="Wheat", category="diseases"
    )

    assert results
    assert isolated_knowledge_base._knowledge_index is first_index
    assert results[0]["source"] == "wheat_diseases.txt"


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
