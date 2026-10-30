"""
Checks that the tools, schema, entrypoint helpers and util work together. No LLM key or network is needed: the LLM call
and the HTTP call are replaced with fakes.
"""
from types import SimpleNamespace

import pytest
from ichatbio.agent_response import ArtifactResponse, DirectResponse, ResponseContext
from ichatbio.test_utils import InMemoryResponseChannel

from schema import ObservationsQueryParams
from tools import count_occurrence_records as count_mod
from tools import find_media_records as media_mod
from tools import find_occurrence_records as find_mod
from tools.context import current_context

RUNTIME = SimpleNamespace(state={"messages": []})


@pytest.fixture
def messages():
    return []


@pytest.fixture
def context(messages):
    ctx = ResponseContext(InMemoryResponseChannel(messages))
    token = current_context.set(ctx)
    yield ctx
    current_context.reset(token)


def fake_generate(params, description="Test artifact", warnings=""):
    async def _generate(request, system_prompt, model, history):
        return "plan", params, description, warnings

    return _generate


def fake_query(results, total, seen):
    async def _query(url):
        seen.append(url)
        return "200 OK", True, {"total_results": total, "results": results}

    return _query


def kinds(messages):
    return [type(m).__name__ for m in messages]


@pytest.mark.parametrize("mod", [find_mod, count_mod, media_mod])
def test_system_prompt_builds_and_contains_examples(mod):
    prompt = mod.get_system_prompt()
    assert "# Examples" in prompt
    assert "Example 0" in prompt


@pytest.mark.parametrize("mod", [find_mod, count_mod, media_mod])
def test_tool_has_name_and_description(mod):
    tool = getattr(mod, mod.__name__.split(".")[-1])
    assert tool.name == mod.__name__.split(".")[-1]
    assert tool.description.strip()


@pytest.mark.asyncio
async def test_find_builds_url_from_schema_and_makes_artifact(context, messages, monkeypatch):
    seen = []
    params = ObservationsQueryParams(taxon_name="Rattus rattus", photos=True, quality_grade="research")
    monkeypatch.setattr(find_mod, "generate_search_parameters", fake_generate(params))
    monkeypatch.setattr(find_mod, "query_inaturalist_observations", fake_query([{"id": 1}], 10, seen))

    result = await find_mod.find_occurrence_records.coroutine(request="rats", runtime=RUNTIME)

    assert "photos=true" in seen[0]
    assert "taxon_name=Rattus+rattus" in seen[0]
    assert seen[0].startswith("https://api.inaturalist.org/v1/observations?")
    artifact = next(m for m in messages if isinstance(m, ArtifactResponse))
    assert artifact.metadata["total_matching_count"] == 10
    assert artifact.metadata["retrieved_record_count"] == 1
    # the LLM-facing messages never carry artifact content
    assert any(isinstance(m, ArtifactResponse) for m in result)


@pytest.mark.asyncio
async def test_find_aborts_without_params_and_never_calls_api(context, messages, monkeypatch):
    seen = []
    monkeypatch.setattr(find_mod, "generate_search_parameters", fake_generate(None))
    monkeypatch.setattr(find_mod, "query_inaturalist_observations", fake_query([], 0, seen))

    await find_mod.find_occurrence_records.coroutine(request="blurry birds", runtime=RUNTIME)

    assert seen == []
    assert not any(isinstance(m, ArtifactResponse) for m in messages)


@pytest.mark.asyncio
async def test_find_makes_no_artifact_when_nothing_matches(context, messages, monkeypatch):
    seen = []
    monkeypatch.setattr(find_mod, "generate_search_parameters", fake_generate(ObservationsQueryParams(q="zzzz")))
    monkeypatch.setattr(find_mod, "query_inaturalist_observations", fake_query([], 0, seen))

    await find_mod.find_occurrence_records.coroutine(request="zzzz", runtime=RUNTIME)

    assert not any(isinstance(m, ArtifactResponse) for m in messages)


@pytest.mark.asyncio
async def test_find_reports_http_failure(context, messages, monkeypatch):
    async def failing(url):
        return "500 Internal Server Error", False, {}

    monkeypatch.setattr(find_mod, "generate_search_parameters", fake_generate(ObservationsQueryParams(q="a")))
    monkeypatch.setattr(find_mod, "query_inaturalist_observations", failing)

    await find_mod.find_occurrence_records.coroutine(request="a", runtime=RUNTIME)

    assert not any(isinstance(m, ArtifactResponse) for m in messages)


@pytest.mark.asyncio
async def test_find_survives_network_exception(context, messages, monkeypatch):
    async def boom(url):
        raise RuntimeError("network down")

    monkeypatch.setattr(find_mod, "generate_search_parameters", fake_generate(ObservationsQueryParams(q="a")))
    monkeypatch.setattr(find_mod, "query_inaturalist_observations", boom)

    await find_mod.find_occurrence_records.coroutine(request="a", runtime=RUNTIME)  # must not raise


@pytest.mark.asyncio
async def test_count_uses_species_counts_endpoint(context, messages, monkeypatch):
    seen = []
    params = ObservationsQueryParams(iconic_taxa=["Aves"], year=2020, per_page=10)
    monkeypatch.setattr(count_mod, "generate_search_parameters", fake_generate(params))
    monkeypatch.setattr(
        count_mod, "query_inaturalist_observations", fake_query([{"count": 5, "taxon": {}}], 300, seen)
    )

    await count_mod.count_occurrence_records.coroutine(request="top birds", runtime=RUNTIME)

    assert seen[0].startswith("https://api.inaturalist.org/v1/observations/species_counts?")
    assert "iconic_taxa%5B%5D=Aves" in seen[0]
    assert "year=2020" in seen[0]
    artifact = next(m for m in messages if isinstance(m, ArtifactResponse))
    assert artifact.metadata["total_species_count"] == 300


@pytest.mark.asyncio
async def test_media_forces_photos_true(context, messages, monkeypatch):
    seen = []
    monkeypatch.setattr(
        media_mod, "generate_search_parameters", fake_generate(ObservationsQueryParams(taxon_name="Rattus rattus"))
    )
    monkeypatch.setattr(media_mod, "query_inaturalist_observations", fake_query([{"id": 1}], 1, seen))

    await media_mod.find_media_records.coroutine(request="photos of rats", runtime=RUNTIME)

    assert "photos=true" in seen[0]


@pytest.mark.asyncio
async def test_media_does_not_force_photos_for_sounds(context, messages, monkeypatch):
    seen = []
    monkeypatch.setattr(
        media_mod, "generate_search_parameters", fake_generate(ObservationsQueryParams(iconic_taxa=["Aves"], sounds=True))
    )
    monkeypatch.setattr(media_mod, "query_inaturalist_observations", fake_query([{"id": 1}], 1, seen))

    await media_mod.find_media_records.coroutine(request="bird recordings", runtime=RUNTIME)

    assert "sounds=true" in seen[0]
    assert "photos=true" not in seen[0]


@pytest.mark.asyncio
async def test_capture_restores_channel_after_error(context, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("fail")

    monkeypatch.setattr(find_mod, "generate_search_parameters", boom)
    original = context._channel.submit

    with pytest.raises(RuntimeError):
        await find_mod.find_occurrence_records.coroutine(request="a", runtime=RUNTIME)

    assert context._channel.submit == original


def test_llm_response_model_rejects_unknown_parameter():
    with pytest.raises(Exception):
        find_mod.LLMResponseModel(
            plan="x", search_parameters={"taxon_name": "a", "bogus": 1}, artifact_description="d", retry=False
        )


def test_llm_response_model_requires_description_with_params():
    with pytest.raises(Exception):
        find_mod.LLMResponseModel(plan="x", search_parameters={"taxon_name": "a"}, retry=False)
