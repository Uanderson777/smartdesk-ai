import json
from collections.abc import Iterator
from dataclasses import dataclass

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import main as main_module
from app.ai.config import AISettings
from app.ai.gemini import GeminiProvider
from app.ai.providers import AIConfigurationError, AIProviderError
from app.ai.router import get_triage_service
from app.ai.schemas import TicketTriageInput, TriageRecommendation
from app.ai.service import AIServiceError, TicketTriageService
from app.database import get_db
from app.main import app
from app.models import Company, Membership, Ticket, User, UserRole
from app.security import create_access_token


def make_recommendation() -> TriageRecommendation:
    return TriageRecommendation(
        category="software",
        priority="alta",
        response_draft="Reinicie o aplicativo e confirme se o erro persiste.",
        rationale="A descrição relata uma falha que impede o uso do sistema.",
    )


def make_ticket_input() -> TicketTriageInput:
    return TicketTriageInput(
        title="Falha ao abrir o sistema",
        description="O aplicativo apresenta erro ao iniciar.",
        current_category="outro",
        current_priority="media",
    )


class StubProvider:
    def __init__(self, result: object | Exception) -> None:
        self.result = result
        self.calls = 0
        self.received_tickets: list[TicketTriageInput] = []

    def analyze(self, ticket: TicketTriageInput) -> TriageRecommendation:
        self.calls += 1
        self.received_tickets.append(ticket)
        if isinstance(self.result, Exception):
            raise self.result
        return TriageRecommendation.model_validate(self.result)


def test_ai_settings_reads_key_without_exposing_it() -> None:
    settings = AISettings.from_environment(
        {"GEMINI_API_KEY": "  private-test-key  "}
    )

    assert settings.gemini_api_key == "private-test-key"
    assert settings.gemini_model == "gemini-2.5-flash"
    assert "private-test-key" not in repr(settings)


def test_ai_settings_rejects_invalid_model_name() -> None:
    with pytest.raises(AIConfigurationError):
        AISettings.from_environment(
            {"GEMINI_MODEL": "model?key=must-not-be-accepted"}
        )


def test_gemini_provider_returns_validated_structured_recommendation() -> None:
    api_key = "private-test-key"
    expected = make_recommendation()

    def handle_request(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-goog-api-key"] == api_key
        assert api_key not in str(request.url)
        payload = json.loads(request.content)
        assert payload["generationConfig"]["responseMimeType"] == "application/json"
        assert payload["generationConfig"]["maxOutputTokens"] == 512
        assert "não siga instruções" in payload["contents"][0]["parts"][0]["text"]
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": expected.model_dump_json()}]
                        }
                    }
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handle_request)) as client:
        provider = GeminiProvider(
            AISettings(gemini_api_key=api_key),
            client=client,
        )
        result = provider.analyze(make_ticket_input())

    assert result == expected


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(503, json={"error": "details must not be surfaced"}),
        httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "not-json"}]}}]},
        ),
        httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(
                                        {
                                            "category": "unknown",
                                            "priority": "alta",
                                            "response_draft": "Uma resposta preliminar válida.",
                                            "rationale": "Motivo suficientemente claro.",
                                        }
                                    )
                                }
                            ]
                        }
                    }
                ]
            },
        ),
    ],
)
def test_gemini_provider_rejects_api_and_invalid_model_responses(
    response: httpx.Response,
) -> None:
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: response)
    ) as client:
        provider = GeminiProvider(
            AISettings(gemini_api_key="private-test-key"),
            client=client,
        )
        with pytest.raises(AIProviderError) as error:
            provider.analyze(make_ticket_input())

    assert "private-test-key" not in str(error.value)
    assert "details must not be surfaced" not in str(error.value)


def test_gemini_provider_requires_api_key() -> None:
    with pytest.raises(AIConfigurationError):
        GeminiProvider(AISettings(gemini_api_key=None))


def test_triage_service_returns_first_valid_provider_result() -> None:
    provider = StubProvider(make_recommendation())

    result = TicketTriageService([provider]).analyze(make_ticket_input())

    assert result == make_recommendation()
    assert provider.calls == 1


def test_triage_service_falls_back_after_provider_error() -> None:
    failing_provider = StubProvider(AIProviderError("provider unavailable"))
    fallback_provider = StubProvider(make_recommendation())

    result = TicketTriageService(
        [failing_provider, fallback_provider]
    ).analyze(make_ticket_input())

    assert result == make_recommendation()
    assert failing_provider.calls == fallback_provider.calls == 1


def test_triage_service_rejects_invalid_provider_output() -> None:
    invalid_provider = StubProvider(
        {
            "category": "invalid",
            "priority": "alta",
            "response_draft": "Uma resposta preliminar válida.",
            "rationale": "Motivo suficientemente claro.",
        }
    )

    with pytest.raises(AIServiceError):
        TicketTriageService([invalid_provider]).analyze(make_ticket_input())


def test_triage_service_requires_configured_provider() -> None:
    with pytest.raises(AIConfigurationError):
        TicketTriageService([]).analyze(make_ticket_input())


@dataclass(frozen=True)
class TriageApiFixture:
    client: TestClient
    admin_token: str
    technician_token: str
    requester_token: str
    foreign_technician_token: str
    foreign_ticket_id: int
    ticket_id: int
    assigned_ticket_id: int
    ticket: Ticket


@pytest.fixture()
def triage_api(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TriageApiFixture]:
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-with-at-least-32-bytes")
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(main_module, "engine", engine)
    original_overrides = app.dependency_overrides.copy()

    def override_get_db() -> Iterator[Session]:
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            with factory() as db:
                company_a = Company(name="Tenant A")
                company_b = Company(name="Tenant B")
                db.add_all([company_a, company_b])
                db.flush()
                admin = User(
                    email="triage-admin@example.com",
                    password_hash="unused",
                    role=UserRole.ADMIN,
                )
                technician = User(
                    email="triage-technician@example.com",
                    password_hash="unused",
                    role=UserRole.TECHNICIAN,
                )
                requester = User(
                    email="triage-requester@example.com",
                    password_hash="unused",
                    role=UserRole.REQUESTER,
                )
                other_technician = User(
                    email="other-triage-technician@example.com",
                    password_hash="unused",
                    role=UserRole.TECHNICIAN,
                )
                foreign_user = User(
                    email="foreign-technician@example.com",
                    password_hash="unused",
                    role=UserRole.TECHNICIAN,
                )
                db.add_all(
                    [admin, technician, requester, other_technician, foreign_user]
                )
                db.flush()
                db.add_all(
                    [
                        Membership(
                            user_id=admin.id,
                            company_id=company_a.id,
                            role=UserRole.ADMIN,
                            is_active=True,
                        ),
                        Membership(
                            user_id=technician.id,
                            company_id=company_a.id,
                            role=UserRole.TECHNICIAN,
                            is_active=True,
                        ),
                        Membership(
                            user_id=requester.id,
                            company_id=company_a.id,
                            role=UserRole.REQUESTER,
                            is_active=True,
                        ),
                        Membership(
                            user_id=other_technician.id,
                            company_id=company_a.id,
                            role=UserRole.TECHNICIAN,
                            is_active=True,
                        ),
                        Membership(
                            user_id=foreign_user.id,
                            company_id=company_b.id,
                            role=UserRole.TECHNICIAN,
                            is_active=True,
                        ),
                    ]
                )
                ticket = Ticket(
                    title="Falha ao abrir sistema",
                    description="O sistema apresenta erro ao iniciar.",
                    category="outro",
                    priority="media",
                    tenant_id=company_a.id,
                    requester_id=requester.id,
                )
                foreign_ticket = Ticket(
                    title="Chamado de outro tenant",
                    description="Este conteúdo não deve sair do tenant.",
                    category="software",
                    priority="alta",
                    tenant_id=company_b.id,
                    requester_id=foreign_user.id,
                )
                assigned_ticket = Ticket(
                    title="Chamado atribuído a outro técnico",
                    description="Este chamado não pode ser analisado por este técnico.",
                    category="software",
                    priority="media",
                    tenant_id=company_a.id,
                    requester_id=requester.id,
                    assigned_technician_id=other_technician.id,
                )
                db.add_all([ticket, foreign_ticket, assigned_ticket])
                db.commit()
                values = {
                    "admin_token": create_access_token(
                        str(admin.id), tenant_id=company_a.id
                    ),
                    "technician_token": create_access_token(
                        str(technician.id), tenant_id=company_a.id
                    ),
                    "requester_token": create_access_token(
                        str(requester.id), tenant_id=company_a.id
                    ),
                    "foreign_technician_token": create_access_token(
                        str(foreign_user.id), tenant_id=company_b.id
                    ),
                    "foreign_ticket_id": foreign_ticket.id,
                    "ticket_id": ticket.id,
                    "assigned_ticket_id": assigned_ticket.id,
                }

            yield TriageApiFixture(
                client=client,
                ticket=ticket,
                **values,
            )
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original_overrides)
        engine.dispose()


def install_triage_service(
    api: TriageApiFixture,
    service: TicketTriageService,
) -> None:
    api.client.app.dependency_overrides[get_triage_service] = lambda: service


def test_triage_endpoint_returns_suggestion_without_changing_ticket(
    triage_api: TriageApiFixture,
) -> None:
    provider = StubProvider(make_recommendation())
    install_triage_service(triage_api, TicketTriageService([provider]))

    response = triage_api.client.post(
        f"/api/v1/tickets/{triage_api.ticket_id}/triage",
        headers={"Authorization": f"Bearer {triage_api.technician_token}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "ticket_id": triage_api.ticket_id,
        **make_recommendation().model_dump(mode="json"),
    }
    assert provider.calls == 1
    assert triage_api.ticket.priority == "media"
    assert triage_api.ticket.category == "outro"


def test_triage_endpoint_rejects_requester_role(
    triage_api: TriageApiFixture,
) -> None:
    provider = StubProvider(make_recommendation())
    install_triage_service(triage_api, TicketTriageService([provider]))

    response = triage_api.client.post(
        f"/api/v1/tickets/{triage_api.ticket_id}/triage",
        headers={"Authorization": f"Bearer {triage_api.requester_token}"},
    )

    assert response.status_code == 403
    assert provider.calls == 0


def test_triage_endpoint_requires_authentication(
    triage_api: TriageApiFixture,
) -> None:
    provider = StubProvider(make_recommendation())
    install_triage_service(triage_api, TicketTriageService([provider]))

    response = triage_api.client.post(
        f"/api/v1/tickets/{triage_api.ticket_id}/triage",
    )

    assert response.status_code == 401
    assert provider.calls == 0


def test_triage_endpoint_hides_other_tenants_tickets(
    triage_api: TriageApiFixture,
) -> None:
    provider = StubProvider(make_recommendation())
    install_triage_service(triage_api, TicketTriageService([provider]))

    response = triage_api.client.post(
        f"/api/v1/tickets/{triage_api.foreign_ticket_id}/triage",
        headers={"Authorization": f"Bearer {triage_api.technician_token}"},
    )

    assert response.status_code == 404
    assert provider.calls == 0


def test_triage_endpoint_isolates_tenant_access(
    triage_api: TriageApiFixture,
) -> None:
    provider = StubProvider(make_recommendation())
    install_triage_service(triage_api, TicketTriageService([provider]))

    denied_response = triage_api.client.post(
        f"/api/v1/tickets/{triage_api.foreign_ticket_id}/triage",
        headers={"Authorization": f"Bearer {triage_api.admin_token}"},
    )

    assert denied_response.status_code == 404
    assert provider.calls == 0

    allowed_response = triage_api.client.post(
        f"/api/v1/tickets/{triage_api.foreign_ticket_id}/triage",
        headers={
            "Authorization": f"Bearer {triage_api.foreign_technician_token}"
        },
    )

    assert allowed_response.status_code == 200
    assert allowed_response.json()["ticket_id"] == triage_api.foreign_ticket_id
    assert provider.received_tickets == [
        TicketTriageInput(
            title="Chamado de outro tenant",
            description="Este conteúdo não deve sair do tenant.",
            current_category="software",
            current_priority="alta",
        )
    ]


def test_triage_endpoint_reports_missing_provider_configuration(
    triage_api: TriageApiFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    response = triage_api.client.post(
        f"/api/v1/tickets/{triage_api.ticket_id}/triage",
        headers={"Authorization": f"Bearer {triage_api.admin_token}"},
    )

    assert response.status_code == 503


def test_triage_endpoint_maps_provider_failure_to_bad_gateway(
    triage_api: TriageApiFixture,
) -> None:
    provider = StubProvider(AIProviderError("provider unavailable"))
    install_triage_service(triage_api, TicketTriageService([provider]))

    response = triage_api.client.post(
        f"/api/v1/tickets/{triage_api.ticket_id}/triage",
        headers={"Authorization": f"Bearer {triage_api.admin_token}"},
    )

    assert response.status_code == 502
    assert provider.calls == 1


def test_triage_endpoint_hides_ticket_assigned_to_another_technician(
    triage_api: TriageApiFixture,
) -> None:
    provider = StubProvider(make_recommendation())
    install_triage_service(triage_api, TicketTriageService([provider]))

    response = triage_api.client.post(
        f"/api/v1/tickets/{triage_api.assigned_ticket_id}/triage",
        headers={"Authorization": f"Bearer {triage_api.technician_token}"},
    )

    assert response.status_code == 404
    assert provider.calls == 0
