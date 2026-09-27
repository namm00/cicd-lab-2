import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.database import get_db
from app.main import app


@pytest.fixture(scope="session")
def engine():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.fail("TEST_DATABASE_URL is required; use compose.test.yaml")
    parsed = make_url(url)
    if parsed.drivername != "postgresql+psycopg" or not (parsed.database or "").endswith("_test"):
        pytest.fail("Integration tests require a PostgreSQL database ending in _test")
    engine = create_engine(url)
    yield engine
    engine.dispose()


@pytest.fixture
def db(engine):
    # Migrations ran before pytest. Each test uses real SQL, inside a transaction
    # that is rolled back even when an API handler calls session.commit().
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            yield session
        transaction.rollback()


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
