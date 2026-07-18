import pytest
from sqlmodel import Session, create_engine

from pathtree.database.connection import init_db


@pytest.fixture(name="engine")
def engine_fixture():
    """Fixture for an in-memory SQLModel engine."""
    engine = create_engine("sqlite://")
    init_db(engine)
    return engine


@pytest.fixture(name="session")
def session_fixture(engine):
    """Fixture for an in-memory SQLModel session."""
    with Session(engine) as session:
        yield session
