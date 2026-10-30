"""Runs the real instructor call path against a fake OpenAI-compatible server (no key, no network)."""
import json

import httpx
import pytest
from openai import AsyncOpenAI

import tools.util as tutil
from tools import find_occurrence_records as find_mod


def _reply(args: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        body = {
            "id": "x", "object": "chat.completion", "created": 0, "model": "m",
            "choices": [{
                "index": 0, "finish_reason": "stop",
                "message": {
                    "role": "assistant", "content": None,
                    "tool_calls": [{
                        "id": "c1", "type": "function",
                        "function": {"name": "LLMResponseModel", "arguments": json.dumps(args)},
                    }],
                },
            }],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
        return httpx.Response(200, json=body)

    return handler


@pytest.fixture
def fake_llm(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://fake")
    monkeypatch.setenv("USE_LLM_PROXY", "false")

    def install(args):
        transport = httpx.MockTransport(_reply(args))
        monkeypatch.setattr(
            tutil, "AsyncOpenAI", lambda **kw: AsyncOpenAI(**kw, http_client=httpx.AsyncClient(transport=transport))
        )

    return install


@pytest.mark.asyncio
async def test_generate_returns_validated_parameters(fake_llm):
    fake_llm({
        "plan": "search by name",
        "search_parameters": {"taxon_name": "Rattus rattus", "photos": True},
        "artifact_description": "Rats with photos",
        "retry": False,
    })
    plan, params, desc, warnings = await tutil.generate_search_parameters(
        "rats with photos", find_mod.get_system_prompt(), find_mod.LLMResponseModel, []
    )
    assert params.taxon_name == "Rattus rattus" and params.photos is True
    assert desc == "Rats with photos" and warnings == ""


@pytest.mark.asyncio
async def test_generate_abort_returns_none_parameters(fake_llm):
    fake_llm({"plan": "cannot do it", "retry": False})
    plan, params, desc, warnings = await tutil.generate_search_parameters(
        "blurry birds", find_mod.get_system_prompt(), find_mod.LLMResponseModel, []
    )
    assert params is None and plan == "cannot do it"


@pytest.mark.asyncio
async def test_generate_raises_after_repeated_invalid_output(fake_llm):
    from util import AIGenerationException

    fake_llm({"plan": "x", "search_parameters": {"bogus_field": 1}, "artifact_description": "d", "retry": False})
    with pytest.raises(AIGenerationException):
        await tutil.generate_search_parameters(
            "x", find_mod.get_system_prompt(), find_mod.LLMResponseModel, []
        )
