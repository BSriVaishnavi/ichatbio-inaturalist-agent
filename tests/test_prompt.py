from entrypoints.search_inaturalist_observations import SYSTEM_PROMPT
from schema import ObservationsQueryParams


def test_prompt_names_only_fields_that_exist_in_the_schema():
    for field in ["license", "photo_license", "order_by", "quality_grade", "iconic_taxa"]:
        assert field in SYSTEM_PROMPT
        assert field in ObservationsQueryParams.model_fields


def test_prompt_does_not_mention_removed_fields_or_formats():
    for stale in ["or has", "yyyy-mm, or yyyy"]:
        assert stale not in SYSTEM_PROMPT