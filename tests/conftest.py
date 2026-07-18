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
