from datetime import date
from urllib.parse import parse_qsl, urlparse

from entrypoints.search_inaturalist_observations import build_query_url
from schema import ObservationsQueryParams

API = "https://api.inaturalist.org/v1/observations"


def query_of(url):
    return parse_qsl(urlparse(url).query)


def test_booleans_are_lowercase():
    # The API silently ignores True and False, it only understands true and false
    url = build_query_url(API, {"photos": True, "captive": False})
    assert query_of(url) == [("photos", "true"), ("captive", "false")]


def test_strings_are_url_encoded():
    url = build_query_url(API, {"taxon_name": "Rattus rattus"})
    assert "Rattus+rattus" in url
    assert query_of(url) == [("taxon_name", "Rattus rattus")]


def test_lists_repeat_a_bracketed_key():
    url = build_query_url(API, {"iconic_taxa": ["Aves", "Mammalia"]})
    assert query_of(url) == [("iconic_taxa[]", "Aves"), ("iconic_taxa[]", "Mammalia")]


def test_dates_are_iso_formatted():
    url = build_query_url(API, {"d1": date(2020, 1, 1)})
    assert query_of(url) == [("d1", "2020-01-01")]


def test_numbers_are_plain_text():
    url = build_query_url(API, {"lat": 40.71, "per_page": 50})
    assert query_of(url) == [("lat", "40.71"), ("per_page", "50")]


def test_url_starts_with_the_api_endpoint():
    assert build_query_url(API, {"per_page": 1}).startswith(API + "?")


def test_schema_output_round_trips_into_a_correct_url():
    params = ObservationsQueryParams(
        taxon_name="Rattus rattus", photos=True, native=False, d1="2020-01-01", iconic_taxa=["Aves"]
    ).model_dump(exclude_none=True, by_alias=True)
    query = dict(query_of(build_query_url(API, params)))
    assert query["photos"] == "true"
    assert query["native"] == "false"
    assert query["d1"] == "2020-01-01"
    assert query["taxon_name"] == "Rattus rattus"
    assert query["iconic_taxa[]"] == "Aves"