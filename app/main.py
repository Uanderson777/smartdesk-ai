from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app.models import Ticket
from app.schemas import TicketCreate, TicketRead, TicketStatusUpdate


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
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


@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "ok", "service": "SmartDesk AI"}


@app.post(
    "/api/v1/tickets",
    response_model=TicketRead,
    status_code=status.HTTP_201_CREATED,
    tags=["Tickets"],
)
def create_ticket(payload: TicketCreate, db: Session = Depends(get_db)):
    ticket = Ticket(
        title=payload.title,
        description=payload.description,
        category=payload.category.value,
        priority=payload.priority.value,
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
):
    statement = select(Ticket).order_by(Ticket.created_at.desc()).offset(skip).limit(limit)
    return list(db.scalars(statement).all())


@app.get("/api/v1/tickets/{ticket_id}", response_model=TicketRead, tags=["Tickets"])
def get_ticket(ticket_id: int, db: Session = Depends(get_db)):
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Chamado não encontrado.")
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
):
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Chamado não encontrado.")

    ticket.status = payload.status.value
    db.commit()
    db.refresh(ticket)
    return ticket
