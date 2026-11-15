from unittest.mock import Mock

import pytest

import llm_service
from agents.evidence import InvalidModelOutputError


def test_groq_configuration_is_checked_at_request_time(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    with pytest.raises(RuntimeError, match="credentials or model configuration"):
        llm_service.ask_groq_json("system", "user")


def test_groq_json_requires_a_json_object(monkeypatch):
    completion = Mock()
    completion.choices = [Mock(message=Mock(content='["not", "an", "object"]'))]
    client = Mock()
    client.chat.completions.create.return_value = completion
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_MODEL", "test-model")
    monkeypatch.setattr(llm_service, "OpenAI", Mock(return_value=client))

    with pytest.raises(InvalidModelOutputError, match="JSON object"):
        llm_service.ask_groq_json("system", "user")


def test_groq_json_returns_only_decoded_object(monkeypatch):
    completion = Mock()
    completion.choices = [Mock(message=Mock(content='{"result": "ok"}'))]
    client = Mock()
    client.chat.completions.create.return_value = completion
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_MODEL", "test-model")
    monkeypatch.setattr(llm_service, "OpenAI", Mock(return_value=client))

    assert llm_service.ask_groq_json("system", "user") == {"result": "ok"}
    assert client.chat.completions.create.call_args.kwargs["response_format"] == {"type": "json_object"}
