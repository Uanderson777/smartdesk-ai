from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import jwt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main as main_module
from app.database import Base, get_db, run_migrations
from app.main import app
from app.models import Ticket, User, UserRole
from app.schemas import UserActiveUpdate, UserRoleUpdate
from app.security import create_access_token, verify_password
from app.users import update_user_active_status, update_user_role


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


def create_role_client(client, session_factory, email, role):
    registration = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "secure-password"},
    )
    assert registration.status_code == 201
    with session_factory() as db:
        user = db.scalar(select(User).where(User.email == email))
        assert user is not None
        user.role = role
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
            "email": "New.User@example.com",
            "password": password,
            "role": "admin",
        },
    )

    assert response.status_code == 201
    assert response.json() == {"id": 1, "email": "new.user@example.com"}
    with session_factory() as db:
        user = db.scalar(select(User).where(User.email == "new.user@example.com"))
        assert user is not None
        assert user.role == UserRole.REQUESTER
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


def test_update_ticket_status(admin_client):
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
        json={"email": "managed@example.com", "password": "secure-password"},
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


def test_inactive_user_existing_token_is_rejected(
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

    assert response.status_code == 401


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
            db.add_all(
                [
                    User(
                        email="first-admin@example.com",
                        password_hash="unused",
                        role=UserRole.ADMIN,
                    ),
                    User(
                        email="second-admin@example.com",
                        password_hash="unused",
                        role=UserRole.ADMIN,
                    ),
                ]
            )
            db.commit()

        start = Barrier(2)

        def demote_admin():
            with session_factory() as db:
                start.wait()
                try:
                    update_user_role(
                        1,
                        UserRoleUpdate(role=UserRole.REQUESTER),
                        db,
                    )
                except HTTPException as error:
                    return error.status_code
                return 200

        def deactivate_admin():
            with session_factory() as db:
                start.wait()
                try:
                    update_user_active_status(
                        2,
                        UserActiveUpdate(is_active=False),
                        db,
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
                select(User.id).where(
                    User.role == UserRole.ADMIN,
                    User.is_active.is_(True),
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
                "SELECT id, title, requester_id, assigned_technician_id FROM tickets ORDER BY id"
            ).all()
            assert rows == [
                (1, "Legado 1", None, None),
                (2, "Legado 2", None, None),
            ]
            assert connection.exec_driver_sql(
                "SELECT COUNT(*) FROM users"
            ).scalar_one() == 0
    finally:
        legacy_engine.dispose()


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
    finally:
        legacy_engine.dispose()
