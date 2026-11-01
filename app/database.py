import os
from collections.abc import Mapping
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker


def normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def database_url_from_environment(environment: Mapping[str, str]) -> str:
    is_render = environment.get("RENDER", "").lower() == "true"
    database_url = environment.get("DATABASE_URL")

    if is_render and not database_url:
        raise RuntimeError(
            "DATABASE_URL must be configured for the Render PostgreSQL database."
        )

    url = normalize_database_url(database_url or "sqlite:///./smartdesk.db")
    if is_render and make_url(url).get_backend_name() != "postgresql":
        raise RuntimeError(
            "Render deployments require DATABASE_URL to point to PostgreSQL."
        )
    return url


DATABASE_URL = database_url_from_environment(os.environ)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
if DATABASE_URL.startswith("postgresql+psycopg://"):
    connect_args["connect_timeout"] = 10
engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_migrations(target_engine=engine) -> None:
    config_path = Path(__file__).resolve().parents[1] / "alembic.ini"
    config = Config(str(config_path))
    config.set_main_option(
        "script_location",
        str(config_path.parent / "migrations"),
    )
    with target_engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
