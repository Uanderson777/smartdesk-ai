from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.config import AISettings
from app.ai.gemini import GeminiProvider
from app.ai.providers import AIConfigurationError
from app.ai.schemas import TicketTriageInput, TicketTriageResponse
from app.ai.service import AIServiceError, TicketTriageService
from app.database import get_db
from app.dependencies import TenantContext, require_roles
from app.models import Ticket, UserRole

router = APIRouter(prefix="/api/v1/tickets", tags=["AI triage"])


def get_triage_service() -> TicketTriageService:
    try:
        settings = AISettings.from_environment()
    except AIConfigurationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="A configuração do serviço de IA é inválida.",
        ) from None

    providers = (
        [GeminiProvider(settings)]
        if settings.gemini_api_key is not None
        else []
    )
    return TicketTriageService(providers)


@router.post(
    "/{ticket_id}/triage",
    response_model=TicketTriageResponse,
    tags=["AI"],
)
def triage_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    context: TenantContext = Depends(
        require_roles(UserRole.ADMIN, UserRole.TECHNICIAN)
    ),
    service: TicketTriageService = Depends(get_triage_service),
) -> TicketTriageResponse:
    statement = select(Ticket).where(
        Ticket.id == ticket_id,
        Ticket.tenant_id == context.tenant_id,
    )
    if context.role == UserRole.TECHNICIAN:
        statement = statement.where(
            Ticket.requester_id.is_not(None),
            (Ticket.assigned_technician_id.is_(None))
            | (Ticket.assigned_technician_id == context.user_id),
        )

    ticket = db.scalar(statement)
    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chamado não encontrado.",
        )

    triage_input = TicketTriageInput(
        title=ticket.title,
        description=ticket.description,
        current_category=ticket.category,
        current_priority=ticket.priority,
    )
    try:
        recommendation = service.analyze(triage_input)
    except AIConfigurationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="O serviço de IA não está configurado.",
        ) from None
    except AIServiceError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Não foi possível obter a triagem do provedor de IA.",
        ) from None

    return TicketTriageResponse(
        ticket_id=ticket.id,
        **recommendation.model_dump(),
    )
