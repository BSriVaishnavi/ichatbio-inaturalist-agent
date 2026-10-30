import functools
import os
import types
from contextlib import contextmanager
from typing import Optional, Self, Type, TypeVar

import instructor
import langchain.tools
from ichatbio.agent_response import ArtifactResponse, ResponseContext
from instructor import AsyncInstructor
from instructor.exceptions import InstructorRetryException
from langchain_core.messages import BaseMessage, convert_to_openai_messages
from openai import AsyncOpenAI
from pydantic import BaseModel, Field, model_validator
from tenacity import AsyncRetrying

from tools.context import current_context
from util import AIGenerationException, StopOnTerminalErrorOrMaxAttempts, get_llm_credentials


def context_tool(description: str):
    """
    Converts an async function into a LangChain tool that sends iChatBio messages. The function gets the current
    ResponseContext from the current_context context variable instead of taking it as an argument, because the
    context is not serializable and cannot be passed through a tool call.

    Example use:

    >>> @context_tool("Does something")
    >>> async def do_something(request: str):
    >>>     context = current_context.get()
    >>>     # Now do something...
    """

    def wrapper(func):
        @langchain.tools.tool(func.__name__, description=description)
        @functools.wraps(func)  # Preserves the function signature
        async def langchain_wrapper(*args, **kwargs):
            context = current_context.get()
            with capture_messages(context) as messages:
                await func(*args, **kwargs)
                return messages  # Pass the iChatBio messages back to the LangChain agent as context

        return langchain_wrapper

    return wrapper


@contextmanager
def capture_messages(context: ResponseContext):
    """
    Modifies a ResponseContext so that any message sent back to iChatBio is also collected into a list. Artifact
    messages are collected without their "content", so the LLM never sees raw data. Descriptions and metadata are
    enough for its decisions, giving it data would let it process data directly instead of leaving that to reliable
    code, and data can be too large for the context window.

    Usage:
        with capture_messages(context) as messages:
            await context.reply("Alert!")
            # Now messages[0] is a DirectResponse object
    """
    messages = []

    channel = context._channel
    old_submit = channel.submit

    async def submit_and_buffer(self, message):
        await old_submit(message)
        match message:
            case ArtifactResponse() as artifact:
                messages.append(
                    ArtifactResponse(
                        description=artifact.description,
                        mimetype=artifact.mimetype,
                        metadata=artifact.metadata,
                    )
                )
            case _:
                messages.append(message)

    channel.submit = types.MethodType(submit_and_buffer, channel)

    try:
        yield messages
    finally:
        # Restore the original method even if the tool raised an error
        channel.submit = old_submit


system_prompt_template = """
{preamble}

# Parameters

Here is a description of the iNaturalist observations API parameters you can use:

[BEGIN PARAMETER DOC]

{query_format_doc}

[END PARAMETER DOC]

# Tips

{tips}

# Examples

{examples}
"""

example_template = """\
## Example {i}

User: {request}

You: {response}\
"""


def make_system_prompt(
    preamble: str, query_format_doc: str, tips: str, examples: dict[str, BaseModel]
) -> str:
    return system_prompt_template.format(
        preamble=preamble.strip(),
        query_format_doc=query_format_doc.strip(),
        tips=tips,
        examples="\n\n".join(
            example_template.format(
                i=i,
                request=request,
                response=response.model_dump_json(exclude_none=True, exclude_unset=True, by_alias=True),
            )
            for i, (request, response) in enumerate(examples.items())
        ),
    ).strip()


TModel = TypeVar("TModel", bound=BaseModel)


def make_llm_response_model(search_parameters_model: Type[TModel]):
    class LLMResponseModel(BaseModel):
        plan: str = Field(
            description="A brief explanation of what API parameters you plan to use. Or, if you are unable to fulfill "
                        "the user's request using the available API parameters, provide a brief explanation for why "
                        "you cannot retrieve the requested observations."
        )
        search_parameters: Optional[search_parameters_model] = Field(
            None,
            description="The search parameters to use to retrieve the requested observations. If you are unable to "
                        "fulfill the user's request using the available API parameters, leave this field unset to "
                        "abort.",
        )
        artifact_description: Optional[str] = Field(
            None, description="A concise characterization of the retrieved observation data, if any."
        )
        warnings: Optional[str] = Field(
            None,
            description="If there is any reason why the search parameters might not fully match the request, or for "
                        "the results of the search to not fully complete the request, explain why here.",
        )
        retry: bool = Field(
            description="Set True if you would be able to fix the warnings by setting different search parameters."
        )

        @model_validator(mode="after")
        def validate_model(self) -> Self:
            if self.search_parameters:
                if not self.artifact_description:
                    raise ValueError("artifact_description must be provided when search_parameters is present")
                if self.retry and self.warnings:
                    raise ValueError("I need to try again to address the following: " + self.warnings)
            return self

    return LLMResponseModel


async def generate_search_parameters(
    request: str, system_prompt: str, llm_response_model: Type[TModel], history: list[BaseMessage]
) -> tuple[str, Optional[BaseModel], Optional[str], str]:
    model = os.getenv("LLM", os.getenv("AGENTS_LLM", "gpt-5.2"))
    try:
        client: AsyncInstructor = instructor.from_openai(AsyncOpenAI(**get_llm_credentials()))
        result = await client.chat.completions.create(
            model=model,
            temperature=0,
            response_model=llm_response_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"Messages exchanged before this request: {convert_to_openai_messages(history)}",
                },
                {"role": "user", "content": request},
            ],
            max_retries=AsyncRetrying(stop=StopOnTerminalErrorOrMaxAttempts(3)),
        )
    except InstructorRetryException as e:
        raise AIGenerationException(e)

    return result.plan, result.search_parameters, result.artifact_description, result.warnings or ""
