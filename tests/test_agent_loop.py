"""
Runs the whole agent (LangChain control loop, tools, schema, URL building) against a fake OpenAI-compatible server and
a fake iNaturalist API. No LLM key or network is needed.
"""
import json

import httpx
import pytest
from ichatbio.agent_response import ArtifactResponse, DirectResponse, ResponseContext
from ichatbio.test_utils import InMemoryResponseChannel
from openai import AsyncOpenAI
from langchain_openai import ChatOpenAI

import agent as agent_module
import tools.find_occurrence_records as find_mod
import tools.util as tutil


def _completion(message: dict) -> httpx.Response:
    return httpx.Response(200, json={
        "id": "x", "object": "chat.completion", "created": 0, "model": "m",
        "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", **message}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    })


def _tool_call(name: str, args: dict) -> dict:
    return {"content": None, "tool_calls": [
        {"id": "c1", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}
    ]}


def make_handler(outer_script, inner_args):
    """outer_script: tool calls the control loop makes, in order. inner_args: what the parameter generator returns."""
    calls = iter(outer_script)

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        tool_names = {t["function"]["name"] for t in body.get("tools", [])}
        if "finish" in tool_names:  # the control loop
            name, args = next(calls)
            return _completion(_tool_call(name, args))
        return _completion(_tool_call("LLMResponseModel", inner_args))  # the parameter generator

    return handler


@pytest.fixture
def run_agent(monkeypatch):
    monkeypatch.setenv("USE_LLM_PROXY", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://fake")

    async def run(outer_script, inner_args, api_results=None, total=0):
        transport = httpx.MockTransport(make_handler(outer_script, inner_args))
        monkeypatch.setattr(
            tutil, "AsyncOpenAI", lambda **kw: AsyncOpenAI(**kw, http_client=httpx.AsyncClient(transport=transport))
        )
        monkeypatch.setattr(
            agent_module, "ChatOpenAI",
            lambda **kw: ChatOpenAI(**{**kw, "streaming": False}, http_async_client=httpx.AsyncClient(transport=transport)),
        )
        urls = []

        async def fake_query(url):
            urls.append(url)
            return "200 OK", True, {"total_results": total, "results": api_results or []}

        monkeypatch.setattr(find_mod, "query_inaturalist_observations", fake_query)

        messages = []
        context = ResponseContext(InMemoryResponseChannel(messages))
        await agent_module.INaturalistAgent().run(context, "request", "search_inaturalist_observations", None, None)
        return messages, urls

    return run


@pytest.mark.asyncio
async def test_agent_searches_then_finishes(run_agent):
    messages, urls = await run_agent(
        outer_script=[
            ("find_occurrence_records", {"request": "research grade rat photos"}),
            ("finish", {"message": "Found the observations."}),
        ],
        inner_args={
            "plan": "name, quality, photos",
            "search_parameters": {"taxon_name": "Rattus rattus", "quality_grade": "research", "photos": True},
            "artifact_description": "Research grade rat observations with photos",
            "retry": False,
        },
        api_results=[{"id": 1}],
        total=5,
    )
    assert len(urls) == 1 and "photos=true" in urls[0] and "quality_grade=research" in urls[0]
    assert any(isinstance(m, ArtifactResponse) for m in messages)
    assert isinstance(messages[-1], DirectResponse) and messages[-1].text == "Found the observations."


@pytest.mark.asyncio
async def test_agent_aborts_without_calling_the_api(run_agent):
    messages, urls = await run_agent(
        outer_script=[("abort", {"reason": "Image quality cannot be searched."})],
        inner_args={},
    )
    assert urls == []
    assert messages[-1].text == "Image quality cannot be searched."


@pytest.mark.asyncio
async def test_agent_rejects_unknown_entrypoint(monkeypatch):
    context = ResponseContext(InMemoryResponseChannel([]))
    with pytest.raises(ValueError):
        await agent_module.INaturalistAgent().run(context, "x", "not_an_entrypoint", None, None)
