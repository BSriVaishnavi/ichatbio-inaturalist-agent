import os

import pytest
import pytest_asyncio
from ichatbio.agent_response import ArtifactResponse

from agent import INaturalistAgent

# This test calls a real LLM. It only runs when LLM credentials are configured (for example in a .env file).
requires_llm = pytest.mark.skipif(
    not (os.getenv("USE_LLM_PROXY") and os.getenv("OPENAI_API_KEY") and os.getenv("OPENAI_BASE_URL")),
    reason="USE_LLM_PROXY, OPENAI_API_KEY and OPENAI_BASE_URL must be set to call a real LLM",
)


@pytest_asyncio.fixture()
def agent():
    return INaturalistAgent()


@requires_llm
@pytest.mark.asyncio
async def test_search_inaturalist_observations(agent, context, messages):
    await agent.run(context, "Find observations of Rattus rattus", "search_inaturalist_observations", None)

    artifact = next((m for m in messages if isinstance(m, ArtifactResponse)), None)
    assert artifact
    assert artifact.mimetype == "application/json"
