import os
from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import URL, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session


class Base(DeclarativeBase):
    pass


def database_url() -> str | URL:
    # CI uses DATABASE_URL. Compose passes separate fields so passwords do not
    # need URL escaping. There is deliberately no SQLite fallback.
    if url := os.getenv("DATABASE_URL"):
        if not url.startswith("postgresql+psycopg://"):
            raise ValueError("DATABASE_URL must use postgresql+psycopg://")
        return url
    return URL.create(
        "postgresql+psycopg",
        username=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.environ["POSTGRES_DB"],
    )


@lru_cache
def get_engine() -> Engine:
    return create_engine(database_url(), pool_pre_ping=True, connect_args={"connect_timeout": 3})


def get_db() -> Generator[Session]:
    with Session(get_engine()) as session:
        yield session
