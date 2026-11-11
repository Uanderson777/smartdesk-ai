from collections.abc import Mapping
from contextlib import asynccontextmanager
import os

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.router import router as ai_router
from app.auth import router as auth_router
from app.database import engine, get_db, run_migrations
from app.dependencies import TenantContext, get_tenant_context, require_roles
from app.models import Membership, Ticket, User, UserRole
from app.schemas import (
    TicketAssigneeUpdate,
    TicketCreate,
    TicketRead,
    TicketStatusUpdate,
)
from app.security import get_jwt_secret
from app.users import router as users_router


VERCEL_FRONTEND_ORIGINS = (
    "https://smartdesk-ai-app.vercel.app",
    "https://smartdesk-ai-rfqc.vercel.app",
)


def cors_origins_from_environment(
    environment: Mapping[str, str] | None = None,
) -> list[str]:
    values = os.environ if environment is None else environment
    configured_origins = values.get(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,"
        + VERCEL_FRONTEND_ORIGIN,
    )
    origins = list(
        dict.fromkeys(
            origin.strip().rstrip("/")
            for origin in configured_origins.split(",")
            if origin.strip()
        )
    )
    for origin in VERCEL_FRONTEND_ORIGINS:
        if origin not in origins:
            origins.append(origin)
    return origins


CORS_ORIGINS = cors_origins_from_environment()


def lock_ticket(
    db: Session,
    ticket_id: int,
    context: TenantContext,
) -> Ticket | None:
    if db.get_bind().dialect.name == "sqlite":
        db.rollback()
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")

    ticket = db.scalar(
        select(Ticket)
        .where(
            Ticket.id == ticket_id,
            Ticket.tenant_id == context.tenant_id,
        )
        .with_for_update()
    )
    if ticket is None:
        return None

    active_membership = db.scalar(
        select(Membership)
        .join(User, User.id == Membership.user_id)
        .where(
            Membership.user_id == context.user_id,
            Membership.company_id == context.tenant_id,
            Membership.role == context.role,
            Membership.is_active.is_(True),
            User.is_active.is_(True),
        )
        .with_for_update()
    )
    if active_membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Selecione uma empresa com participação ativa.",
        )
    return ticket


def active_technician_membership(
    db: Session,
    technician_id: int,
    tenant_id: int,
) -> Membership | None:
    return db.scalar(
        select(Membership)
        .join(User, User.id == Membership.user_id)
        .where(
            Membership.user_id == technician_id,
            Membership.company_id == tenant_id,
            Membership.role == UserRole.TECHNICIAN,
            Membership.is_active.is_(True),
            User.is_active.is_(True),
        )
        .with_for_update()
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_jwt_secret()
    run_migrations(engine)
    yield


app = FastAPI(
    title="SmartDesk AI",
    description=(
        "API de Service Desk para gerenciamento de chamados. "
        "Projeto de portfólio em evolução."
    ),
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(ai_router)


@app.get("/", tags=["Health"])
def root():
    return {
        "service": "SmartDesk AI",
        "version": "0.1.0",
        "description": "API inteligente de gerenciamento de chamados de Service Desk",
        "status": "online",
        "documentation": "/docs",
    }


@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "ok", "service": "SmartDesk AI"}


@app.post(
    "/api/v1/tickets",
    response_model=TicketRead,
    status_code=status.HTTP_201_CREATED,
    tags=["Tickets"],
)
def create_ticket(
    payload: TicketCreate,
    db: Session = Depends(get_db),
    context: TenantContext = Depends(get_tenant_context),
):
    if context.role not in (UserRole.REQUESTER, UserRole.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem permissão para abrir chamados.",
        )
    ticket = Ticket(
        title=payload.title,
        description=payload.description,
        category=payload.category.value,
        priority=payload.priority.value,
        requester_id=context.user_id,
        tenant_id=context.tenant_id,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


@app.get("/api/v1/tickets", response_model=list[TicketRead], tags=["Tickets"])
def list_tickets(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    context: TenantContext = Depends(get_tenant_context),
):
    statement = select(Ticket).where(Ticket.tenant_id == context.tenant_id)
    if context.role == UserRole.REQUESTER:
        statement = statement.where(Ticket.requester_id == context.user_id)
    elif context.role == UserRole.TECHNICIAN:
        statement = statement.where(
            Ticket.requester_id.is_not(None),
            (Ticket.assigned_technician_id.is_(None))
            | (Ticket.assigned_technician_id == context.user_id),
        )
    statement = statement.order_by(Ticket.created_at.desc()).offset(skip).limit(limit)
    return list(db.scalars(statement).all())


@app.get(
    "/api/v1/tickets/available",
    response_model=list[TicketRead],
    tags=["Tickets"],
)
def list_available_tickets(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    context: TenantContext = Depends(
        require_roles(UserRole.ADMIN, UserRole.TECHNICIAN)
    ),
):
    statement = (
        select(Ticket)
        .where(
            Ticket.tenant_id == context.tenant_id,
            Ticket.requester_id.is_not(None),
            Ticket.assigned_technician_id.is_(None),
        )
        .order_by(Ticket.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(db.scalars(statement).all())


@app.get("/api/v1/tickets/{ticket_id}", response_model=TicketRead, tags=["Tickets"])
def get_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    context: TenantContext = Depends(get_tenant_context),
):
    ticket = db.scalar(
        select(Ticket).where(
            Ticket.id == ticket_id,
            Ticket.tenant_id == context.tenant_id,
        )
    )
    if ticket is None:
        raise HTTPException(status_code=404, detail="Chamado não encontrado.")
    if context.role == UserRole.REQUESTER and ticket.requester_id != context.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem permissão para visualizar este chamado.",
        )
    if context.role == UserRole.TECHNICIAN and (
        ticket.requester_id is None
        or ticket.assigned_technician_id not in (None, context.user_id)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem permissão para visualizar este chamado.",
        )
    return ticket


@app.patch(
    "/api/v1/tickets/{ticket_id}/status",
    response_model=TicketRead,
    tags=["Tickets"],
)
def update_ticket_status(
    ticket_id: int,
    payload: TicketStatusUpdate,
    db: Session = Depends(get_db),
    context: TenantContext = Depends(get_tenant_context),
):
    ticket = lock_ticket(db, ticket_id, context)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Chamado não encontrado.")
    if context.role == UserRole.REQUESTER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solicitantes não podem atualizar o status dos chamados.",
        )
    if (
        context.role == UserRole.TECHNICIAN
        and ticket.assigned_technician_id != context.user_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Técnicos só podem atualizar chamados atribuídos a eles.",
        )
    if payload.status.value == "em_atendimento":
        if ticket.assigned_technician_id is None or active_technician_membership(
            db,
            ticket.assigned_technician_id,
            context.tenant_id,
        ) is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="O chamado precisa de um técnico ativo atribuído para iniciar o atendimento.",
            )

    ticket.status = payload.status.value
    db.commit()
    db.refresh(ticket)
    return ticket


@app.post(
    "/api/v1/tickets/{ticket_id}/claim",
    response_model=TicketRead,
    tags=["Tickets"],
)
def claim_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    context: TenantContext = Depends(get_tenant_context),
):
    if context.role != UserRole.TECHNICIAN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Somente técnicos podem assumir chamados.",
        )
    ticket = lock_ticket(db, ticket_id, context)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Chamado não encontrado.")
    if ticket.requester_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chamados históricos sem solicitante não podem ser assumidos.",
        )
    if ticket.assigned_technician_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Chamado já está atribuído.",
        )
    if active_technician_membership(db, context.user_id, context.tenant_id) is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Somente técnicos ativos da empresa podem assumir chamados.",
        )

    ticket.assigned_technician_id = context.user_id
    ticket.status = "em_atendimento"
    db.commit()
    db.refresh(ticket)
    return ticket


@app.patch(
    "/api/v1/tickets/{ticket_id}/assignee",
    response_model=TicketRead,
    tags=["Tickets"],
)
def assign_ticket(
    ticket_id: int,
    payload: TicketAssigneeUpdate,
    db: Session = Depends(get_db),
    context: TenantContext = Depends(require_roles(UserRole.ADMIN)),
):
    ticket = lock_ticket(db, ticket_id, context)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Chamado não encontrado.")
    if ticket.requester_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Chamados históricos sem solicitante não podem ser atribuídos.",
        )
    if (
        payload.technician_id is None
        and ticket.status == "em_atendimento"
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Altere o status do chamado antes de desatribuir o técnico.",
        )

    technician_membership = None
    if payload.technician_id is not None:
        technician_membership = active_technician_membership(
            db,
            payload.technician_id,
            context.tenant_id,
        )
    if payload.technician_id is not None and technician_membership is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="O usuário informado não é um técnico ativo.",
        )

    ticket.assigned_technician_id = (
        technician_membership.user_id if technician_membership is not None else None
    )
    db.commit()
    db.refresh(ticket)
    return ticket
