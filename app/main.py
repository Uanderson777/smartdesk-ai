from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth import router as auth_router
from app.database import engine, get_db, run_migrations
from app.dependencies import get_current_user, require_roles
from app.models import Ticket, User, UserRole
from app.schemas import (
    TicketAssigneeUpdate,
    TicketCreate,
    TicketRead,
    TicketStatusUpdate,
)
from app.security import get_jwt_secret
from app.users import router as users_router


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
app.include_router(auth_router)
app.include_router(users_router)


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
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in (UserRole.REQUESTER, UserRole.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem permissão para abrir chamados.",
        )
    ticket = Ticket(
        title=payload.title,
        description=payload.description,
        category=payload.category.value,
        priority=payload.priority.value,
        requester_id=current_user.id,
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
    current_user: User = Depends(get_current_user),
):
    statement = select(Ticket)
    if current_user.role == UserRole.REQUESTER:
        statement = statement.where(Ticket.requester_id == current_user.id)
    elif current_user.role == UserRole.TECHNICIAN:
        statement = statement.where(
            Ticket.requester_id.is_not(None),
            (Ticket.assigned_technician_id.is_(None))
            | (Ticket.assigned_technician_id == current_user.id),
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
    _: User = Depends(require_roles(UserRole.ADMIN, UserRole.TECHNICIAN)),
):
    statement = (
        select(Ticket)
        .where(
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
    current_user: User = Depends(get_current_user),
):
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Chamado não encontrado.")
    if current_user.role == UserRole.REQUESTER and ticket.requester_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem permissão para visualizar este chamado.",
        )
    if current_user.role == UserRole.TECHNICIAN and (
        ticket.requester_id is None
        or ticket.assigned_technician_id not in (None, current_user.id)
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
    current_user: User = Depends(get_current_user),
):
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Chamado não encontrado.")
    if current_user.role == UserRole.REQUESTER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solicitantes não podem atualizar o status dos chamados.",
        )
    if (
        current_user.role == UserRole.TECHNICIAN
        and ticket.assigned_technician_id != current_user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Técnicos só podem atualizar chamados atribuídos a eles.",
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
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.TECHNICIAN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Somente técnicos podem assumir chamados.",
        )
    result = db.execute(
        update(Ticket)
        .where(
            Ticket.id == ticket_id,
            Ticket.requester_id.is_not(None),
            Ticket.assigned_technician_id.is_(None),
        )
        .values(
            assigned_technician_id=current_user.id,
            status="em_atendimento",
        )
    )
    if result.rowcount != 1:
        db.rollback()
        ticket = db.get(Ticket, ticket_id)
        if ticket is None:
            raise HTTPException(status_code=404, detail="Chamado não encontrado.")
        if ticket.requester_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Chamados históricos sem solicitante não podem ser assumidos.",
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Chamado já está atribuído.",
        )

    db.commit()
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chamado não encontrado.",
        )
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
    _: User = Depends(require_roles(UserRole.ADMIN)),
):
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Chamado não encontrado.")
    if ticket.requester_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Chamados históricos sem solicitante não podem ser atribuídos.",
        )

    technician = (
        db.get(User, payload.technician_id)
        if payload.technician_id is not None
        else None
    )
    if payload.technician_id is not None and (
        technician is None
        or technician.role != UserRole.TECHNICIAN
        or not technician.is_active
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="O usuário informado não é um técnico ativo.",
        )

    ticket.assigned_technician_id = (
        technician.id if technician is not None else None
    )
    db.commit()
    db.refresh(ticket)
    return ticket
