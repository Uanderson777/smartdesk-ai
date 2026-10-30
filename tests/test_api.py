from datetime import timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main as main_module
from app.database import Base, get_db
from app.main import app
from app.models import User
from app.security import create_access_token, verify_password


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
def authenticated_client(client):
    registered = client.post(
        "/api/v1/auth/register",
        json={"email": "tester@example.com", "password": "secure-password"},
    )
    assert registered.status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "tester@example.com", "password": "secure-password"},
    )
    assert login.status_code == 200
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
    return client


def test_register_user_returns_public_data_and_stores_password_hash(
    client, session_factory
):
    password = "secure-password"
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "New.User@example.com", "password": password},
    )

    assert response.status_code == 201
    assert response.json() == {"id": 1, "email": "new.user@example.com"}
    with session_factory() as db:
        user = db.scalar(select(User).where(User.email == "new.user@example.com"))
        assert user is not None
        assert user.password_hash != password
        assert verify_password(password, user.password_hash)


def test_register_duplicate_email_returns_409(client):
    payload = {"email": "duplicate@example.com", "password": "secure-password"}
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201

    response = client.post(
        "/api/v1/auth/register",
        json={"email": "DUPLICATE@example.com", "password": "another-password"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "E-mail já cadastrado."}


def test_login_returns_bearer_token(client):
    client.post(
        "/api/v1/auth/register",
        json={"email": "login@example.com", "password": "secure-password"},
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
        json={"email": "known@example.com", "password": "secure-password"},
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


def test_update_ticket_status(authenticated_client):
    payload = {
        "title": "Solicitação de acesso",
        "description": "Usuário precisa de acesso ao sistema interno.",
        "category": "acesso",
        "priority": "baixa",
    }
    created = authenticated_client.post("/api/v1/tickets", json=payload).json()
    response = authenticated_client.patch(
        f"/api/v1/tickets/{created['id']}/status",
        json={"status": "em_atendimento"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "em_atendimento"


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
