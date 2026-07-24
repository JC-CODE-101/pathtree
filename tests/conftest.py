from pathlib import Path

import pytest
from sqlmodel import Session

from pathtree.database.connection import create_db_engine, init_db


@pytest.fixture(name="engine")
def engine_fixture():
    """Fixture for an in-memory SQLModel engine."""
    engine = create_db_engine(Path(":memory:"))
    init_db(engine)
    return engine


@pytest.fixture(name="session")
def session_fixture(engine):
    """Fixture for an in-memory SQLModel session."""
    with Session(engine) as session:
        yield session


@pytest.fixture(autouse=True)
def disable_nerd_fonts_for_tests():
    """Autouse fixture to disable Nerd Fonts for all tests by default."""
    from pathtree.utils.icons import icon_registry

    old_state = icon_registry.nerd_fonts_enabled
    icon_registry.nerd_fonts_enabled = False
    yield
    icon_registry.nerd_fonts_enabled = old_state


@pytest.fixture(autouse=True)
def mock_clipboard_for_tests(request):
    """Autouse fixture to mock PlatformLauncher.copy_to_clipboard globally."""
    if "test_platform_launcher_copy_to_clipboard" in request.node.name:
        yield
    else:
        from unittest.mock import patch

        with patch(
            "pathtree.utils.launcher.PlatformLauncher.copy_to_clipboard"
        ) as mock:
            yield mock
