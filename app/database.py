import logging
import os
from collections.abc import Mapping
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import DeclarativeBase, sessionmaker

logger = logging.getLogger(__name__)


def normalize_database_url(url: str) -> str:
    scheme, separator, remainder = url.partition("://")
    if not separator:
        return url

    if scheme.lower() in ("postgres", "postgresql", "postgresql+psycopg"):
        return f"postgresql+psycopg://{remainder}"
    return url


def database_url_from_environment(environment: Mapping[str, str]) -> str:
    is_render = environment.get("RENDER", "").lower() == "true"
    database_url = environment.get("DATABASE_URL")

    if database_url is not None:
        database_url = database_url.strip()
        if database_url and (
            database_url[0] in ("'", '"') or database_url[-1] in ("'", '"')
        ):
            if (
                len(database_url) < 2
                or database_url[0] not in ("'", '"')
                or database_url[-1] != database_url[0]
            ):
                raise RuntimeError(
                    "DATABASE_URL must not contain unmatched surrounding quotes."
                )
            database_url = database_url[1:-1].strip()
        if database_url and ("'" in database_url or '"' in database_url):
            raise RuntimeError(
                "DATABASE_URL must not contain unmatched surrounding quotes."
            )
        if not database_url:
            database_url = None

    if is_render and not database_url:
        raise RuntimeError(
            "DATABASE_URL must be configured for the Render PostgreSQL database."
        )

    url = normalize_database_url(database_url or "sqlite:///./smartdesk.db")
    try:
        parsed_url = make_url(url)
    except ArgumentError as error:
        logger.error(
            "SQLAlchemy could not parse DATABASE_URL; value redacted "
            "(parser_error=%s).",
            type(error).__name__,
        )
        raise RuntimeError(
            "DATABASE_URL must be a valid SQLAlchemy URL; "
            "check its scheme and percent-encoding (value redacted)."
        ) from None

    backend = parsed_url.get_backend_name()
    if is_render and backend != "postgresql":
        raise RuntimeError(
            "Render deployments require DATABASE_URL to point to PostgreSQL."
        )
    if backend == "sqlite":
        supported_driver = parsed_url.drivername in ("sqlite", "sqlite+pysqlite")
    elif backend == "postgresql":
        supported_driver = parsed_url.drivername == "postgresql+psycopg"
    else:
        supported_driver = False

    if not supported_driver:
        raise RuntimeError(
            "DATABASE_URL uses an unsupported database backend or driver."
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
