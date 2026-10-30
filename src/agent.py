import os
from importlib.resources import files
from typing import Any, override

import dotenv
import langchain.agents
from ichatbio.agent import IChatBioAgent
from ichatbio.agent_response import ResponseContext
from ichatbio.server import build_agent_app
from ichatbio.types import AgentCard, AgentEntrypoint
from langchain.agents.middleware import after_model
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import ToolRuntime
from pydantic import BaseModel
from starlette.applications import Starlette

from tools.context import current_context
from tools.count_occurrence_records import count_occurrence_records
from tools.find_media_records import find_media_records
from tools.find_occurrence_records import find_occurrence_records
from util import get_llm_credentials, set_llm_credentials


class INaturalistAgent(IChatBioAgent):
    @override
    def get_agent_card(self) -> AgentCard:
        return AgentCard(
            name="iNaturalist Observation Search",
            description="Searches for observations in iNaturalist (https://inaturalist.org).",
            documentation_url="https://github.com/acislab/ichatbio-inaturalist-agent",
            icon="https://static.inaturalist.org/wiki_page_attachments/3154-medium.png",
            entrypoints=[
                AgentEntrypoint(
                    id="search_inaturalist_observations",
                    description="Retrieves data from iNaturalist, including observations and associated photos and sounds. Can also provide species counts for the observations that match a search.",
                ),
            ],
        )

    @override
    async def run(
            self,
            context: ResponseContext,
            request: str,
            entrypoint: str,
            params: BaseModel | None = None,
            metadata: dict[str, Any] | None = None
    ):
        """
        Executes a LangChain agent graph with `request` as input. The agent does not produce text responses directly,
        but must do so by calling tools. Only tools send response messages back iChatBio.
        """
        if entrypoint != "search_inaturalist_observations":
            raise ValueError(f"Unknown entrypoint: {entrypoint}")

        set_llm_credentials(metadata)
        current_context.set(context)

        # Run the graph
        langchain_agent = self._build_langchain_agent()
        await langchain_agent.ainvoke(
            {
                "messages": [
                    {"role": "user", "content": request},
                ]
            }
        )

    def _build_langchain_agent(self):
        @after_model
        async def share_text_messages(state, runtime):
            message = state["messages"][-1]
            if isinstance(message, AIMessage) and isinstance(message.content, str):
                await current_context.get().reply(message.content)

        control_loop_prompt = files().joinpath("resources", "control_loop_prompt.md").read_text()
        credentials = get_llm_credentials()

        return langchain.agents.create_agent(
            model=ChatOpenAI(
                model=os.getenv("LLM", os.getenv("AGENTS_LLM", "gpt-5.2")),
                streaming=True,
                base_url=credentials["base_url"],
                api_key=credentials["api_key"],
                temperature=0,
                model_kwargs={"tool_choice": "required"}
            ),
            tools=[
                find_occurrence_records,
                count_occurrence_records,
                find_media_records,
                abort,
                finish
            ],
            middleware=[share_text_messages],
            system_prompt=control_loop_prompt
        )


@tool(return_direct=True)  # This tool ends the agent loop
async def abort(reason: str, runtime: ToolRuntime):
    """If you can't fulfill the user's request, abort instead and explain why."""
    await current_context.get().reply(reason)


@tool(return_direct=True)  # This tool ends the agent loop
async def finish(message: str, runtime: ToolRuntime):
    """Mark the user's request as successfully completed."""
    await current_context.get().reply(message)


def create_app() -> Starlette:
    dotenv.load_dotenv()
    agent = INaturalistAgent()
    app = build_agent_app(agent)
    return app
