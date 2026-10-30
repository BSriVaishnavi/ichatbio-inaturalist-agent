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

API_URL = "https://api.inaturalist.org/v1/observations/species_counts"

description = """\
Counts the observations in iNaturalist that match the user's search criteria, broken down by species. Use it to build
top-N lists of species, for example the 10 species with the most observations in a place, or to see which species
matched. Also returns the total number of species found and the URL used to call the iNaturalist species counts API.
"""

LLMResponseModel = make_llm_response_model(ObservationsQueryParams)


@context_tool(description=description)
async def count_occurrence_records(request: str, runtime: ToolRuntime):
    context = current_context.get()
    async with context.begin_process("Requesting iNaturalist statistics") as process:
        process: IChatBioAgentProcess

        await process.log("Generating search parameters for iNaturalist species counts")
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
        await process.log(f"Sending a GET request to the iNaturalist species counts API at {api_query_url}")

        try:
            response_code, success, response_data = await query_inaturalist_observations(api_query_url)
        except Exception as e:
            await process.log(f"An error occurred while querying iNaturalist: {e}")
            return

        if not success:
            await process.log(f"Response code: {response_code} - something went wrong!")
            return

        total_species = response_data.get("total_results", 0)
        returned = len(response_data.get("results", []))

        await context.reply(
            f"The API query found {total_species} matching species in iNaturalist and returned counts for {returned}"
            f" of them using the URL {api_query_url}"
        )

        if returned > 0:
            await process.create_artifact(
                mimetype="application/json",
                description=artifact_description,
                uris=[api_query_url],
                metadata={
                    "data_source": "iNaturalist",
                    "total_species_count": total_species,
                    "returned_species_count": returned,
                },
            )


@functools.cache
def get_system_prompt():
    examples = {
        "The 10 species of Aves with the most observations in 2020": LLMResponseModel(
            plan="Birds are the iconic taxon Aves. Results come back ordered by observation count, so I limit per_page to 10.",
            search_parameters=ObservationsQueryParams(iconic_taxa=["Aves"], year=2020, per_page=10),
            artifact_description="The 10 bird species with the most observations in 2020",
            warnings=None,
            retry=False,
        ),
        "Which species of Rattus have research grade observations?": LLMResponseModel(
            plan="I will search the genus Rattus with quality_grade set to research.",
            search_parameters=ObservationsQueryParams(taxon_name="Rattus", quality_grade="research"),
            artifact_description="Species of Rattus with research grade observations and their counts",
            warnings=None,
            retry=False,
        ),
        "Which observers have the most bird observations?": LLMResponseModel.model_construct(
            plan="This tool counts species, not observers, so I should abort.",
            search_parameters=None,
            artifact_description=None,
            warnings=None,
            retry=False,
        ),
    }

    query_format_doc = files().joinpath("..", "resources", "records_query_format.md").read_text()
    tips_doc = files().joinpath("..", "resources", "occurrence_records_tips.md").read_text()

    return make_system_prompt(
        preamble="You translate user requests into parameters for the iNaturalist species counts API.",
        query_format_doc=query_format_doc,
        tips=tips_doc,
        examples=examples,
    )
