from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class TicketCategory(str, Enum):
    hardware = "hardware"
    software = "software"
    rede = "rede"
    acesso = "acesso"
    outro = "outro"


class TicketPriority(str, Enum):
    baixa = "baixa"
    media = "media"
    alta = "alta"
    critica = "critica"


class TicketStatus(str, Enum):
    aberto = "aberto"
    em_atendimento = "em_atendimento"
    aguardando_usuario = "aguardando_usuario"
    resolvido = "resolvido"
    fechado = "fechado"


class TicketCreate(BaseModel):
    title: str = Field(min_length=5, max_length=160)
    description: str = Field(min_length=10, max_length=5000)
    category: TicketCategory
    priority: TicketPriority = TicketPriority.media


class TicketStatusUpdate(BaseModel):
    status: TicketStatus


class TicketRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    category: TicketCategory
    priority: TicketPriority
    status: TicketStatus
    created_at: datetime
    updated_at: datetime


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserRead(BaseModel):
    id: int
    email: EmailStr


class AccessToken(BaseModel):
    access_token: str
    token_type: str = "bearer"
