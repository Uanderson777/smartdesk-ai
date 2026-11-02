from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from threading import Barrier

import jwt
import pytest
from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, make_url, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main as main_module
from app.database import (
    Base,
    database_url_from_environment,
    get_db,
    normalize_database_url,
    run_migrations,
)
from app.dependencies import TenantContext
from app.main import app
from app.models import Company, Membership, Ticket, User, UserRole
from app.schemas import UserActiveUpdate, UserRoleUpdate
from app.security import create_access_token, hash_password, verify_password
from app.users import update_user_active_status, update_user_role


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "postgres://user:password@db.example:5432/smartdesk",
            "postgresql+psycopg://user:password@db.example:5432/smartdesk",
        ),
        (
            "postgresql://user:password@db.example:5432/smartdesk",
            "postgresql+psycopg://user:password@db.example:5432/smartdesk",
        ),
        (
            "postgresql+psycopg://user:password@db.example:5432/smartdesk",
            "postgresql+psycopg://user:password@db.example:5432/smartdesk",
        ),
        ("sqlite:///./smartdesk.db", "sqlite:///./smartdesk.db"),
    ],
)
def test_normalize_database_url(url, expected):
    assert normalize_database_url(url) == expected


def test_database_url_defaults_to_sqlite_outside_render():
    assert database_url_from_environment({}) == "sqlite:///./smartdesk.db"


def test_render_requires_database_url():
    with pytest.raises(RuntimeError, match="DATABASE_URL must be configured"):
        database_url_from_environment({"RENDER": "true"})


def test_render_rejects_non_postgresql_database():
    with pytest.raises(RuntimeError, match="require DATABASE_URL.*PostgreSQL"):
        database_url_from_environment(
            {"RENDER": "true", "DATABASE_URL": "sqlite:///./smartdesk.db"}
        )


def test_render_normalizes_postgresql_database_url():
    assert database_url_from_environment(
        {
            "RENDER": "true",
            "DATABASE_URL": "postgresql://user:password@db.example:5432/smartdesk",
        }
    ) == "postgresql+psycopg://user:password@db.example:5432/smartdesk"


@pytest.mark.parametrize(
    "url",
    [
        "  postgresql://fake-user:fake-password@db.example:5432/smartdesk  ",
        '"postgresql://fake-user:fake-password@db.example:5432/smartdesk"',
        "'postgresql://fake-user:fake-password@db.example:5432/smartdesk'",
    ],
)
def test_database_url_strips_whitespace_and_balanced_quotes(url):
    assert database_url_from_environment({"DATABASE_URL": url}) == (
        "postgresql+psycopg://fake-user:fake-password@db.example:5432/smartdesk"
    )


@pytest.mark.parametrize(
    "url",
    [
        "not-a-sqlalchemy-url",
        "'postgresql://fake-user:fake-password@db.example:5432/smartdesk",
        '"postgresql://fake-user:fake-password@db.example:5432/smartdesk\'',
        "postgresql+asyncpg://fake-user:fake-password@db.example:5432/smartdesk",
    ],
)
def test_database_url_rejects_invalid_quotes_and_unsupported_drivers(url):
    with pytest.raises(RuntimeError) as error:
        database_url_from_environment({"DATABASE_URL": url})

    assert url not in str(error.value)


def test_database_url_decodes_percent_encoded_credentials():
    url = database_url_from_environment(
        {
            "RENDER": "true",
            "DATABASE_URL": (
                "postgresql://fake%40user:fake%3Apassword"
                "@db.example:5432/smartdesk"
            ),
        }
    )
    parsed_url = make_url(url)

    assert parsed_url.drivername == "postgresql+psycopg"
    assert parsed_url.username == "fake@user"
    assert parsed_url.password == "fake:password"


def test_lifespan_runs_alembic_migrations(test_engine):
    with TestClient(app):
        assert inspect(test_engine).has_table("alembic_version")


def test_lifespan_stops_before_migrations_without_jwt_secret(
    test_engine, monkeypatch
):
    monkeypatch.delenv("JWT_SECRET_KEY")

    def migrations_must_not_run(_engine):
        raise AssertionError("Migrations must not run without the JWT secret.")

    monkeypatch.setattr(main_module, "run_migrations", migrations_must_not_run)

    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        with TestClient(app):
            pass


def test_lifespan_propagates_postgresql_connection_failure(test_engine, monkeypatch):
    def fail_connection():
        raise OperationalError(
            "connect",
            {},
            OSError("simulated PostgreSQL connection failure"),
        )

    unavailable_engine = create_engine(
        "postgresql+psycopg://localhost/smartdesk",
        creator=fail_connection,
    )
    monkeypatch.setattr(main_module, "engine", unavailable_engine)
    try:
        with pytest.raises(OperationalError, match="simulated PostgreSQL"):
            with TestClient(app):
                pass
    finally:
        unavailable_engine.dispose()


@pytest.fixture()
def test_engine(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-with-at-least-32-bytes")
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    monkeypatch.setattr(main_module, "engine", test_engine)
    yield test_engine
    test_engine.dispose()


@pytest.fixture()
def session_factory(test_engine):
    return sessionmaker(
        bind=test_engine, autoflush=False, autocommit=False
    )


@pytest.fixture()
def client(test_engine, session_factory):
    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture()
def authenticated_client(client, session_factory):
    _, _, token = create_role_client(
        client, session_factory, "tester@example.com", UserRole.REQUESTER
    )
    client.headers["Authorization"] = token
    return client


def test_cors_preflight_allows_local_frontend(client):
    response = client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_default_cors_origins_include_vercel_frontend():
    assert main_module.cors_origins_from_environment({}) == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://smartdesk-ai-app.vercel.app",
    ]


def test_cors_origins_include_explicitly_configured_vercel_domains():
    assert main_module.cors_origins_from_environment(
        {
            "CORS_ORIGINS": (
                " https://smartdesk-ai.vercel.app/ , "
                "https://preview-smartdesk.vercel.app "
            )
        }
    ) == [
        "https://smartdesk-ai.vercel.app",
        "https://preview-smartdesk.vercel.app",
        "https://smartdesk-ai-app.vercel.app",
    ]


def test_configured_cors_origins_keep_vercel_frontend_without_duplicates():
    assert main_module.cors_origins_from_environment(
        {
            "CORS_ORIGINS": (
                "https://smartdesk-ai-app.vercel.app/,"
                "https://other.example,"
                "https://smartdesk-ai-app.vercel.app"
            )
        }
    ) == [
        "https://smartdesk-ai-app.vercel.app",
        "https://other.example",
    ]


def create_role_client(client, session_factory, email, role):
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Test User",
            "email": email,
            "password": "secure-password",
        },
    )
    assert registration.status_code == 201
    with session_factory() as db:
        user = db.scalar(select(User).where(User.email == email))
        assert user is not None
        user.role = role
        membership = db.scalar(
            select(Membership).where(Membership.user_id == user.id)
        )
        assert membership is not None
        membership.role = role
        db.commit()
        user_id = user.id

    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "secure-password"},
    )
    assert login.status_code == 200
    return client, user_id, f"Bearer {login.json()['access_token']}"


@pytest.fixture()
def admin_client(client, session_factory):
    _, _, token = create_role_client(
        client, session_factory, "admin@example.com", UserRole.ADMIN
    )
    with TestClient(app) as role_client:
        role_client.headers["Authorization"] = token
        yield role_client


@pytest.fixture()
def technician_client(client, session_factory):
    _, _, token = create_role_client(
        client, session_factory, "tech@example.com", UserRole.TECHNICIAN
    )
    with TestClient(app) as role_client:
        role_client.headers["Authorization"] = token
        yield role_client


def test_register_user_returns_public_data_and_stores_password_hash(
    client, session_factory
):
    password = "secure-password"
    response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "New User",
            "email": "New.User@example.com",
            "password": password,
            "role": "admin",
        },
    )

    assert response.status_code == 201
    assert response.json() == {
        "id": 1,
        "full_name": "New User",
        "email": "new.user@example.com",
    }
    with session_factory() as db:
        user = db.scalar(select(User).where(User.email == "new.user@example.com"))
        assert user is not None
        assert user.full_name == "New User"
        assert user.role == UserRole.REQUESTER
        assert user.password_hash != password
        assert verify_password(password, user.password_hash)


def test_register_requires_non_empty_full_name(client):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "missing-name@example.com", "password": "secure-password"},
    )
    assert response.status_code == 422

    response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "   ",
            "email": "blank-name@example.com",
            "password": "secure-password",
        },
    )
    assert response.status_code == 422


def test_register_duplicate_email_returns_409(client):
    payload = {
        "full_name": "Duplicate User",
        "email": "duplicate@example.com",
        "password": "secure-password",
    }
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201

    response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Duplicate User",
            "email": "DUPLICATE@example.com",
            "password": "another-password",
        },
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "E-mail já cadastrado."}


def test_login_returns_bearer_token(client):
    client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Login User",
            "email": "login@example.com",
            "password": "secure-password",
        },
    )

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "LOGIN@example.com", "password": "secure-password"},
    )

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert jwt.decode(
        response.json()["access_token"],
        "test-secret-key-with-at-least-32-bytes",
        algorithms=["HS256"],
    )["sub"] == "1"
    profile = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {response.json()['access_token']}"},
    )
    assert profile.status_code == 200
    assert profile.json()["full_name"] == "Login User"


def test_login_accepts_smartdeskai_local_email(client, session_factory):
    with session_factory() as db:
        user = User(
            full_name="Técnico de Teste",
            email="tecnico.teste@smartdeskai.local",
            password_hash=hash_password("secure-password"),
            role=UserRole.TECHNICIAN,
            is_active=True,
        )
        db.add(user)
        db.flush()
        db.add(
            Membership(
                user_id=user.id,
                company_id=1,
                role=UserRole.TECHNICIAN,
                is_active=True,
            )
        )
        db.commit()
        user_id = user.id

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "tecnico.teste@smartdeskai.local",
            "password": "secure-password",
            "company_id": 1,
        },
    )

    assert response.status_code == 200
    profile = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer " + response.json()["access_token"]},
    )
    assert profile.status_code == 200
    assert profile.json() == {
        "id": user_id,
        "full_name": "Técnico de Teste",
        "email": "tecnico.teste@smartdeskai.local",
    }


def test_login_rejects_other_reserved_local_domains(client):
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "user@other.local",
            "password": "secure-password",
        },
    )

    assert response.status_code == 422


def test_authenticated_user_without_name_returns_null(
    client, session_factory
):
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Legacy User",
            "email": "legacy-name@example.com",
            "password": "secure-password",
        },
    )
    assert registration.status_code == 201
    with session_factory() as db:
        user = db.scalar(select(User).where(User.email == "legacy-name@example.com"))
        assert user is not None
        user.full_name = None
        db.commit()

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "legacy-name@example.com", "password": "secure-password"},
    )
    assert login.status_code == 200
    profile = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert profile.status_code == 200
    assert profile.json()["full_name"] is None


def test_current_user_profile_requires_authentication(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_login_requires_explicit_selection_for_multiple_active_memberships(
    client, session_factory
):
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Multi User",
            "email": "multi@example.com",
            "password": "secure-password",
        },
    )
    assert registration.status_code == 201

    with session_factory() as db:
        second_company = Company(name="Second company")
        db.add(second_company)
        db.flush()
        user = db.scalar(select(User).where(User.email == "multi@example.com"))
        assert user is not None
        db.add(
            Membership(
                user_id=user.id,
                company_id=second_company.id,
                role=UserRole.TECHNICIAN,
                is_active=True,
            )
        )
        second_company_id = second_company.id
        db.commit()

    ambiguous_login = client.post(
        "/api/v1/auth/login",
        json={"email": "multi@example.com", "password": "secure-password"},
    )
    assert ambiguous_login.status_code == 409
    companies = ambiguous_login.json()["detail"]["companies"]
    assert {company["id"] for company in companies} == {1, second_company_id}

    unauthorized_selection = client.post(
        "/api/v1/auth/login",
        json={
            "email": "multi@example.com",
            "password": "secure-password",
            "company_id": 999,
        },
    )
    assert unauthorized_selection.status_code == 403

    selected_login = client.post(
        "/api/v1/auth/login",
        json={
            "email": "multi@example.com",
            "password": "secure-password",
            "company_id": second_company_id,
        },
    )
    assert selected_login.status_code == 200
    token = selected_login.json()["access_token"]
    assert client.get(
        "/api/v1/tickets",
        headers={"Authorization": f"Bearer {token}"},
    ).status_code == 200


def test_tenant_scope_prevents_cross_company_ticket_and_user_access(
    authenticated_client, admin_client, technician_client, client, session_factory
):
    with session_factory() as db:
        company_b = Company(name="Company B")
        db.add(company_b)
        db.flush()
        requester_b = User(
            email="requester-b@example.com",
            password_hash=hash_password("secure-password"),
            role=UserRole.REQUESTER,
        )
        technician_b = User(
            email="technician-b@example.com",
            password_hash=hash_password("secure-password"),
            role=UserRole.TECHNICIAN,
        )
        admin_b = User(
            email="admin-b@example.com",
            password_hash=hash_password("secure-password"),
            role=UserRole.ADMIN,
        )
        db.add_all([requester_b, technician_b, admin_b])
        db.flush()
        db.add_all(
            [
                Membership(
                    user_id=requester_b.id,
                    company_id=company_b.id,
                    role=UserRole.REQUESTER,
                    is_active=True,
                ),
                Membership(
                    user_id=technician_b.id,
                    company_id=company_b.id,
                    role=UserRole.TECHNICIAN,
                    is_active=True,
                ),
                Membership(
                    user_id=admin_b.id,
                    company_id=company_b.id,
                    role=UserRole.ADMIN,
                    is_active=True,
                ),
            ]
        )
        company_b_id = company_b.id
        requester_b_id = requester_b.id
        technician_b_id = technician_b.id
        db.commit()

    requester_b_login = client.post(
        "/api/v1/auth/login",
        json={
            "email": "requester-b@example.com",
            "password": "secure-password",
            "company_id": company_b_id,
        },
    )
    admin_b_login = client.post(
        "/api/v1/auth/login",
        json={
            "email": "admin-b@example.com",
            "password": "secure-password",
            "company_id": company_b_id,
        },
    )
    assert requester_b_login.status_code == admin_b_login.status_code == 200
    requester_b_token = requester_b_login.json()["access_token"]
    admin_b_token = admin_b_login.json()["access_token"]

    ticket_a = authenticated_client.post(
        "/api/v1/tickets",
        json={
            "title": "Ticket for company A",
            "description": "A sufficiently long description.",
            "category": "software",
        },
    ).json()
    ticket_b_response = client.post(
        "/api/v1/tickets",
        headers={"Authorization": f"Bearer {requester_b_token}"},
        json={
            "title": "Ticket for company B",
            "description": "Another sufficiently long description.",
            "category": "software",
        },
    )
    assert ticket_b_response.status_code == 201
    ticket_b = ticket_b_response.json()
    with session_factory() as db:
        persisted_ticket_a = db.get(Ticket, ticket_a["id"])
        persisted_ticket_b = db.get(Ticket, ticket_b["id"])
        assert persisted_ticket_a is not None
        assert persisted_ticket_b is not None
        assert persisted_ticket_a.tenant_id == 1
        assert persisted_ticket_b.tenant_id == company_b_id

    requester_a_token = authenticated_client.headers["Authorization"]
    assert client.get(
        "/api/v1/tickets",
        headers={"Authorization": requester_a_token},
    ).json() == [ticket_a]
    assert client.get(
        f"/api/v1/tickets/{ticket_b['id']}",
        headers={"Authorization": requester_a_token},
    ).status_code == 404

    technician_a_token = technician_client.headers["Authorization"]
    tech_a_list = client.get(
        "/api/v1/tickets",
        headers={"Authorization": technician_a_token},
    )
    assert tech_a_list.status_code == 200
    visible_to_technician_a = {
        ticket["id"] for ticket in tech_a_list.json()
    }
    assert ticket_a["id"] in visible_to_technician_a
    assert ticket_b["id"] not in visible_to_technician_a
    assert client.post(
        f"/api/v1/tickets/{ticket_b['id']}/claim",
        headers={"Authorization": technician_a_token},
    ).status_code == 404

    assert ticket_b["id"] not in {
        ticket["id"] for ticket in admin_client.get("/api/v1/tickets").json()
    }
    available_a = admin_client.get("/api/v1/tickets/available")
    available_b = client.get(
        "/api/v1/tickets/available",
        headers={"Authorization": f"Bearer {admin_b_token}"},
    )
    assert available_a.status_code == available_b.status_code == 200
    assert ticket_b["id"] not in {
        ticket["id"] for ticket in available_a.json()
    }
    assert ticket_b["id"] in {
        ticket["id"] for ticket in available_b.json()
    }
    users_a = admin_client.get("/api/v1/users")
    assert users_a.status_code == 200
    assert requester_b_id not in {user["id"] for user in users_a.json()}
    assert admin_client.patch(
        f"/api/v1/users/{requester_b_id}/role",
        json={"role": "technician"},
    ).status_code == 404
    assert admin_client.patch(
        f"/api/v1/tickets/{ticket_b['id']}/assignee",
        json={"technician_id": requester_b_id},
    ).status_code == 404
    assert admin_client.patch(
        f"/api/v1/tickets/{ticket_a['id']}/assignee",
        json={"technician_id": technician_b_id},
    ).status_code == 422

    assert client.get(
        f"/api/v1/tickets/{ticket_a['id']}",
        headers={"Authorization": f"Bearer {admin_b_token}"},
    ).status_code == 404


def test_deactivated_membership_revokes_existing_token(
    authenticated_client, session_factory
):
    token = authenticated_client.headers["Authorization"]
    with session_factory() as db:
        user = db.scalar(select(User).where(User.email == "tester@example.com"))
        assert user is not None
        membership = db.scalar(
            select(Membership).where(
                Membership.user_id == user.id,
                Membership.company_id == 1,
            )
        )
        assert membership is not None
        membership.is_active = False
        db.commit()

    response = authenticated_client.get(
        "/api/v1/tickets",
        headers={"Authorization": token},
    )
    assert response.status_code == 403
    profile = authenticated_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": token},
    )
    assert profile.status_code == 403


@pytest.mark.parametrize(
    "email,password",
    [
        ("unknown@example.com", "secure-password"),
        ("known@example.com", "wrong-password"),
    ],
)
def test_login_invalid_credentials_returns_401(client, email, password):
    client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Known User",
            "email": "known@example.com",
            "password": "secure-password",
        },
    )

    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "E-mail ou senha inválidos."}
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "method,path,payload",
    [
        (
            "post",
            "/api/v1/tickets",
            {
                "title": "Acesso à rede",
                "description": "Solicito acesso à rede corporativa.",
                "category": "rede",
            },
        ),
        ("get", "/api/v1/tickets", None),
        ("get", "/api/v1/tickets/1", None),
        ("patch", "/api/v1/tickets/1/status", {"status": "resolvido"}),
    ],
)
def test_ticket_endpoints_require_authentication(client, method, path, payload):
    request = getattr(client, method)
    response = request(path, json=payload) if payload is not None else request(path)

    assert response.status_code == 401
    assert response.json() == {"detail": "Credenciais de autenticação inválidas."}
    assert response.headers["www-authenticate"] == "Bearer"


def test_expired_token_is_rejected(client, authenticated_client):
    expired_token = create_access_token(
        "1",
        expires_delta=timedelta(minutes=-1),
    )
    client.headers["Authorization"] = f"Bearer {expired_token}"

    response = client.get("/api/v1/tickets")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_invalid_token_is_rejected(client):
    client.headers["Authorization"] = "Bearer not-a-valid-token"

    response = client.get("/api/v1/tickets")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_authenticated_user_can_create_ticket(authenticated_client):
    response = authenticated_client.post(
        "/api/v1/tickets",
        json={
            "title": "Acesso à rede",
            "description": "Solicito acesso à rede corporativa.",
            "category": "rede",
        },
    )

    assert response.status_code == 201
    assert response.json()["requester_id"] == 1


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_root_returns_service_info(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {
        "service": "SmartDesk AI",
        "version": "0.1.0",
        "description": "API inteligente de gerenciamento de chamados de Service Desk",
        "status": "online",
        "documentation": "/docs",
    }


def test_create_and_read_ticket(authenticated_client):
    payload = {
        "title": "Computador sem internet",
        "description": "A estação não consegue acessar sites externos.",
        "category": "rede",
        "priority": "alta",
    }
    created = authenticated_client.post("/api/v1/tickets", json=payload)
    assert created.status_code == 201
    ticket_id = created.json()["id"]

    fetched = authenticated_client.get(f"/api/v1/tickets/{ticket_id}")
    assert fetched.status_code == 200
    assert fetched.json()["title"] == payload["title"]
    assert fetched.json()["status"] == "aberto"


def test_list_tickets(authenticated_client):
    payload = {
        "title": "Falha ao abrir sistema",
        "description": "Aplicativo apresenta erro ao iniciar.",
        "category": "software",
        "priority": "media",
    }
    authenticated_client.post("/api/v1/tickets", json=payload)
    response = authenticated_client.get("/api/v1/tickets")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_admin_cannot_start_ticket_without_active_assignee(
    admin_client, session_factory
):
    payload = {
        "title": "Solicitação de acesso",
        "description": "Usuário precisa de acesso ao sistema interno.",
        "category": "acesso",
        "priority": "baixa",
    }
    created = admin_client.post("/api/v1/tickets", json=payload).json()
    response = admin_client.patch(
        f"/api/v1/tickets/{created['id']}/status",
        json={"status": "em_atendimento"},
    )
    assert response.status_code == 409
    with session_factory() as db:
        ticket = db.get(Ticket, created["id"])
        assert ticket is not None
        assert ticket.status == "aberto"
        assert ticket.assigned_technician_id is None


def test_update_ticket_status_after_admin_assigns_active_technician(
    admin_client, authenticated_client, technician_client, session_factory
):
    created = authenticated_client.post(
        "/api/v1/tickets",
        json={
            "title": "Solicitação de acesso",
            "description": "Usuário precisa de acesso ao sistema interno.",
            "category": "acesso",
        },
    ).json()
    with session_factory() as db:
        technician = db.scalar(
            select(User).where(User.email == "tech@example.com")
        )
        assert technician is not None
        technician_id = technician.id

    assigned = admin_client.patch(
        f"/api/v1/tickets/{created['id']}/assignee",
        json={"technician_id": technician_id},
    )
    assert assigned.status_code == 200
    response = admin_client.patch(
        f"/api/v1/tickets/{created['id']}/status",
        json={"status": "em_atendimento"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "em_atendimento"
    assert response.json()["assigned_technician_id"] == technician_id


@pytest.mark.parametrize("inactive_record", ["user", "membership"])
def test_admin_cannot_start_ticket_with_inactive_assignee(
    admin_client,
    authenticated_client,
    technician_client,
    session_factory,
    inactive_record,
):
    created = authenticated_client.post(
        "/api/v1/tickets",
        json={
            "title": "Chamado com técnico inativo",
            "description": "Descrição suficientemente longa.",
            "category": "software",
        },
    ).json()
    with session_factory() as db:
        technician = db.scalar(
            select(User).where(User.email == "tech@example.com")
        )
        assert technician is not None
        technician_id = technician.id
        membership = db.scalar(
            select(Membership).where(Membership.user_id == technician_id)
        )
        assert membership is not None
        ticket = db.get(Ticket, created["id"])
        assert ticket is not None
        ticket.assigned_technician_id = technician_id
        if inactive_record == "user":
            technician.is_active = False
        else:
            membership.is_active = False
        db.commit()

    response = admin_client.patch(
        f"/api/v1/tickets/{created['id']}/status",
        json={"status": "em_atendimento"},
    )
    assert response.status_code == 409
    with session_factory() as db:
        ticket = db.get(Ticket, created["id"])
        assert ticket is not None
        assert ticket.status == "aberto"
        assert ticket.assigned_technician_id == technician_id


@pytest.mark.parametrize("inactive_record", ["user", "membership"])
def test_admin_cannot_assign_inactive_technician(
    admin_client,
    authenticated_client,
    technician_client,
    session_factory,
    inactive_record,
):
    created = authenticated_client.post(
        "/api/v1/tickets",
        json={
            "title": "Chamado sem técnico",
            "description": "Descrição suficientemente longa.",
            "category": "software",
        },
    ).json()
    with session_factory() as db:
        technician = db.scalar(
            select(User).where(User.email == "tech@example.com")
        )
        assert technician is not None
        technician_id = technician.id
        membership = db.scalar(
            select(Membership).where(Membership.user_id == technician_id)
        )
        assert membership is not None
        if inactive_record == "user":
            technician.is_active = False
        else:
            membership.is_active = False
        db.commit()

    response = admin_client.patch(
        f"/api/v1/tickets/{created['id']}/assignee",
        json={"technician_id": technician_id},
    )
    assert response.status_code == 422
    with session_factory() as db:
        ticket = db.get(Ticket, created["id"])
        assert ticket is not None
        assert ticket.status == "aberto"
        assert ticket.assigned_technician_id is None


def test_missing_ticket_returns_404(authenticated_client):
    response = authenticated_client.get("/api/v1/tickets/999")
    assert response.status_code == 404
    assert response.json() == {"detail": "Chamado não encontrado."}


def test_update_missing_ticket_returns_404(authenticated_client):
    response = authenticated_client.patch(
        "/api/v1/tickets/999/status",
        json={"status": "em_atendimento"},
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Chamado não encontrado."}


def test_invalid_ticket_is_rejected(authenticated_client):
    response = authenticated_client.post(
        "/api/v1/tickets",
        json={
            "title": "abc",
            "description": "curta",
            "category": "inexistente",
            "priority": "urgente",
        },
    )
    assert response.status_code == 422
    errors = response.json()["detail"]
    assert isinstance(errors, list)
    assert {tuple(error["loc"]) for error in errors} == {
        ("body", "title"),
        ("body", "description"),
        ("body", "category"),
        ("body", "priority"),
    }
    assert all({"loc", "msg", "type"} <= error.keys() for error in errors)


def test_requester_only_lists_and_reads_own_tickets(
    authenticated_client, session_factory
):
    created = authenticated_client.post(
        "/api/v1/tickets",
        json={
            "title": "Chamado próprio",
            "description": "Descrição suficientemente longa.",
            "category": "software",
        },
    ).json()
    other, _, other_token = create_role_client(
        authenticated_client, session_factory, "other@example.com", UserRole.REQUESTER
    )

    response = other.get("/api/v1/tickets", headers={"Authorization": other_token})
    assert response.status_code == 200
    assert response.json() == []
    assert (
        other.get(
            f"/api/v1/tickets/{created['id']}",
            headers={"Authorization": other_token},
        ).status_code
        == 403
    )


def test_requester_cannot_update_ticket_status(authenticated_client):
    created = authenticated_client.post(
        "/api/v1/tickets",
        json={
            "title": "Chamado próprio",
            "description": "Descrição suficientemente longa.",
            "category": "software",
        },
    ).json()

    response = authenticated_client.patch(
        f"/api/v1/tickets/{created['id']}/status",
        json={"status": "resolvido"},
    )

    assert response.status_code == 403


def test_technician_can_claim_and_update_available_ticket(
    authenticated_client, technician_client
):
    created = authenticated_client.post(
        "/api/v1/tickets",
        json={
            "title": "Chamado para atendimento",
            "description": "Descrição suficientemente longa.",
            "category": "software",
        },
    ).json()

    available = technician_client.get("/api/v1/tickets/available")
    assert available.status_code == 200
    assert [ticket["id"] for ticket in available.json()] == [created["id"]]
    assert [ticket["id"] for ticket in technician_client.get(
        "/api/v1/tickets"
    ).json()] == [created["id"]]
    assert technician_client.get(
        f"/api/v1/tickets/{created['id']}"
    ).status_code == 200

    claimed = technician_client.post(f"/api/v1/tickets/{created['id']}/claim")
    assert claimed.status_code == 200
    assert claimed.json()["assigned_technician_id"] == 2
    assert claimed.json()["status"] == "em_atendimento"

    updated = technician_client.patch(
        f"/api/v1/tickets/{created['id']}/status",
        json={"status": "resolvido"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "resolvido"


def test_only_one_technician_can_claim_ticket(
    authenticated_client, technician_client, client, session_factory
):
    created = authenticated_client.post(
        "/api/v1/tickets",
        json={
            "title": "Chamado compartilhado",
            "description": "Descrição suficientemente longa.",
            "category": "software",
        },
    ).json()
    _, _, second_token = create_role_client(
        client, session_factory, "tech2@example.com", UserRole.TECHNICIAN
    )

    first_claim = technician_client.post(f"/api/v1/tickets/{created['id']}/claim")
    second_claim = client.post(
        f"/api/v1/tickets/{created['id']}/claim",
        headers={"Authorization": second_token},
    )

    assert first_claim.status_code == 200
    assert second_claim.status_code == 409


def test_technician_cannot_view_ticket_assigned_to_another_technician(
    authenticated_client, technician_client, client, session_factory
):
    created = authenticated_client.post(
        "/api/v1/tickets",
        json={
            "title": "Chamado atribuído",
            "description": "Descrição suficientemente longa.",
            "category": "software",
        },
    ).json()
    _, _, second_token = create_role_client(
        client, session_factory, "other-tech@example.com", UserRole.TECHNICIAN
    )
    assert technician_client.post(
        f"/api/v1/tickets/{created['id']}/claim"
    ).status_code == 200

    response = client.get(
        f"/api/v1/tickets/{created['id']}",
        headers={"Authorization": second_token},
    )

    assert response.status_code == 403


def test_technician_cannot_create_or_update_unassigned_ticket(
    authenticated_client, technician_client
):
    created = authenticated_client.post(
        "/api/v1/tickets",
        json={
            "title": "Chamado não atribuído",
            "description": "Descrição suficientemente longa.",
            "category": "software",
        },
    ).json()
    create_response = technician_client.post(
        "/api/v1/tickets",
        json={
            "title": "Tentativa técnica",
            "description": "Descrição suficientemente longa.",
            "category": "software",
        },
    )
    update_response = technician_client.patch(
        f"/api/v1/tickets/{created['id']}/status",
        json={"status": "resolvido"},
    )

    assert create_response.status_code == 403
    assert update_response.status_code == 403


def test_admin_can_assign_and_unassign_ticket(
    admin_client, authenticated_client, technician_client, session_factory
):
    created = authenticated_client.post(
        "/api/v1/tickets",
        json={
            "title": "Chamado para atribuição",
            "description": "Descrição suficientemente longa.",
            "category": "software",
        },
    ).json()
    with session_factory() as db:
        technician = db.scalar(
            select(User).where(User.email == "tech@example.com")
        )
        assert technician is not None
        technician_id = technician.id

    assigned = admin_client.patch(
        f"/api/v1/tickets/{created['id']}/assignee",
        json={"technician_id": technician_id},
    )
    assert assigned.status_code == 200
    assert assigned.json()["assigned_technician_id"] == technician_id
    assert technician_client.get(
        f"/api/v1/tickets/{created['id']}"
    ).status_code == 200

    started = admin_client.patch(
        f"/api/v1/tickets/{created['id']}/status",
        json={"status": "em_atendimento"},
    )
    assert started.status_code == 200
    assert started.json()["assigned_technician_id"] == technician_id

    unassigned = admin_client.patch(
        f"/api/v1/tickets/{created['id']}/assignee",
        json={"technician_id": None},
    )
    assert unassigned.status_code == 409
    unchanged = admin_client.get(f"/api/v1/tickets/{created['id']}").json()
    assert unchanged["status"] == "em_atendimento"
    assert unchanged["assigned_technician_id"] == technician_id

    returned_to_open = admin_client.patch(
        f"/api/v1/tickets/{created['id']}/status",
        json={"status": "aberto"},
    )
    assert returned_to_open.status_code == 200
    unassigned = admin_client.patch(
        f"/api/v1/tickets/{created['id']}/assignee",
        json={"technician_id": None},
    )
    assert unassigned.status_code == 200
    assert unassigned.json()["assigned_technician_id"] is None


def test_administrator_can_view_legacy_and_manage_users(
    admin_client, authenticated_client, session_factory
):
    requester_ticket = authenticated_client.post(
        "/api/v1/tickets",
        json={
            "title": "Chamado de solicitante",
            "description": "Descrição suficientemente longa.",
            "category": "software",
        },
    ).json()
    with session_factory() as db:
        legacy = Ticket(
            title="Chamado legado",
            description="Registro histórico sem proprietário.",
            category="outro",
            requester_id=None,
            tenant_id=1,
        )
        db.add(legacy)
        db.commit()
        legacy_id = legacy.id

    tickets = admin_client.get("/api/v1/tickets")
    users = admin_client.get("/api/v1/users")

    assert tickets.status_code == 200
    assert {ticket["id"] for ticket in tickets.json()} == {
        requester_ticket["id"],
        legacy_id,
    }
    assert any(user["email"] == "admin@example.com" for user in users.json())


def test_admin_can_change_role_and_deactivate_user(
    admin_client, client, session_factory
):
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Managed User",
            "email": "managed@example.com",
            "password": "secure-password",
        },
    )
    user_id = registration.json()["id"]

    role_response = admin_client.patch(
        f"/api/v1/users/{user_id}/role",
        json={"role": "technician"},
    )
    deactivate_response = admin_client.patch(
        f"/api/v1/users/{user_id}/active",
        json={"is_active": False},
    )
    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "managed@example.com", "password": "secure-password"},
    )
    activate_response = admin_client.patch(
        f"/api/v1/users/{user_id}/active",
        json={"is_active": True},
    )

    assert role_response.status_code == 200
    assert role_response.json()["role"] == "technician"
    assert deactivate_response.status_code == 200
    assert deactivate_response.json()["is_active"] is False
    assert login_response.status_code == 401
    assert activate_response.status_code == 200
    assert activate_response.json()["is_active"] is True
    with session_factory() as db:
        assert db.get(User, user_id) is not None


def test_non_admin_cannot_manage_users(authenticated_client):
    response = authenticated_client.get("/api/v1/users")
    assert response.status_code == 403


def test_inactive_membership_existing_token_is_rejected(
    admin_client, client, session_factory
):
    _, user_id, token = create_role_client(
        client, session_factory, "deactivated@example.com", UserRole.REQUESTER
    )
    admin_client.patch(
        f"/api/v1/users/{user_id}/active",
        json={"is_active": False},
    )

    response = client.get("/api/v1/tickets", headers={"Authorization": token})

    assert response.status_code == 403


def test_last_active_admin_cannot_be_demoted_or_deactivated(
    admin_client, session_factory
):
    with session_factory() as db:
        admin = db.scalar(select(User).where(User.email == "admin@example.com"))
        assert admin is not None
        admin_id = admin.id

    demote = admin_client.patch(
        f"/api/v1/users/{admin_id}/role",
        json={"role": "requester"},
    )
    deactivate = admin_client.patch(
        f"/api/v1/users/{admin_id}/active",
        json={"is_active": False},
    )

    assert demote.status_code == 409
    assert deactivate.status_code == 409


def test_concurrent_admin_changes_cannot_remove_all_active_admins(tmp_path):
    database_path = tmp_path / "concurrent-admins.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"timeout": 10},
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    try:
        Base.metadata.create_all(bind=engine)
        with session_factory() as db:
            company = Company(name="Concurrency tenant")
            db.add(company)
            db.flush()
            first = User(
                email="first-admin@example.com",
                password_hash="unused",
                role=UserRole.ADMIN,
            )
            second = User(
                email="second-admin@example.com",
                password_hash="unused",
                role=UserRole.ADMIN,
            )
            db.add_all([first, second])
            db.flush()
            db.add_all(
                [
                    Membership(
                        user_id=first.id,
                        company_id=company.id,
                        role=UserRole.ADMIN,
                    ),
                    Membership(
                        user_id=second.id,
                        company_id=company.id,
                        role=UserRole.ADMIN,
                    ),
                ]
            )
            db.commit()
            first_admin_id = first.id
            second_admin_id = second.id
            tenant_id = company.id

        first_context = TenantContext(
            user_id=first_admin_id,
            tenant_id=tenant_id,
            role=UserRole.ADMIN,
        )
        second_context = TenantContext(
            user_id=second_admin_id,
            tenant_id=tenant_id,
            role=UserRole.ADMIN,
        )

        start = Barrier(2)

        def demote_admin():
            with session_factory() as db:
                start.wait()
                try:
                    update_user_role(
                        first_admin_id,
                        UserRoleUpdate(role=UserRole.REQUESTER),
                        db,
                        first_context,
                    )
                except HTTPException as error:
                    return error.status_code
                return 200

        def deactivate_admin():
            with session_factory() as db:
                start.wait()
                try:
                    update_user_active_status(
                        second_admin_id,
                        UserActiveUpdate(is_active=False),
                        db,
                        second_context,
                    )
                except HTTPException as error:
                    return error.status_code
                return 200

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = (
                executor.submit(demote_admin),
                executor.submit(deactivate_admin),
            )
            results = [future.result() for future in futures]

        assert sorted(results) == [200, 409]
        with session_factory() as db:
            active_admins = db.scalars(
                select(Membership.id).where(
                    Membership.company_id == tenant_id,
                    Membership.role == UserRole.ADMIN,
                    Membership.is_active.is_(True),
                )
            ).all()
            assert len(active_admins) == 1
    finally:
        engine.dispose()


def test_requester_cannot_access_legacy_ticket(authenticated_client, session_factory):
    with session_factory() as db:
        legacy = Ticket(
            title="Chamado legado",
            description="Registro histórico sem proprietário.",
            category="outro",
            tenant_id=1,
        )
        db.add(legacy)
        db.commit()
        legacy_id = legacy.id

    assert authenticated_client.get(f"/api/v1/tickets/{legacy_id}").status_code == 403


def test_admin_only_can_see_legacy_ticket_available_queue(
    authenticated_client, admin_client, technician_client, session_factory
):
    with session_factory() as db:
        db.add(
            Ticket(
                title="Chamado legado",
                description="Registro histórico sem proprietário.",
                category="outro",
                tenant_id=1,
            )
        )
        db.commit()

    assert authenticated_client.get("/api/v1/tickets/available").status_code == 403
    assert technician_client.get("/api/v1/tickets/available").json() == []
    assert admin_client.get("/api/v1/tickets").status_code == 200


def test_legacy_migration_preserves_tickets_without_owner(tmp_path):
    legacy_database = tmp_path / "legacy.db"
    legacy_engine = create_engine(f"sqlite:///{legacy_database}")
    try:
        with legacy_engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TABLE tickets (
                    id INTEGER PRIMARY KEY,
                    title VARCHAR(160) NOT NULL,
                    description TEXT NOT NULL,
                    category VARCHAR(40) NOT NULL,
                    priority VARCHAR(20) NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """
            )
            connection.exec_driver_sql(
                """
                INSERT INTO tickets
                    (id, title, description, category, priority, status, created_at, updated_at)
                VALUES
                    (1, 'Legado 1', 'Histórico um.', 'outro', 'media', 'aberto',
                     '2025-01-01', '2025-01-01'),
                    (2, 'Legado 2', 'Histórico dois.', 'outro', 'alta', 'resolvido',
                     '2025-01-02', '2025-01-02')
                """
            )

        run_migrations(legacy_engine)
        run_migrations(legacy_engine)

        with legacy_engine.connect() as connection:
            rows = connection.exec_driver_sql(
                """
                SELECT id, title, requester_id, assigned_technician_id, tenant_id
                FROM tickets ORDER BY id
                """
            ).all()
            assert [tuple(row[:4]) for row in rows] == [
                (1, "Legado 1", None, None),
                (2, "Legado 2", None, None),
            ]
            assert rows[0][4] is not None
            assert rows[1][4] == rows[0][4]
            assert connection.exec_driver_sql(
                "SELECT name FROM companies WHERE id = ?", (rows[0][4],)
            ).scalar_one() == "Empresa legada"
            assert connection.exec_driver_sql(
                "SELECT COUNT(*) FROM users"
            ).scalar_one() == 0
    finally:
        legacy_engine.dispose()


def test_full_name_migration_preserves_existing_user_data(tmp_path):
    database_path = tmp_path / "existing-user-full-name.db"
    migration_engine = create_engine(f"sqlite:///{database_path}")
    config_path = Path(__file__).resolve().parents[1] / "alembic.ini"
    migration_config = Config(str(config_path))
    migration_config.set_main_option(
        "script_location",
        str(config_path.parent / "migrations"),
    )
    try:
        with migration_engine.begin() as connection:
            migration_config.attributes["connection"] = connection
            command.upgrade(migration_config, "20261030_0002")

        with migration_engine.begin() as connection:
            connection.exec_driver_sql(
                """
                INSERT INTO users (id, email, password_hash, role, is_active)
                VALUES
                    (1, 'Andubryanrj@hotmail.com', 'target-hash', 'requester', 1),
                    (18, 'existing@example.com', 'existing-hash', 'admin', 1),
                    (19, 'other@example.com', 'other-hash', 'technician', 1)
                """
            )

        with migration_engine.begin() as connection:
            migration_config.attributes["connection"] = connection
            command.upgrade(migration_config, "head")

        with migration_engine.connect() as connection:
            user = connection.exec_driver_sql(
                """
                SELECT id, email, password_hash, role, is_active, full_name
                FROM users ORDER BY id
                """
            ).all()
            assert [tuple(row) for row in user] == [
                (
                    1,
                    "Andubryanrj@hotmail.com",
                    "target-hash",
                    "requester",
                    1,
                    "Uanderson Martins",
                ),
                (18, "existing@example.com", "existing-hash", "admin", 1, None),
                (19, "other@example.com", "other-hash", "technician", 1, None),
            ]
    finally:
        migration_engine.dispose()


def test_migration_adds_role_fields_to_existing_users_table(tmp_path):
    database_path = tmp_path / "existing-users.db"
    legacy_engine = create_engine(f"sqlite:///{database_path}")
    try:
        with legacy_engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY,
                    email VARCHAR(320) NOT NULL UNIQUE,
                    password_hash VARCHAR(255) NOT NULL
                )
                """
            )
            connection.exec_driver_sql(
                """
                INSERT INTO users (id, email, password_hash)
                VALUES (1, 'existing@example.com', 'legacy-hash')
                """
            )

        run_migrations(legacy_engine)

        with legacy_engine.connect() as connection:
            user = connection.exec_driver_sql(
                "SELECT id, email, password_hash, role, is_active FROM users"
            ).one()
            assert tuple(user) == (
                1,
                "existing@example.com",
                "legacy-hash",
                "requester",
                1,
            )
            membership = connection.exec_driver_sql(
                """
                SELECT user_id, company_id, role, is_active
                FROM memberships WHERE user_id = 1
                """
            ).one()
            assert tuple(membership) == (1, 1, "requester", 1)
    finally:
        legacy_engine.dispose()


def test_migration_copies_existing_roles_and_active_status_to_memberships(tmp_path):
    database_path = tmp_path / "existing-memberships.db"
    legacy_engine = create_engine(f"sqlite:///{database_path}")
    try:
        with legacy_engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY,
                    email VARCHAR(320) NOT NULL UNIQUE,
                    password_hash VARCHAR(255) NOT NULL,
                    role VARCHAR(20) NOT NULL,
                    is_active BOOLEAN NOT NULL
                )
                """
            )
            connection.exec_driver_sql(
                """
                INSERT INTO users (id, email, password_hash, role, is_active)
                VALUES
                    (1, 'admin@example.com', 'admin-hash', 'admin', 1),
                    (2, 'tech@example.com', 'tech-hash', 'technician', 1),
                    (3, 'inactive@example.com', 'requester-hash', 'requester', 0)
                """
            )

        run_migrations(legacy_engine)

        with legacy_engine.connect() as connection:
            memberships = connection.exec_driver_sql(
                """
                SELECT user_id, company_id, role, is_active
                FROM memberships ORDER BY user_id
                """
            ).all()
            assert [tuple(row) for row in memberships] == [
                (1, 1, "admin", 1),
                (2, 1, "technician", 1),
                (3, 1, "requester", 0),
            ]
    finally:
        legacy_engine.dispose()
