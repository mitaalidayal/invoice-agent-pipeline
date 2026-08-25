import pytest

from setup_db import setup_db


@pytest.fixture(autouse=True, scope="session")
def _inventory_db():
    """Ensures inventory.db exists with the expected seed data before any
    test runs - autouse+session means this runs exactly once, before the
    first test, regardless of which tests get selected. Without this, a
    fresh clone of the repo would hit "no such table: inventory" instead of
    a real test failure.
    """
    setup_db()
