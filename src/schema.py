"""
This module provides pydantic schema used to craft and validate iNaturalist API queries.

Only parameters documented for GET /v1/observations are included. The API silently ignores parameters it does not
recognize, so an undocumented field can look valid while filtering nothing. extra="forbid" makes the LLM's output fail
validation (and get retried) if it invents a field.
"""
from datetime import date
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

License = Literal["cc-by", "cc-by-nc", "cc-by-nd", "cc-by-sa", "cc-by-nc-nd", "cc-by-nc-sa", "cc0"]


class ObservationsQueryParams(BaseModel):
    """
    Request parameters for the iNaturalist v1 observations search API (GET /v1/observations).
    """
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "taxon_name": "Rattus rattus",
                "photos": True,
                "quality_grade": "research",
                "per_page": 50,
            }
        },
    )

    # Free text and taxon
    q: Optional[str] = Field(
        None, description="Free-text search across observation properties. Use only when no other field fits."
    )
    taxon_name: Optional[str] = Field(
        None,
        description="A scientific or common taxon name. Includes descendant taxa. A common name can match several taxa.",
    )
    taxon_id: Optional[int] = Field(
        None,
        description="iNaturalist taxon ID. Includes descendant taxa. Only set this if the request states the ID. "
                    "Never guess an ID, use taxon_name instead.",
    )
    without_taxon_id: Optional[int] = Field(
        None, description="Exclude observations of this taxon ID and its descendants. Only set if the request states the ID."
    )
    iconic_taxa: Optional[List[Literal[
        "Plantae", "Animalia", "Mollusca", "Reptilia", "Aves", "Amphibia", "Actinopterygii", "Mammalia",
        "Insecta", "Arachnida", "Fungi", "Protozoa", "Chromista", "unknown"
    ]]] = Field(None, description="Broad taxon groups. Observations of any of the listed groups match.")
    rank: Optional[str] = Field(
        None, description="Only observations whose identified taxon has this rank.", examples=["species", "genus", "family"]
    )

    # Observer, place, project
    user_login: Optional[str] = Field(None, description="Only observations by the user with this login name.")
    place_id: Optional[int] = Field(
        None,
        description="iNaturalist place ID. Only set this if the request states the ID. Never guess an ID. "
                    "For named regions, use a bounding box or lat/lng/radius if coordinates are known.",
    )
    project_id: Optional[str] = Field(
        None, description="Project ID or slug. Only set if the request states it."
    )

    # Location
    lat: Optional[float] = Field(None, ge=-90, le=90, description="Center latitude. Use together with lng and radius.")
    lng: Optional[float] = Field(None, ge=-180, le=180, description="Center longitude. Use together with lat and radius.")
    radius: Optional[float] = Field(None, gt=0, description="Radius in kilometers around lat/lng.")
    nelat: Optional[float] = Field(None, ge=-90, le=90, description="Bounding box northeast latitude.")
    nelng: Optional[float] = Field(None, ge=-180, le=180, description="Bounding box northeast longitude.")
    swlat: Optional[float] = Field(None, ge=-90, le=90, description="Bounding box southwest latitude.")
    swlng: Optional[float] = Field(None, ge=-180, le=180, description="Bounding box southwest longitude.")

    # Time
    observed_on: Optional[date] = Field(None, description="Observed on exactly this date (yyyy-mm-dd).")
    d1: Optional[date] = Field(None, description="Observed on or after this date (yyyy-mm-dd).")
    d2: Optional[date] = Field(None, description="Observed on or before this date (yyyy-mm-dd).")
    year: Optional[int] = Field(None, ge=1, description="Observed in this year, e.g. 2022.")
    month: Optional[int] = Field(None, ge=1, le=12, description="Observed in this month of any year (1-12).")
    day: Optional[int] = Field(None, ge=1, le=31, description="Observed on this day of the month (1-31).")
    hour: Optional[int] = Field(None, ge=0, le=23, description="Observed within this hour of the day (0-23).")
    updated_since: Optional[date] = Field(None, description="Updated on or after this date (yyyy-mm-dd).")

    # Evidence and status
    photos: Optional[bool] = Field(None, description="True for observations with photos.")
    sounds: Optional[bool] = Field(None, description="True for observations with sounds.")
    geo: Optional[bool] = Field(None, description="True for observations that have coordinates.")
    captive: Optional[bool] = Field(None, description="True for captive or cultivated observations.")
    native: Optional[bool] = Field(None, description="True for taxa that are native to the observation location.")
    introduced: Optional[bool] = Field(None, description="True for taxa that are introduced at the observation location.")
    out_of_range: Optional[bool] = Field(None, description="True for taxa outside their known range.")
    verifiable: Optional[bool] = Field(
        None, description="True for observations with quality grade needs_id or research."
    )
    quality_grade: Optional[Literal["needs_id", "casual", "research"]] = Field(
        None,
        description="Quality grade. research means community-verified, needs_id means awaiting identification, "
                    "casual means missing evidence or flagged. Leave unset unless the request asks for it.",
    )
    geoprivacy: Optional[Literal["obscured", "obscured_private", "open", "private"]] = Field(
        None, description="Location privacy setting chosen by the observer."
    )
    license: Optional[License] = Field(None, description="License of the observation.")
    photo_license: Optional[License] = Field(None, description="License of at least one photo.")

    # Paging and ordering
    per_page: Optional[int] = Field(
        default=200, ge=1, le=200,
        description="Number of results to return (1-200). Leave at the default unless the user asks for fewer.",
    )
    order_by: Optional[Literal["created_at", "observed_on", "id"]] = Field(
        None,
        description="Field to sort by. created_at is when the observation was uploaded (the default), observed_on is "
                    "when the organism was observed, id sorts by observation ID. Only set when the request asks for "
                    "an ordering, such as the most recent or oldest observations.",
    )
    order: Optional[Literal["asc", "desc"]] = Field(
        None, description="Sort direction for order_by. The API default is desc, so newest first."
    )


class LLMGeneration(BaseModel):
    artifact_description: str = Field(
        description="A concise characterization of the observation data to be retrieved",
        examples=["Rattus Rattus observations in iNaturalist",
                  "Galax Urceolata iNaturalist observations since 2015"])
    search_parameters: ObservationsQueryParams = Field()