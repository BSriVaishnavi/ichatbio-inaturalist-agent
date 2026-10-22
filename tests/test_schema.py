from datetime import date

import pytest
from pydantic import ValidationError

from schema import LLMGeneration, ObservationsQueryParams


def make(**kwargs):
    return ObservationsQueryParams(**kwargs)


def test_empty_params_use_defaults():
    params = make()
    assert params.per_page == 200
    assert params.model_dump(exclude_none=True) == {"per_page": 200}


def test_dump_contains_only_fields_that_were_set():
    params = make(taxon_name="Rattus rattus", photos=True, quality_grade="research")
    assert params.model_dump(exclude_none=True) == {
        "taxon_name": "Rattus rattus",
        "photos": True,
        "quality_grade": "research",
        "per_page": 200,
    }


@pytest.mark.parametrize(
    "field, value",
    [
        ("m1", 6),
        ("m2", 6),
        ("h1", 1),
        ("h2", 1),
        ("has", ["photos"]),
        ("on", "2020-01-01"),
        ("extra", ["fields"]),
        ("banana", 1),
    ],
)
def test_undocumented_or_dead_fields_are_rejected(field, value):
    # The API silently ignores unknown parameters, so the schema must reject them instead
    with pytest.raises(ValidationError):
        make(**{field: value})


@pytest.mark.parametrize("grade", ["needs_id", "casual", "research"])
def test_quality_grade_accepts_all_three_values(grade):
    assert make(quality_grade=grade).quality_grade == grade


def test_quality_grade_rejects_unknown_value():
    with pytest.raises(ValidationError):
        make(quality_grade="verified")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"lat": 91},
        {"lat": -91},
        {"lng": 181},
        {"lng": -181},
        {"nelat": 91},
        {"swlng": -181},
        {"radius": 0},
        {"radius": -5},
        {"month": 0},
        {"month": 13},
        {"day": 0},
        {"day": 32},
        {"hour": -1},
        {"hour": 24},
        {"per_page": 0},
        {"per_page": 201},
    ],
)
def test_out_of_range_values_are_rejected(kwargs):
    with pytest.raises(ValidationError):
        make(**kwargs)


def test_boundary_values_are_accepted():
    params = make(lat=90, lng=-180, radius=0.1, month=12, day=31, hour=0, per_page=1)
    assert params.lat == 90
    assert params.lng == -180
    assert params.per_page == 1


def test_dates_parse_from_iso_strings():
    params = make(d1="2020-01-01", d2="2020-12-31", observed_on="2020-06-15")
    assert params.d1 == date(2020, 1, 1)
    assert params.d2 == date(2020, 12, 31)
    assert params.observed_on == date(2020, 6, 15)


def test_invalid_date_is_rejected():
    with pytest.raises(ValidationError):
        make(d1="2020-13-45")


def test_license_accepts_documented_values_only():
    assert make(license="cc0").license == "cc0"
    for bad in ["CC-BY", "none", "any"]:
        with pytest.raises(ValidationError):
            make(license=bad)


def test_iconic_taxa_accepts_a_list_and_rejects_unknown_groups():
    assert make(iconic_taxa=["Aves", "Mammalia"]).iconic_taxa == ["Aves", "Mammalia"]
    with pytest.raises(ValidationError):
        make(iconic_taxa=["Birds"])


def test_llm_generation_parses_nested_parameters():
    result = LLMGeneration(
        artifact_description="Rattus rattus observations",
        search_parameters={"taxon_name": "Rattus rattus"},
    )
    assert result.search_parameters.taxon_name == "Rattus rattus"


def test_llm_generation_requires_artifact_description():
    with pytest.raises(ValidationError):
        LLMGeneration(search_parameters={"taxon_name": "Rattus rattus"})


def test_llm_generation_rejects_invented_search_field():
    with pytest.raises(ValidationError):
        LLMGeneration(artifact_description="x", search_parameters={"m1": 6})