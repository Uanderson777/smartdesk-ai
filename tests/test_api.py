import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


@pytest.fixture()
def client():
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(
        bind=test_engine, autoflush=False, autocommit=False
    )
    Base.metadata.create_all(bind=test_engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()


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


def test_create_and_read_ticket(client):
    payload = {
        "title": "Computador sem internet",
        "description": "A estação não consegue acessar sites externos.",
        "category": "rede",
        "priority": "alta",
    }
    created = client.post("/api/v1/tickets", json=payload)
    assert created.status_code == 201
    ticket_id = created.json()["id"]

    fetched = client.get(f"/api/v1/tickets/{ticket_id}")
    assert fetched.status_code == 200
    assert fetched.json()["title"] == payload["title"]
    assert fetched.json()["status"] == "aberto"


def test_list_tickets(client):
    payload = {
        "title": "Falha ao abrir sistema",
        "description": "Aplicativo apresenta erro ao iniciar.",
        "category": "software",
        "priority": "media",
    }
    client.post("/api/v1/tickets", json=payload)
    response = client.get("/api/v1/tickets")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_update_ticket_status(client):
    payload = {
        "title": "Solicitação de acesso",
        "description": "Usuário precisa de acesso ao sistema interno.",
        "category": "acesso",
        "priority": "baixa",
    }
    created = client.post("/api/v1/tickets", json=payload).json()
    response = client.patch(
        f"/api/v1/tickets/{created['id']}/status",
        json={"status": "em_atendimento"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "em_atendimento"


def test_missing_ticket_returns_404(client):
    response = client.get("/api/v1/tickets/999")
    assert response.status_code == 404


def test_invalid_ticket_is_rejected(client):
    response = client.post(
        "/api/v1/tickets",
        json={
            "title": "abc",
            "description": "curta",
            "category": "inexistente",
            "priority": "urgente",
        },
    )
    assert response.status_code == 422
