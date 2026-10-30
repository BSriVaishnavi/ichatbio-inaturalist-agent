import functools
from importlib.resources import files

from ichatbio.agent_response import IChatBioAgentProcess
from langgraph.prebuilt import ToolRuntime

from entrypoints.search_inaturalist_observations import build_query_url, query_inaturalist_observations
from schema import ObservationsQueryParams
from tools.context import current_context
from tools.util import (
    context_tool,
    generate_search_parameters,
    make_llm_response_model,
    make_system_prompt,
)
from util import AIGenerationException

API_URL = "https://api.inaturalist.org/v1/observations"

description = """\
Searches for iNaturalist observations that have photos or sounds, for requests about images or recordings. Only
observations with media are returned. Photo URLs are in the artifact data at results[].photos[].url.
"""

LLMResponseModel = make_llm_response_model(ObservationsQueryParams)


@context_tool(description=description)
async def find_media_records(request: str, runtime: ToolRuntime):
    context = current_context.get()
    async with context.begin_process("Searching iNaturalist observations with media") as process:
        process: IChatBioAgentProcess

        await process.log("Generating search parameters for iNaturalist observations with media")
        try:
            plan, params, artifact_description, generation_warnings = await generate_search_parameters(
                request, get_system_prompt(), LLMResponseModel, runtime.state.get("messages", [])
            )
        except AIGenerationException as e:
            await process.log(e.message)
            return

        if generation_warnings:
            await process.log(generation_warnings)

        if params is None:
            await process.log(f"Failed to generate appropriate search parameters. Reason: {plan}")
            return

        # Media requests only make sense for observations that have media
        if not params.sounds:
            params.photos = True

        json_params = params.model_dump(exclude_none=True, by_alias=True)
        await process.log("Generated search parameters", data=json_params)

        api_query_url = build_query_url(API_URL, json_params)
        await process.log(f"Sending a GET request to the iNaturalist observations API at {api_query_url}")

        try:
            response_code, success, response_data = await query_inaturalist_observations(api_query_url)
        except Exception as e:
            await process.log(f"An error occurred while querying iNaturalist: {e}")
            return

        if not success:
            await process.log(f"Response code: {response_code} - something went wrong!")
            return

        matching_count = response_data.get("total_results", 0)
        record_count = len(response_data.get("results", []))

        await context.reply(
            f"The API query returned {record_count} out of {matching_count} matching observations with media in"
            f" iNaturalist using the URL {api_query_url}"
        )

        if record_count > 0:
            await process.create_artifact(
                mimetype="application/json",
                description=artifact_description,
                uris=[api_query_url],
                metadata={
                    "data_source": "iNaturalist",
                    "retrieved_record_count": record_count,
                    "total_matching_count": matching_count,
                },
            )
            await context.reply(
                "Tips:\n"
                "- Photo URLs are in the artifact data at results[].photos[].url.\n"
                "- To get a different photo size, replace only the size name in the URL (for example square) with"
                " original, large, medium, small, or thumb."
            )


@functools.cache
def get_system_prompt():
    examples = {
        "Photos of Rattus rattus": LLMResponseModel(
            plan="Photos are on observations, so I search by taxon_name and require photos.",
            search_parameters=ObservationsQueryParams(taxon_name="Rattus rattus", photos=True),
            artifact_description="Observations of Rattus rattus that have photos",
            warnings=None,
            retry=False,
        ),
        "Recordings of birds": LLMResponseModel(
            plan="Birds are the iconic taxon Aves, and recordings are sounds.",
            search_parameters=ObservationsQueryParams(iconic_taxa=["Aves"], sounds=True),
            artifact_description="Bird observations that have sound recordings",
            warnings=None,
            retry=False,
        ),
        "Blurry photos of birds": LLMResponseModel.model_construct(
            plan="There is no search parameter for image quality, so I should abort.",
            search_parameters=None,
            artifact_description=None,
            warnings=None,
            retry=False,
        ),
    }

    query_format_doc = files().joinpath("..", "resources", "records_query_format.md").read_text()
    tips_doc = files().joinpath("..", "resources", "occurrence_records_tips.md").read_text()

    return make_system_prompt(
        preamble="You translate user requests for photos or sounds into parameters for the iNaturalist observations search API.",
        query_format_doc=query_format_doc,
        tips=tips_doc,
        examples=examples,
    )
