import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def point_reyes_month() -> dict:
    """Trimmed real /api/camps/availability/campground/233359/month response.

    Two sites per loop, five October 2026 nights, statuses forced to a known mix
    so assertions are deterministic. Site metadata fields are real."""
    return load_fixture("campground_month_point_reyes_233359.json")


@pytest.fixture
def permit_month_nested() -> dict:
    """Trimmed real /api/permits/{id}/availability/month response (2026 shape:
    availability keyed by division_id, dates nested under date_availability)."""
    return load_fixture("permit_month_nested_divisions.json")


@pytest.fixture
def ridb_yosemite_page() -> dict:
    return load_fixture("ridb_facilities_yosemite_page.json")


@pytest.fixture
def campground_meta() -> dict:
    return load_fixture("campground_meta_233359.json")
