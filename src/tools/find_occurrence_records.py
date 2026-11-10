import functools
import json
from datetime import date
from importlib.resources import files

from ichatbio.agent_response import IChatBioAgentProcess
from langgraph.prebuilt import ToolRuntime

from entrypoints.search_inaturalist_observations import build_query_url, query_inaturalist_observations
from schema import ObservationsQueryParams
from tools.context import current_context
from tools.util import (
    PHOTO_SIZE,
    context_tool,
    generate_search_parameters,
    make_llm_response_model,
    make_system_prompt,
    upsize_photo_urls,
)
from util import AIGenerationException

API_URL = "https://api.inaturalist.org/v1/observations"

# This description helps the control loop decide when to call this tool
description = """\
Searches for observations using the iNaturalist observations API.

Returns:
- The total number of observations that were found
- The URL used to call the iNaturalist observations API
- An artifact containing the retrieved observations
"""

LLMResponseModel = make_llm_response_model(ObservationsQueryParams)


@context_tool(description=description)
async def find_occurrence_records(request: str, runtime: ToolRuntime):
    """
    Generates a sequence of messages that are returned one-by-one to iChatBio in response to the request, logging the
    retrieval process in real time. Observations retrieved from the iNaturalist API are packaged as a JSON artifact
    that iChatBio can interact with.
    """
    context = current_context.get()
    async with context.begin_process("Searching iNaturalist observations") as process:
        process: IChatBioAgentProcess

        await process.log("Generating search parameters for iNaturalist's observations API")
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

        # iNaturalist returns tiny "square" photo URLs by default. Point them to the full-size image so that photos
        # display properly in iChatBio.
        photo_count = upsize_photo_urls(response_data)
        if photo_count:
            await process.log(f"Changed {photo_count} photo URLs to the {PHOTO_SIZE} size")

        await context.reply(
            f"The API query returned {record_count} out of {matching_count} matching observations in iNaturalist"
            f" using the URL {api_query_url}"
        )

        if record_count > 0:
            await process.create_artifact(
                mimetype="application/json",
                description=artifact_description,
                content=json.dumps(response_data).encode("utf-8"),
                metadata={
                    "data_source": "iNaturalist",
                    "retrieved_record_count": record_count,
                    "total_matching_count": matching_count,
                    "source_url": api_query_url,
                },
            )
            await context.reply(
                "Tips:\n"
                "- Photo URLs are in the artifact data at results[].photos[].url and point to the original,"
                " full-size images."
            )


@functools.cache
def get_system_prompt():
    examples = {
        "Rattus rattus": LLMResponseModel(
            plan="The request names a species, so I will search by taxon_name.",
            search_parameters=ObservationsQueryParams(taxon_name="Rattus rattus"),
            artifact_description="Observations of Rattus rattus",
            warnings=None,
            retry=False,
        ),
        "Research grade observations of Rattus rattus that have photos": LLMResponseModel(
            plan="I will search by taxon_name, filter quality_grade to research, and set photos to true.",
            search_parameters=ObservationsQueryParams(
                taxon_name="Rattus rattus", quality_grade="research", photos=True
            ),
            artifact_description="Research grade observations of Rattus rattus that have photos",
            warnings=None,
            retry=False,
        ),
        "Rattus rattus observations without photos": LLMResponseModel(
            plan="To exclude observations with photos, photos must be set to false, not left unset.",
            search_parameters=ObservationsQueryParams(taxon_name="Rattus rattus", photos=False),
            artifact_description="Observations of Rattus rattus that have no photos",
            warnings=None,
            retry=False,
        ),
        "Birds observed in June 2020": LLMResponseModel(
            plan="Birds are the iconic taxon Aves. A whole year and month are set with the year and month fields.",
            search_parameters=ObservationsQueryParams(iconic_taxa=["Aves"], year=2020, month=6),
            artifact_description="Bird observations from June 2020",
            warnings=None,
            retry=False,
        ),
        "Rattus rattus observed between 2020-03-01 and 2020-05-31": LLMResponseModel(
            plan="A date range is set with d1 (start) and d2 (end).",
            search_parameters=ObservationsQueryParams(
                taxon_name="Rattus rattus", d1=date(2020, 3, 1), d2=date(2020, 5, 31)
            ),
            artifact_description="Observations of Rattus rattus from March to May 2020",
            warnings=None,
            retry=False,
        ),
        "Ursus americanus within 25 km of latitude 40.71, longitude -74.00": LLMResponseModel(
            plan="The request gives a center point and a distance, so I will use lat, lng, and radius (in km).",
            search_parameters=ObservationsQueryParams(
                taxon_name="Ursus americanus", lat=40.71, lng=-74.00, radius=25
            ),
            artifact_description="Observations of Ursus americanus within 25 km of 40.71, -74.00",
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
        "Birds observed in Florida": LLMResponseModel.model_construct(
            plan="The request names a region but gives no coordinates or place ID. I cannot look up place IDs and must"
                 " not guess them, so I should abort.",
            search_parameters=None,
            artifact_description=None,
            warnings=None,
            retry=False,
        ),
    }

    query_format_doc = files().joinpath("..", "resources", "records_query_format.md").read_text()
    tips_doc = files().joinpath("..", "resources", "occurrence_records_tips.md").read_text()

    return make_system_prompt(
        preamble="You translate user requests into parameters for the iNaturalist observations search API.",
        query_format_doc=query_format_doc,
        tips=tips_doc,
        examples=examples,
    )