import re
from importlib.resources import files
from pathlib import Path

from schema import ObservationsQueryParams

RESOURCES = Path(__file__).resolve().parent.parent / "src" / "resources"


def _documented_parameters() -> set[str]:
    names = set()
    for line in (RESOURCES / "records_query_format.md").read_text().splitlines():
        match = re.match(r"- ((?:`[a-z_0-9]+`(?:, | and )?)+):", line)
        if match:
            names.update(re.findall(r"`([a-z_0-9]+)`", match.group(1)))
    return names


def test_every_documented_parameter_exists_in_the_schema():
    documented = _documented_parameters()
    assert documented, "no parameters found in records_query_format.md"
    assert documented <= set(ObservationsQueryParams.model_fields), documented - set(ObservationsQueryParams.model_fields)


def test_every_schema_parameter_is_documented():
    missing = set(ObservationsQueryParams.model_fields) - _documented_parameters()
    assert not missing, f"not documented in records_query_format.md: {sorted(missing)}"


def test_tips_file_is_not_empty():
    assert (RESOURCES / "occurrence_records_tips.md").read_text().strip()
