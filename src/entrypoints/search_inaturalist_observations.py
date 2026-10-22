import http.client
import os
from urllib.parse import urlencode, quote_plus

import httpx
import instructor
from ichatbio.agent_response import ResponseContext, IChatBioAgentProcess
from ichatbio.types import AgentEntrypoint
from instructor import AsyncInstructor
from instructor.exceptions import InstructorRetryException
from openai import AsyncOpenAI
from tenacity import AsyncRetrying

from util import AIGenerationException, StopOnTerminalErrorOrMaxAttempts, get_llm_credentials
from schema import LLMGeneration

# This description helps iChatBio understand when to call this entrypoint
description = """
Searches for observation data in the iNaturalist observations API. Returns the query used and a URL to view the results. 
"""

entrypoint = AgentEntrypoint(
    id="search_inaturalist_observations",
    description=description,
    parameters=None
)

SYSTEM_PROMPT = """
You are a backend assistant that generates structured API queries for the iNaturalist observations endpoint (/observations). Your task is to convert natural language requests into precise query parameters using a Pydantic schema called ObservationsQueryParams.

You must return a valid dictionary that can be parsed by this schema. Only include parameters that are relevant to the user's request. Be strict and accurate in your interpretation — only include values that the user clearly expresses or implies. Never fabricate values or fill optional fields unless there's a clear signal to do so.

Instructions:

DO NOT guess.

If a specific field is not implied or mentioned, leave it out.

Dates must be in yyyy-mm-dd, yyyy-mm, or yyyy format where applicable.

Boolean values must be expressed as true or false.

Use enums and constrained values exactly as specified in the schema:

license, photo_license, order_by, quality_grade, etc. must be from their allowed list.

If multiple values are specified for fields like iconic_taxa or has, include them as lists.
"""


async def run(context: ResponseContext, request: str):
    """
    Executes this specific entrypoint. See description above. This function yields a sequence of messages that are
    returned one-by-one to iChatBio in response to the request, logging the retrieval process in real time.
    """
    async with context.begin_process("Searching iNaturalist observation records") as process:
        process: IChatBioAgentProcess

        await process.log("Generating search parameters for iNaturalist's observations API")

        try:
            params, artifact_description = await _generate_observations_params(request)
        except AIGenerationException as e:
            await process.log(str(e))
            return

        await process.log("Generated search parameters:", data=params)

        api_url = 'https://api.inaturalist.org/v1/observations'
        api_query_url = build_query_url(api_url, params)
        await process.log(f"Sending a GET request to iNaturalist observations API at {api_query_url}")

        try:
            response_code, success, response_data = await query_inaturalist_observations(api_query_url)
        except Exception as e:
            await process.log(f"An error occurred while querying iNaturalist: {e}")
            return

        if not success:
            await process.log(f"Response code: {response_code} - something went wrong!")
            return

        response_item_count = response_data.get('total_results', )
        if response_item_count > 0:
            await process.create_artifact(
                mimetype="application/json",
                description=artifact_description,
                uris=[api_query_url],
                metadata={"data_source": "iNaturalist"}
            )

            await context.reply(
                f"In the artifact record contents, the last part of photo URLs (e.g. square.jpg) can be changed to"
                f" original.jpg to access the original, full-size images. The small photo versions are not of interest."
                f"So, if you view an observation image with a URL like https://inaturalist-open-data.s3.amazonaws.com/photos/[ID]/square.jpg, you should instead view https://inaturalist-open-data.s3.amazonaws.com/photos/[ID]/original.jpg"
            )

        await process.log(
            f"Found {response_item_count} observation records: {api_query_url}"
        )


async def query_inaturalist_observations(api_query_url):
    async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
        response = await client.get(api_query_url)
        code = f"{response.status_code} {http.client.responses.get(response.status_code, '')}"
        data = response.json() if response.is_success else None
        return code, response.is_success, data


def _format_value(value) -> str:
    # The API only understands lowercase true/false. Python's str(True) is "True", which it silently ignores.
    # bool must be checked before anything else because bool is a subclass of int.
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def build_query_url(api_url: str, params: dict) -> str:
    query_items = []

    for key, value in params.items():
        if isinstance(value, list):
            list_key = key if key.endswith("[]") else f"{key}[]"
            for item in value:
                query_items.append((list_key, _format_value(item)))
        else:
            query_items.append((key, _format_value(value)))

    query_string = urlencode(query_items, quote_via=quote_plus)
    return f"{api_url}?{query_string}"


async def _generate_observations_params(request: str):
    model = os.getenv("LLM", os.getenv("AGENTS_LLM", "gpt-5.2"))
    try:
        client: AsyncInstructor = instructor.from_openai(AsyncOpenAI(**get_llm_credentials()))
        result = await client.chat.completions.create(
            model=model,
            temperature=0,
            response_model=LLMGeneration,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": request}
            ],
            max_retries=AsyncRetrying(stop=StopOnTerminalErrorOrMaxAttempts(3))
        )

        params = result.model_dump(exclude_none=True, by_alias=True)
        return params['search_parameters'], params['artifact_description']
    except InstructorRetryException as e:
        raise AIGenerationException(e)